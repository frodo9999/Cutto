import asyncio
import os
import subprocess
import tempfile
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


async def composite_video(
    clip_uris: list[str],
    user_asset_uri: str | None,
    job_id: str,
    gcs_bucket: str,
    add_transitions: bool = True,
) -> str:
    """
    Composite all generated clips into a final video using FFmpeg.
    Returns GCS URI of the final video.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Download all clips
        local_clips = []
        for i, uri in enumerate(clip_uris):
            local_path = os.path.join(tmpdir, f"clip_{i:02d}.mp4")
            await download_from_gcs(uri, local_path)
            local_clips.append(local_path)

        # Optionally download user asset
        if user_asset_uri:
            user_asset_path = os.path.join(tmpdir, "user_asset.mp4")
            await download_from_gcs(user_asset_uri, user_asset_path)

        # Create concat file
        concat_file = os.path.join(tmpdir, "concat.txt")
        with open(concat_file, "w") as f:
            for clip in local_clips:
                f.write(f"file '{clip}'\n")

        # Output path
        output_path = os.path.join(tmpdir, "final.mp4")

        if add_transitions:
            # Use xfade filter for smooth transitions
            await _composite_with_transitions(local_clips, output_path)
        else:
            # Simple concatenation
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                output_path
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        # Upload final video to GCS
        output_uri = f"gs://{gcs_bucket}/jobs/{job_id}/final.mp4"
        await upload_to_gcs(output_path, output_uri)

        return output_uri


async def _composite_with_transitions(clips: list[str], output_path: str):
    """Apply xfade transitions between clips."""
    if len(clips) == 1:
        import shutil
        shutil.copy(clips[0], output_path)
        return

    # Build complex filtergraph for xfade
    inputs = []
    for clip in clips:
        inputs.extend(["-i", clip])

    # Get durations
    durations = []
    for clip in clips:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", clip],
            capture_output=True, text=True
        )
        durations.append(float(result.stdout.strip()))

    # Build xfade filter chain
    transition_duration = 0.3
    filter_parts = []
    offset = durations[0] - transition_duration

    for i in range(1, len(clips)):
        if i == 1:
            in_a = "[0:v]"
        else:
            in_a = f"[v{i-1}]"
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
        output_path
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise Exception(f"FFmpeg failed: {stderr.decode()}")


async def generate_signed_url(gcs_uri: str, expiration_minutes: int = 60) -> str:
    """Generate a signed URL for temporary access to a GCS object."""
    from datetime import timedelta
    bucket_name, blob_name = _parse_gcs_uri(gcs_uri)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    url = blob.generate_signed_url(
        expiration=timedelta(minutes=expiration_minutes),
        method="GET",
    )
    return url
