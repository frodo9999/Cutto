import asyncio
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from google.cloud import storage

storage_client = storage.Client()


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    """Parse gs://bucket/path into (bucket, path)"""
    uri = uri.replace("gs://", "")
    parts = uri.split("/", 1)
    return parts[0], parts[1]


async def download_from_gcs(gcs_uri: str, local_path: str):
    """Download a file from GCS to local path."""
    bucket_name, blob_name = _parse_gcs_uri(gcs_uri)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(local_path)


async def upload_to_gcs(local_path: str, gcs_uri: str):
    """Upload a local file to GCS."""
    bucket_name, blob_name = _parse_gcs_uri(gcs_uri)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path)


def _get_clip_duration(clip_path: str) -> float:
    """Get actual duration of a video file using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            clip_path,
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _cut_clip(input_path: str, output_path: str, start: float, duration: float):
    """
    Cut a clip from start_seconds for duration seconds.
    Uses re-encode for frame-accurate cut at any start point.
    """
    actual = _get_clip_duration(input_path)
    # Clamp to actual clip bounds
    start = max(0.0, min(start, actual))
    duration = min(duration, actual - start)
    if duration <= 0:
        shutil.copy(input_path, output_path)
        return

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-an",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        shutil.copy(input_path, output_path)


async def composite_video(
    clip_uris: list[str],
    user_asset_uri: str | None,
    job_id: str,
    gcs_bucket: str,
    cut_points: list[tuple[float, float]] | None = None,
    add_transitions: bool = True,
) -> str:
    """
    Composite all generated clips into a final video using FFmpeg.
    Uses Gemini-determined cut_points (start, end) per clip for smart trimming.
    Returns GCS URI of the final video.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Download all clips
        raw_clips = []
        for i, uri in enumerate(clip_uris):
            local_path = os.path.join(tmpdir, f"raw_{i:02d}.mp4")
            await download_from_gcs(uri, local_path)
            raw_clips.append(local_path)

        # Smart trim each clip using Gemini cut points
        local_clips = []
        for i, raw_path in enumerate(raw_clips):
            trimmed_path = os.path.join(tmpdir, f"clip_{i:02d}.mp4")
            if cut_points and i < len(cut_points):
                start, end = cut_points[i]
            else:
                start, end = 0.0, _get_clip_duration(raw_path)
            duration = end - start
            print(f"[FFmpeg] Cutting clip {i}: {start:.2f}s → {end:.2f}s ({duration:.2f}s)")
            _cut_clip(raw_path, trimmed_path, start, duration)
            local_clips.append(trimmed_path)

        # Optionally prepend user asset
        if user_asset_uri:
            user_asset_path = os.path.join(tmpdir, "user_asset.mp4")
            await download_from_gcs(user_asset_uri, user_asset_path)
            local_clips.insert(0, user_asset_path)

        # Output path
        output_path = os.path.join(tmpdir, "final.mp4")

        if add_transitions and len(local_clips) > 1:
            await _composite_with_transitions(local_clips, output_path)
        else:
            await _simple_concat(local_clips, output_path, tmpdir)

        # Upload final video to GCS
        output_uri = f"gs://{gcs_bucket}/jobs/{job_id}/final.mp4"
        await upload_to_gcs(output_path, output_uri)

        return output_uri


async def _simple_concat(clips: list[str], output_path: str, tmpdir: str):
    """Simple concatenation using concat demuxer."""
    concat_file = os.path.join(tmpdir, "concat.txt")
    with open(concat_file, "w") as f:
        for clip in clips:
            f.write(f"file '{clip}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        output_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise Exception(f"FFmpeg concat failed: {stderr.decode()}")


async def _composite_with_transitions(clips: list[str], output_path: str):
    """Apply xfade transitions between clips."""
    if len(clips) == 1:
        shutil.copy(clips[0], output_path)
        return

    # Build inputs
    inputs = []
    for clip in clips:
        inputs.extend(["-i", clip])

    # Get actual durations of trimmed clips
    durations = [_get_clip_duration(c) for c in clips]

    # Use a short transition — keeps energy high
    transition_duration = 0.2
    filter_parts = []
    offset = durations[0] - transition_duration

    for i in range(1, len(clips)):
        in_a = "[0:v]" if i == 1 else f"[v{i-1}]"
        in_b = f"[{i}:v]"
        out = f"[v{i}]" if i < len(clips) - 1 else "[vout]"
        filter_parts.append(
            f"{in_a}{in_b}xfade=transition=fade:duration={transition_duration}:offset={offset:.2f}{out}"
        )
        if i < len(clips) - 1:
            offset += durations[i] - transition_duration

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        output_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise Exception(f"FFmpeg xfade failed: {stderr.decode()}")


async def generate_signed_url(gcs_uri: str, expiration_minutes: int = 60) -> str:
    """Generate a accessible URL for the output video."""
    bucket_name, blob_name = _parse_gcs_uri(gcs_uri)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.make_public()
    return blob.public_url