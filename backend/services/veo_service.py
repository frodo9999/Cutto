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


def _load_image(image_path: str) -> types.Image:
    """Load a local image file into a Veo-compatible Image object."""
    import mimetypes
    mime, _ = mimetypes.guess_type(image_path)
    mime = mime or "image/png"
    with open(image_path, "rb") as f:
        data = f.read()
    return types.Image(image_bytes=data, mime_type=mime)


def _generate_clip_sync(
    prompt: str,
    duration_seconds: int,
    output_gcs_uri: str,
    reference_image_path: str | None = None,
) -> str:
    """Synchronous Veo generation - runs in thread pool.
    Always generates 8s to give Gemini the most material to find the best cut.
    If reference_image_path is provided, uses image-to-video for continuity.
    """
    FIXED_DURATION = 8
    client = _create_veo_client()

    config = types.GenerateVideosConfig(
        duration_seconds=FIXED_DURATION,
        output_gcs_uri=output_gcs_uri,
        aspect_ratio="9:16",
        number_of_videos=1,
        enhance_prompt=True,
    )

    if reference_image_path:
        print(f"[Veo] Using image-to-video with reference frame: {reference_image_path}")
        image = _load_image(reference_image_path)
        operation = client.models.generate_videos(
            model=VEO_MODEL,
            prompt=prompt,
            image=image,
            config=config,
        )
    else:
        operation = client.models.generate_videos(
            model=VEO_MODEL,
            prompt=prompt,
            config=config,
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
    reference_image_path: str | None = None,
) -> str:
    """Async wrapper - runs sync Veo call in thread pool."""
    return await asyncio.to_thread(
        _generate_clip_sync, prompt, duration_seconds, output_gcs_uri, reference_image_path
    )


async def generate_all_clips(
    prompts: list[str],
    scene_durations: list[int],
    gcs_bucket: str,
    job_id: str,
    continuous_flags: list[bool] | None = None,
) -> list[str]:
    """
    Generate all clips sequentially.
    If continuous_flags[i] is True, scene i+1 is generated using Veo Scene Extension
    from scene i — Veo uses the last second of the previous clip to maintain
    visual continuity (same objects, lighting, environment).
    """
    clip_uris = []

    for i, (prompt, duration) in enumerate(zip(prompts, scene_durations)):
        output_uri = f"gs://{gcs_bucket}/jobs/{job_id}/clips/scene_{i:02d}.mp4"

        # Use Scene Extension if previous scene is marked continuous with this one
        use_extension = (
            i > 0
            and continuous_flags is not None
            and i - 1 < len(continuous_flags)
            and continuous_flags[i - 1]
        )

        if use_extension:
            prev_uri = clip_uris[-1]
            print(f"[Veo] Scene {i+1}: using Scene Extension from scene {i} for continuity...")
            uri = await _extend_video_clip(prompt, prev_uri, output_uri)
        else:
            print(f"[Veo] Scene {i+1}/{len(prompts)}: generating independently...")
            uri = await generate_video_clip(prompt, duration, output_uri)

        clip_uris.append(uri)

    return clip_uris


def _extend_clip_sync(prompt: str, source_gcs_uri: str, output_gcs_uri: str) -> str:
    """Synchronous Veo Scene Extension - runs in thread pool.
    Veo uses the final second of source_gcs_uri as context for visual continuity.
    """
    from google.genai.types import Video as VeoVideo
    client = _create_veo_client()

    operation = client.models.generate_videos(
        model=VEO_MODEL,
        prompt=prompt,
        video=VeoVideo(
            uri=source_gcs_uri,
            mime_type="video/mp4",
        ),
        config=types.GenerateVideosConfig(
            output_gcs_uri=output_gcs_uri,
            number_of_videos=1,
            enhance_prompt=True,
        ),
    )

    while not operation.done:
        print(f"[Veo] Waiting for extension {getattr(operation, 'name', '?')}...")
        time.sleep(15)
        operation = client.operations.get(operation)

    print(f"[Veo] Scene Extension done.")

    error = getattr(operation, "error", None)
    if error:
        if isinstance(error, dict):
            error_msg = error.get("message") or str(error)
        else:
            error_msg = getattr(error, "message", None) or str(error)
        if error_msg and error_msg.lower() not in ("none", ""):
            raise Exception(f"Veo extension error: {error_msg}")
        print(f"[Veo] Extension error field present but empty: {error!r}")

    uri = _extract_video_uri(operation)
    if not uri:
        raise Exception("Veo Scene Extension returned no video URI")

    print(f"[Veo] Extended clip: {uri}")
    return uri


async def _extend_video_clip(prompt: str, source_gcs_uri: str, output_gcs_uri: str) -> str:
    """Async wrapper for Veo Scene Extension."""
    return await asyncio.to_thread(
        _extend_clip_sync, prompt, source_gcs_uri, output_gcs_uri
    )

async def generate_continuous_group_clip(
    prompts: list[str],
    gcs_bucket: str,
    job_id: str,
    group_id: int,
) -> str:
    """
    Generate a long clip for a continuous scene group by:
    1. Generating the first scene as an 8s clip
    2. Extending it for each subsequent scene (7s each)
    Returns the GCS URI of the final extended clip.
    """
    # Generate base clip (first scene in group)
    base_uri = f"gs://{gcs_bucket}/jobs/{job_id}/groups/group_{group_id:02d}_base.mp4"
    print(f"[Veo] Group {group_id}: generating base clip for scene 1/{len(prompts)}...")
    current_uri = await generate_video_clip(prompts[0], 8, base_uri)

    # Extend for each subsequent scene
    for i, prompt in enumerate(prompts[1:], start=1):
        ext_uri = f"gs://{gcs_bucket}/jobs/{job_id}/groups/group_{group_id:02d}_ext_{i:02d}.mp4"
        print(f"[Veo] Group {group_id}: extending for scene {i+1}/{len(prompts)}...")
        current_uri = await _extend_video_clip(prompt, current_uri, ext_uri)

    print(f"[Veo] Group {group_id}: long clip ready → {current_uri}")
    return current_uri