import os
import json
import base64
from google import genai
from google.genai import types
from google.genai.types import Modality
from models.schemas import AnalysisResult
from typing import AsyncGenerator

client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image-preview"


async def analyze_viral_video_stream(video_gcs_uri: str) -> AsyncGenerator[dict, None]:
    """
    Step 1: Analyze video with gemini-3.1-pro-preview (text only).
    Step 2: Generate storyboard images with gemini-3.1-flash-image-preview (interleaved).
    """
    # --- Step 1: Video analysis (text) ---
    analysis_prompt = """You are an expert viral content strategist and video editor.

Analyze this viral video deeply and provide a comprehensive breakdown.

Return your analysis as a JSON object with this exact structure:
{
  "hook_strategy": "description of the first 3 seconds hook technique",
  "pacing": "description of editing rhythm and cut frequency",
  "visual_style": "color grading, framing, camera movement style",
  "audio_style": "music type, beat sync, sound effect usage",
  "caption_style": "text overlay style, font energy, placement",
  "viral_factors": ["factor1", "factor2", "factor3"],
  "storyboard": [
    {
      "scene": 1,
      "duration": 3,
      "description": "what happens in this scene",
      "visual_prompt": "detailed Veo prompt to recreate this scene style",
      "timing_note": "edit/transition note"
    }
  ]
}

Be specific and actionable. The goal is to help someone recreate the viral formula with their own content."""

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_uri(file_uri=video_gcs_uri, mime_type="video/mp4"),
                types.Part.from_text(text=analysis_prompt),
            ],
        )
    ]

    full_text = ""
    async for chunk in await client.aio.models.generate_content_stream(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(temperature=0.4),
    ):
        for part in chunk.candidates[0].content.parts:
            if part.text:
                full_text += part.text
                yield {"type": "text_chunk", "content": part.text.replace('\n', '\\n')}

    # Parse analysis JSON
    analysis_data = None
    try:
        json_start = full_text.find("{")
        json_end = full_text.rfind("}") + 1
        if json_start != -1:
            analysis_data = json.loads(full_text[json_start:json_end])
            yield {"type": "analysis_complete", "content": analysis_data}
    except Exception as e:
        yield {"type": "error", "content": f"Failed to parse analysis: {str(e)}"}
        return

    # --- Step 2: Generate storyboard images (interleaved) ---
    if analysis_data and analysis_data.get("storyboard"):
        yield {"type": "text_chunk", "content": "\n\n🎬 Generating storyboard visuals...\n"}

        scenes_desc = "\n".join(
            [f"Scene {s['scene']}: {s['description']}" for s in analysis_data["storyboard"]]
        )
        image_prompt = f"""Create a visual storyboard for a viral video with these scenes:

{scenes_desc}

Visual style: {analysis_data.get('visual_style', 'modern, dynamic')}

For each scene, generate a storyboard frame image showing the key visual moment.
Between each image, write a brief caption with the scene number and timing note."""

        try:
            image_response = await client.aio.models.generate_content(
                model=GEMINI_IMAGE_MODEL,
                contents=image_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=[Modality.TEXT, Modality.IMAGE],
                    temperature=0.7,
                ),
            )

            for part in image_response.candidates[0].content.parts:
                if part.text:
                    yield {"type": "text_chunk", "content": part.text.replace('\n', '\\n')}
                elif part.inline_data:
                    print(f"[DEBUG] Image generated! size={len(part.inline_data.data)} bytes")
                    image_b64 = base64.b64encode(part.inline_data.data).decode()
                    yield {
                        "type": "storyboard_image",
                        "content": f"data:{part.inline_data.mime_type};base64,{image_b64}",
                    }
                else:
                    print(f"[DEBUG] Unknown part type: {part}")
        except Exception as e:
            yield {"type": "text_chunk", "content": f"\n(Storyboard generation skipped: {str(e)})\n"}

    yield {"type": "done"}


async def generate_veo_prompts(
    analysis: AnalysisResult,
    custom_assets_description: str,
    user_requirements: str,
) -> list[str]:
    prompt = f"""You are a Veo video generation expert.

Based on this viral video analysis:
{json.dumps(analysis.model_dump(), indent=2)}

User's custom assets/brand: {custom_assets_description}
User's requirements: {user_requirements}

Generate optimized Veo video generation prompts for each scene in the storyboard.
Incorporate the user's brand/assets while maintaining the viral formula.

Return ONLY a JSON array of strings, one prompt per scene:
["prompt for scene 1", "prompt for scene 2", ...]

Each prompt should be 2-3 sentences, highly descriptive."""

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.6),
    )

    text = response.text
    json_start = text.find("[")
    json_end = text.rfind("]") + 1
    prompts = json.loads(text[json_start:json_end])
    return prompts