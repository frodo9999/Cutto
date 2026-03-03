import os
import asyncio
from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
)

VEO_MODEL = os.getenv("VEO_MODEL", "veo-3.1-generate-preview")


async def generate_video_clip(
    prompt: str,
    duration_seconds: int = 5,
    output_gcs_uri: str = None,
) -> str:
    """
    Generate a video clip using Veo 3.1.
    Returns GCS URI of the generated video.
    """
    operation = await client.aio.models.generate_videos(
        model=VEO_MODEL,
        prompt=prompt,
        config=types.GenerateVideosConfig(
            duration_seconds=duration_seconds,
            output_gcs_uri=output_gcs_uri,
            aspect_ratio="9:16",  # Vertical for short-form viral content
            number_of_videos=1,
        ),
    )

    # Poll until done
    while not operation.done:
        await asyncio.sleep(5)
        operation = await operation.refresh()

    if operation.error:
        raise Exception(f"Veo generation failed: {operation.error}")

    generated_videos = operation.response.generated_videos
    if not generated_videos:
        raise Exception("No videos generated")

    return generated_videos[0].video.uri


async def generate_all_clips(
    prompts: list[str],
    scene_durations: list[int],
    gcs_bucket: str,
    job_id: str,
) -> list[str]:
    """
    Generate all video clips in parallel.
    Returns list of GCS URIs.
    """
    tasks = []
    for i, (prompt, duration) in enumerate(zip(prompts, scene_durations)):
        output_uri = f"gs://{gcs_bucket}/jobs/{job_id}/clips/scene_{i:02d}.mp4"
        tasks.append(generate_video_clip(prompt, duration, output_uri))

    clip_uris = await asyncio.gather(*tasks)
    return list(clip_uris)
