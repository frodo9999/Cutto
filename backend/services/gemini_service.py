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
    analysis_prompt = """You are an expert viral content strategist, cinematographer, and Veo video generation specialist.

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
      "visual_prompt": "A highly detailed Veo cinematic prompt for this scene. Must include: (1) subject and action, (2) camera movement (e.g. slow push in, handheld tracking, static wide), (3) lighting (e.g. golden hour backlight, soft studio fill, neon rim light), (4) color grade (e.g. warm orange tones, desaturated muted palette, high contrast punchy), (5) shot type (e.g. extreme close-up on product, medium shot, aerial drone), (6) mood/energy (e.g. fast-paced kinetic energy, calm meditative, euphoric). Write as a single flowing paragraph of 4-6 sentences.",
      "timing_note": "edit/transition note",
      "transition_out": "cut"
    }
  ]
}

For transition_out, choose exactly one from this list based on what you observe in the video:
- "cut" — instant hard cut (most common in fast-paced viral videos)
- "fade" — fade to black/white then fade in
- "dissolve" — crossfade/dissolve between scenes
- "wipeleft" — wipe from right to left
- "wiperight" — wipe from left to right
- "slideleft" — slide outgoing scene to the left
- "slideright" — slide outgoing scene to the right
- "slideup" — slide outgoing scene upward
- "slidedown" — slide outgoing scene downward

Default to "cut" unless you clearly see a different transition in the original video.
Be specific and actionable. The visual_prompt for each scene must be detailed enough for Veo to generate a high-quality, on-brand video clip without any additional context."""

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
    """
    Generate high-quality Veo prompts by combining:
    - The visual_prompt already crafted per scene during analysis
    - The overall visual/audio style of the viral video
    - The user's brand identity and requirements
    """

    # Build a concise style reference from the analysis
    style_context = f"""Viral video style DNA:
- Hook: {analysis.hook_strategy}
- Pacing: {analysis.pacing}
- Visual: {analysis.visual_style}
- Audio energy: {analysis.audio_style}
- Viral factors: {', '.join(analysis.viral_factors) if analysis.viral_factors else 'n/a'}"""

    # Build scene list with the pre-generated visual_prompts as starting points
    scenes_context = ""
    for i, scene in enumerate(analysis.storyboard):
        scenes_context += f"""
Scene {scene['scene']} ({scene['duration']}s):
  Description: {scene['description']}
  Base visual prompt: {scene.get('visual_prompt', '')}
  Timing: {scene.get('timing_note', '')}"""

    prompt = f"""You are a world-class Veo video generation specialist and brand cinematographer.

Your task: Write one final Veo generation prompt per scene that will produce a stunning, on-brand marketing video clip.

{style_context}

Brand & product information:
{custom_assets_description}

Additional user requirements:
{user_requirements if user_requirements else 'None'}

Scenes to generate prompts for:
{scenes_context}

INSTRUCTIONS:
1. Start from the "Base visual prompt" for each scene — it captures the viral style DNA.
2. Adapt it to feature the user's brand/product naturally within that visual style.
3. Preserve the camera movement, lighting mood, color grade, and energy from the original analysis.
4. Each final prompt must be a single flowing paragraph of 5-7 sentences.
5. Be hyper-specific: include subject, action, camera movement, lighting, color grade, shot type, and mood.
6. Do NOT use generic phrases like "high quality" or "cinematic" alone — describe exactly what you see.
7. If the user provided no brand info, focus purely on recreating the viral visual style.

Return ONLY a valid JSON array with one string per scene, in order:
["<full prompt for scene 1>", "<full prompt for scene 2>", ...]

No markdown, no explanation, just the JSON array."""

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.5),
    )

    text = response.text
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    json_start = text.find("[")
    json_end = text.rfind("]") + 1
    prompts = json.loads(text[json_start:json_end])
    return prompts


async def find_best_cut(
    clip_gcs_uri: str,
    scene: dict,
    target_duration: float,
) -> tuple[float, float]:
    """
    Use Gemini video understanding to find the best start/end cut points
    within an 8s clip, based on the original scene analysis.

    Returns (start_seconds, end_seconds).
    """
    prompt = f"""You are a professional video editor reviewing a raw video clip.

This clip was generated for the following scene:
- Scene description: {scene.get('description', '')}
- Target duration: {target_duration:.1f} seconds
- Timing note: {scene.get('timing_note', '')}
- Visual prompt used: {scene.get('visual_prompt', '')}

Watch the clip carefully and find the best {target_duration:.1f}-second window that:
1. Captures the most visually compelling and on-brand moment
2. Avoids any AI artifacts, distortions, or awkward transitions at the cut points
3. Starts at a natural beginning of motion or visual beat
4. Ends at a natural pause or completion of motion

The clip is {8} seconds long. Return ONLY a JSON object:
{{
  "start": <float, seconds from beginning>,
  "end": <float, seconds from beginning>,
  "reason": "<one sentence explaining why this window is best>"
}}

Constraints:
- end - start must equal exactly {target_duration:.1f} seconds
- start >= 0.0
- end <= 8.0
- If the whole clip is good, return {{"start": 0.0, "end": {target_duration:.1f}, "reason": "..."}}"""

    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(file_uri=clip_gcs_uri, mime_type="video/mp4"),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
            config=types.GenerateContentConfig(temperature=0.2),
        )

        text = response.text.strip()
        # Strip markdown fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        result = json.loads(text[json_start:json_end])

        start = float(result.get("start", 0.0))
        end = float(result.get("end", target_duration))
        reason = result.get("reason", "")

        # Validate constraints
        start = max(0.0, min(start, 8.0 - target_duration))
        end = start + target_duration
        end = min(end, 8.0)

        print(f"[Gemini] Best cut for scene: {start:.2f}s → {end:.2f}s | {reason}")
        return start, end

    except Exception as e:
        print(f"[Gemini] find_best_cut failed ({e}), using start=0")
        return 0.0, min(target_duration, 8.0)