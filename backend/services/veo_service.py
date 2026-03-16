import os
import time
import asyncio
from google import genai
from google.genai import types

VEO_MODEL = os.getenv("VEO_MODEL", "veo-3.1-generate-preview")


def _create_veo_client():
    return genai.Client(
        vertexai=True,
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("VEO_LOCATION", "us-central1"),
    )


def _extract_video_uri(operation) -> str | None:
    """Try every known response structure to extract the GCS URI."""
    # Structure 1: operation.result.generated_videos[0].video.uri
    result = getattr(operation, "result", None)
    if result:
        videos = getattr(result, "generated_videos", None)
        if videos:
            try:
                return videos[0].video.uri
            except Exception:
                pass

    # Structure 2: operation.response.generated_videos[0].video.uri
    response = getattr(operation, "response", None)
    if response:
        videos = getattr(response, "generated_videos", None)
        if videos:
            try:
                return videos[0].video.uri
            except Exception:
                pass

    # Structure 3: response is a dict
    if isinstance(response, dict):
        try:
            return response["generated_videos"][0]["video"]["uri"]
        except (KeyError, IndexError, TypeError):
            pass

    return None


def _generate_clip_sync(prompt: str, duration_seconds: int, output_gcs_uri: str) -> str:
    """Synchronous Veo generation - runs in thread pool.
    Always generates 8s to give Gemini the most material to find the best cut.
    """
    # Always use 8s — Gemini will find the best cut window afterward
    FIXED_DURATION = 8

    client = _create_veo_client()

    operation = client.models.generate_videos(
        model=VEO_MODEL,
        prompt=prompt,
        config=types.GenerateVideosConfig(
            duration_seconds=FIXED_DURATION,
            output_gcs_uri=output_gcs_uri,
            aspect_ratio="9:16",
            number_of_videos=1,
            enhance_prompt=True,
        ),
    )

    # Poll until done
    while not operation.done:
        print(f"[Veo] Waiting for operation {getattr(operation, 'name', '?')}...")
        time.sleep(15)
        operation = client.operations.get(operation)

    print(f"[Veo] Operation done.")

    # Check for error — operation.error can be an object, dict, or None
    error = getattr(operation, "error", None)
    if error:
        # Extract message regardless of error format
        if isinstance(error, dict):
            error_msg = error.get("message") or str(error)
        else:
            error_msg = getattr(error, "message", None) or str(error)
        # Only raise if there's an actual non-empty message
        if error_msg and error_msg.lower() not in ("none", ""):
            raise Exception(f"Veo error: {error_msg}")
        else:
            # error object exists but message is None/empty — log and continue
            print(f"[Veo] Operation error field present but empty: {error!r}")

    # Extract URI
    uri = _extract_video_uri(operation)
    if not uri:
        # Log full operation for debugging
        try:
            print(f"[Veo] Could not extract URI. operation.result={operation.result!r}")
            print(f"[Veo] operation.response={operation.response!r}")
        except Exception:
            pass
        raise Exception("Veo returned no video URI — check GCS bucket permissions and output_gcs_uri path")

    print(f"[Veo] Clip generated: {uri}")
    return uri


async def generate_video_clip(
    prompt: str,
    duration_seconds: int = 6,
    output_gcs_uri: str = None,
) -> str:
    """Async wrapper - runs sync Veo call in thread pool."""
    return await asyncio.to_thread(
        _generate_clip_sync, prompt, duration_seconds, output_gcs_uri
    )


async def generate_all_clips(
    prompts: list[str],
    scene_durations: list[int],
    gcs_bucket: str,
    job_id: str,
) -> list[str]:
    """Generate all clips sequentially."""
    clip_uris = []
    for i, (prompt, duration) in enumerate(zip(prompts, scene_durations)):
        output_uri = f"gs://{gcs_bucket}/jobs/{job_id}/clips/scene_{i:02d}.mp4"
        print(f"[Veo] Generating clip {i+1}/{len(prompts)}...")
        uri = await generate_video_clip(prompt, duration, output_uri)
        clip_uris.append(uri)
    return clip_uris