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


def _generate_clip_sync(prompt: str, duration_seconds: int, output_gcs_uri: str) -> str:
    """Synchronous Veo generation - runs in thread pool."""
    valid_durations = [4, 6, 8]
    duration_seconds = min(valid_durations, key=lambda x: abs(x - duration_seconds))
    client = _create_veo_client()

    operation = client.models.generate_videos(
        model=VEO_MODEL,
        prompt=prompt,
        config=types.GenerateVideosConfig(
            duration_seconds=duration_seconds,
            output_gcs_uri=output_gcs_uri,
            aspect_ratio="9:16",
            number_of_videos=1,
        ),
    )

    # Poll until done
    while not operation.done:
        print(f"[Veo] Waiting for video generation...")
        time.sleep(15)
        operation = client.operations.get(operation)

    print(f"[Veo] Operation done. Response: {operation.response}")
    print(f"[Veo] Operation result: {operation.result}")
    print(f"[Veo] Operation error: {operation.error}")

    if operation.error:
        error_msg = operation.error.get('message') if isinstance(operation.error, dict) else str(operation.error)
        raise Exception(f"Veo error: {error_msg}")

    # Try different response structures
    result = operation.result
    if result and hasattr(result, 'generated_videos') and result.generated_videos:
        uri = result.generated_videos[0].video.uri
    elif operation.response and hasattr(operation.response, 'generated_videos') and operation.response.generated_videos:
        uri = operation.response.generated_videos[0].video.uri
    else:
        print(f"[Veo] Full operation dump: {vars(operation)}")
        raise Exception("Veo returned no videos")
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