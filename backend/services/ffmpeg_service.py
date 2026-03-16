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
    transitions: list[str] | None = None,
    add_transitions: bool = True,
) -> str:
    """
    Composite all generated clips into a final video using FFmpeg.
    Uses Gemini-determined cut_points (start, end) per clip for smart trimming.
    Uses per-scene transition types from original video analysis.
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
            await _composite_with_transitions(local_clips, output_path, transitions)
        else:
            await _simple_concat(local_clips, output_path, tmpdir)

        # Upload final video to GCS
        output_uri = f"gs://{gcs_bucket}/jobs/{job_id}/final.mp4"
        await upload_to_gcs(output_path, output_uri)

        return output_uri


async def _simple_concat(clips: list[str], output_path: str, tmpdir: str):
    """Concatenate clips with re-encode for format consistency."""
    concat_file = os.path.join(tmpdir, "concat.txt")
    with open(concat_file, "w") as f:
        for clip in clips:
            f.write(f"file '{clip}'\n")

    print(f"[FFmpeg] Concatenating {len(clips)} clips...")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-an",
        "-movflags", "+faststart",
        output_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise Exception(f"FFmpeg concat failed: {stderr.decode()[-500:]}")
    print(f"[FFmpeg] Concat done → {output_path}")


# xfade transition types supported by FFmpeg
XFADE_TRANSITIONS = {
    "dissolve", "fade", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown",
    "circlecrop", "rectcrop", "distance", "fadeblack", "fadewhite",
    "radial", "smoothleft", "smoothright", "smoothup", "smoothdown",
    "horzopen", "horzclose", "vertopen", "vertclose",
}


async def _composite_with_transitions(
    clips: list[str],
    output_path: str,
    transitions: list[str] | None = None,
):
    """
    Composite clips with per-scene transition types.
    - "cut": hard cut, no xfade overlap
    - anything else: xfade with that transition type
    Falls back to simple concat if all transitions are hard cuts.
    """
    if len(clips) == 1:
        shutil.copy(clips[0], output_path)
        return

    # Normalize transitions list — default to "cut" if not provided
    n_transitions = len(clips) - 1
    if transitions:
        trans = [t.lower().strip() for t in transitions[:n_transitions]]
        # Pad with "cut" if shorter than needed
        trans += ["cut"] * (n_transitions - len(trans))
    else:
        trans = ["cut"] * n_transitions

    print(f"[FFmpeg] Transitions: {trans}")

    # If all cuts — simple concat is faster and cleaner
    if all(t == "cut" for t in trans):
        import tempfile, os
        tmpdir = os.path.dirname(output_path)
        await _simple_concat(clips, output_path, tmpdir)
        return

    # Mixed: group consecutive cuts and apply xfade for non-cuts
    # Strategy: re-encode each clip uniformly first, then build filtergraph
    durations = [_get_clip_duration(c) for c in clips]
    inputs = []
    for clip in clips:
        inputs.extend(["-i", clip])

    XFADE_DUR = 0.2  # keep snappy
    filter_parts = []
    # We build a chain: [prev_out][i:v] xfade -> [vi]
    prev_label = "[0:v]"
    timeline_offset = durations[0]  # running offset accounting for overlaps

    for i in range(1, len(clips)):
        t = trans[i - 1]
        in_b = f"[{i}:v]"
        out_label = f"[v{i}]" if i < len(clips) - 1 else "[vout]"

        if t == "cut":
            # Hard cut: use xfade with duration=0 equivalent — use "fade" at offset
            # Actually: use concat filter for hard cuts, xfade for the rest
            # Simplest: treat cut as xfade with duration=0.05 (imperceptible)
            xfade_type = "fade"
            xfade_dur = 0.05
        else:
            xfade_type = t if t in XFADE_TRANSITIONS else "fade"
            xfade_dur = XFADE_DUR

        offset = timeline_offset - xfade_dur
        offset = max(0.0, offset)

        filter_parts.append(
            f"{prev_label}{in_b}xfade=transition={xfade_type}"
            f":duration={xfade_dur}:offset={offset:.3f}{out_label}"
        )

        prev_label = out_label
        timeline_offset += durations[i] - xfade_dur

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
        print(f"[FFmpeg] xfade failed, falling back to simple concat: {stderr.decode()[-300:]}")
        tmpdir = os.path.dirname(output_path)
        await _simple_concat(clips, output_path, tmpdir)


async def extract_keyframes(
    video_gcs_uri: str,
    timestamps: list[float],
    job_id: str,
    gcs_bucket: str,
) -> list[str]:
    """
    Download video from GCS, extract one frame per timestamp,
    upload to GCS, return list of public URLs.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        local_video = os.path.join(tmpdir, "source.mp4")
        await download_from_gcs(video_gcs_uri, local_video)

        frame_urls = []
        for i, ts in enumerate(timestamps):
            frame_path = os.path.join(tmpdir, f"frame_{i:02d}.jpg")
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(ts),
                "-i", local_video,
                "-frames:v", "1",
                "-q:v", "3",
                "-vf", "scale=480:-1",
                frame_path,
            ]
            result = subprocess.run(cmd, capture_output=True)

            if result.returncode == 0 and os.path.exists(frame_path):
                gcs_frame_uri = f"gs://{gcs_bucket}/jobs/{job_id}/frames/frame_{i:02d}.jpg"
                await upload_to_gcs(frame_path, gcs_frame_uri)
                bucket_name, blob_name = _parse_gcs_uri(gcs_frame_uri)
                bucket = storage_client.bucket(bucket_name)
                blob = bucket.blob(blob_name)
                blob.make_public()
                frame_urls.append(blob.public_url)
                print(f"[Keyframe] Scene {i+1} @ {ts:.1f}s → {blob.public_url}")
            else:
                print(f"[Keyframe] Failed to extract frame at {ts:.1f}s")
                frame_urls.append(None)

        return frame_urls


async def generate_signed_url(gcs_uri: str, expiration_minutes: int = 60) -> str:
    """Generate a accessible URL for the output video."""
    bucket_name, blob_name = _parse_gcs_uri(gcs_uri)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.make_public()
    return blob.public_url