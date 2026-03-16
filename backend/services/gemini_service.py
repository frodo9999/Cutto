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


async def analyze_viral_video_stream(video_gcs_uri: str) -> AsyncGenerator[dict, None]:
    """
    Step 1: Analyze video with Gemini Pro (text only), 6 FPS sampling.
    Step 2: Calculate keyframe timestamps from scene durations.
    """
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
      "transition_out": "cut",
      "continuous_with_next": false,
      "continuity_note": "one sentence explaining why this scene is or is not continuous with the next"
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

For continuous_with_next, watch the transition between THIS scene and the NEXT scene carefully, then apply this decision tree:

Set true if ANY of these conditions are met:
- The SAME physical object appears in both scenes and is being interacted with across the cut
- A single continuous physical action is split across two scenes
- The same person/hand continues an uninterrupted motion across the cut
- The same product is being revealed progressively across consecutive scenes
- The camera angle changes but the subject and action are in direct physical continuity

Set false if ANY of these conditions are met:
- The next scene introduces a completely different object, person, or location
- There is a clear time jump between scenes
- The next scene is a reaction shot, text overlay, or b-roll cutaway
- The scenes share a theme but different physical moments
- You are unsure — default to false

IMPORTANT: Look ahead at the next scene before deciding. Last scene is always false.

Be specific and actionable. The visual_prompt must be detailed enough for Veo to generate without additional context."""

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part(
                    file_data=types.FileData(
                        file_uri=video_gcs_uri,
                        mime_type="video/mp4",
                    ),
                    video_metadata=types.VideoMetadata(fps=6),
                ),
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

    # Calculate keyframe timestamps from scene durations
    if analysis_data and analysis_data.get("storyboard"):
        storyboard = analysis_data["storyboard"]
        timestamps = []
        cursor = 0.0
        for scene in storyboard:
            duration = float(scene.get("duration", 2))
            timestamps.append(round(cursor + duration / 2, 2))
            cursor += duration
        yield {
            "type": "keyframe_timestamps",
            "timestamps": timestamps,
            "scene_count": len(storyboard),
        }
        print(f"[Keyframe] Timestamps to extract: {timestamps}")

    yield {"type": "done"}


async def generate_director_script(
    analysis: AnalysisResult,
    brand_description: str,
    style_adjustments: str,
) -> list[dict]:
    """
    Generate a director script for the new brand video.
    Combines the viral formula from original video analysis with brand identity.
    Each scene includes description, veo_prompt, and cut_requirement.
    """
    storyboard_summary = ""
    for s in analysis.storyboard:
        storyboard_summary += f"\n  Scene {s['scene']} ({s.get('duration', 2)}s): {s.get('description', '')}"

    prompt = f"""You are a creative director and viral video strategist.

You have analyzed a viral video and extracted its formula:
- Hook strategy: {analysis.hook_strategy}
- Pacing: {analysis.pacing}
- Visual style: {analysis.visual_style}
- Audio energy: {analysis.audio_style}
- Viral factors: {', '.join(analysis.viral_factors) if analysis.viral_factors else 'n/a'}

Original video storyboard (for reference — reuse this structure and pacing):
{storyboard_summary}

Brand information:
{brand_description}

Style adjustments requested:
{style_adjustments if style_adjustments else 'None'}

YOUR TASK:
Create a NEW director script for a brand video that:
1. Replicates the viral formula (same pacing, shot types, editing rhythm, visual energy)
2. Features the brand's actual products and aesthetic naturally
3. Has the same number of scenes as the original storyboard
4. Keeps the same scene durations as the original

CRITICAL RULES:
- Physical actions and shot structure must make sense for THIS brand's products
- Do NOT force product types that don't match the brand
- Each scene must flow logically from the previous
- cut_requirement must describe EXACTLY what action starts and ends the clip

CONTINUOUS SCENE GROUPS:
Identify which consecutive scenes form a single continuous action sequence
(e.g. "open box → take out pouch → unzip pouch" is one continuous sequence).
Assign the same continuous_group_id (integer starting from 1) to scenes in the same group.
Independent scenes get their own unique group_id.

For scenes in the same continuous group, the veo_prompt MUST:
- Start with a transition phrase referencing the previous scene's ending action
  (e.g. "Continuing from the previous shot, as the box lid falls open, hands then...")
- Describe ONLY what happens in THIS scene, not the full sequence
- Use identical vocabulary for shared objects across all scenes in the group
  (e.g. always "blush-pink velvet pouch with gold drawstrings" — never vary this)

PHYSICAL REALISM RULES (apply to ALL brands and product types):
These rules prevent the most common AI video generation artifacts by enforcing 
physical causality in every prompt.

RULE 1 — DESCRIBE THE INITIAL FRAME STATE FIRST:
Every veo_prompt MUST begin by describing the exact static state of the first frame —
what objects are already present, where they are positioned, and what the hands/subject 
are doing at the START — before describing any action.

GOOD: "A white ceramic mug already sits on the wooden table, steam rising from it. 
A hand enters from the left, wraps around the handle, and lifts it..."
BAD: "A hand picks up a mug from the table..." 
(Veo will invent how the mug got there and how the hand arrived)

RULE 2 — OBJECTS MUST ALREADY EXIST IN THE FRAME:
Never describe an object appearing, materializing, or being revealed unless the 
physical mechanism (opening a container, unfolding a cloth) is explicitly described 
step by step. Objects that are inside containers must be stated as visible from 
frame one if the scene begins after the container is opened.

GOOD: "The open box already shows the product resting inside. A hand reaches in..."
BAD: "The box opens to reveal the product..." (Veo will generate a fantasy reveal)

RULE 3 — DESCRIBE COMPLETE PHYSICAL CAUSALITY FOR EVERY ACTION:
Every action must include: the agent (which hand/body part), the starting position, 
the path of movement, and the end state. Never skip steps.

GOOD: "The right hand, already holding the bottle by its cap, tilts it at 45 degrees 
over the glass, and liquid pours in a steady stream downward into the glass below."
BAD: "Liquid is poured into the glass." (who is pouring? from where? what angle?)

RULE 4 — CONTACT AND ATTACHMENT MUST BE PHYSICALLY DESCRIBED:
When an object is placed on, attached to, or put onto a surface or body part, 
describe the precise physical mechanism: which fingers hold it, from which direction 
it approaches, and how it makes contact.

GOOD: "Both hands hold the bracelet taut by its two ends. The left hand positions 
the clasp side against the inside of the right wrist, while the right hand 
feeds the other end around and clicks the clasp shut."
BAD: "The bracelet is fastened around the wrist." (Veo will animate it wrapping itself)

RULE 5 — NO TELEPORTATION OR JUMP CUTS WITHIN A CLIP:
If an object changes location between the start and end of a scene, describe every 
physical step of that transition. Objects cannot skip from one location to another.

GOOD: "The hand lifts the card from the table, carries it across frame, 
and places it down on the right side next to the product."
BAD: "The card moves from the left to the right side." (too abstract — Veo will jump cut)

Return ONLY a valid JSON array:
[
  {{
    "scene": 1,
    "duration": <same as original>,
    "description": "what happens — brand-specific, action-focused, user-readable",
    "veo_prompt": "5-7 sentence hyper-specific Veo generation prompt.",
    "cut_requirement": "Find the moment when [specific action] begins and cut when [specific action] completes.",
    "continuous_group_id": 1
  }}
]

No markdown, no explanation, just the JSON array."""

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.6),
    )

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    json_start = text.find("[")
    json_end = text.rfind("]") + 1
    scenes = json.loads(text[json_start:json_end])
    print(f"[Director] Generated script with {len(scenes)} scenes")
    return scenes


async def generate_veo_prompts(director_scenes: list[dict]) -> list[str]:
    """Extract veo_prompts from the director script."""
    return [scene["veo_prompt"] for scene in director_scenes]


async def find_best_cut(
    clip_gcs_uri: str,
    scene: dict,
    target_duration: float,
) -> tuple[float, float]:
    """
    Use Gemini video understanding to find the best cut points within an 8s clip.
    Uses cut_requirement from the director script to guide the decision.
    Returns (start_seconds, end_seconds).
    """
    cut_requirement = scene.get('cut_requirement', '')
    description = scene.get('description', '')

    prompt = f"""You are a professional video editor reviewing a raw video clip for a brand video.

Scene: {description}
Target duration: {target_duration:.1f} seconds
Cut requirement: {cut_requirement}

Find the {target_duration:.1f}-second window that best satisfies the cut requirement.
The cut requirement defines exactly what action to start and end on — follow it precisely.
If the clip does not contain the exact action, find the closest matching moment.
Avoid AI artifacts, distortions, or unstable frames at cut points.

The clip is 8 seconds long. Return ONLY a JSON object:
{{
  "start": <float, seconds from beginning>,
  "end": <float, seconds from beginning>,
  "reason": "<describe what you actually see at this window and how it satisfies the cut requirement>"
}}

Constraints:
- end - start must equal exactly {target_duration:.1f} seconds
- start >= 0.0
- end <= 8.0"""

    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            file_data=types.FileData(
                                file_uri=clip_gcs_uri,
                                mime_type="video/mp4",
                            ),
                            video_metadata=types.VideoMetadata(fps=8),
                        ),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
            config=types.GenerateContentConfig(temperature=0.2),
        )

        text = response.text.strip()
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

        start = max(0.0, min(start, 8.0 - target_duration))
        end = start + target_duration
        end = min(end, 8.0)

        print(f"[Gemini] Best cut: {start:.2f}s → {end:.2f}s | {reason}")
        return start, end

    except Exception as e:
        print(f"[Gemini] find_best_cut failed ({e}), using start=0")
        return 0.0, min(target_duration, 8.0)


async def find_scene_cuts(
    clip_gcs_uri: str,
    scenes: list[dict],
) -> list[tuple[float, float]]:
    """
    Analyze a single long clip and find cut points for multiple consecutive scenes.
    Used when a continuous group of scenes was generated as one long video.
    Returns list of (start, end) tuples, one per scene.
    """
    total_duration = sum(float(s["duration"]) for s in scenes)
    scenes_desc = "\n".join([
        f"Scene {s['scene']} ({s['duration']}s): {s['cut_requirement']}"
        for s in scenes
    ])

    prompt = f"""You are a professional video editor analyzing a long video clip that contains {len(scenes)} consecutive scenes.

The clip contains these scenes in order:
{scenes_desc}

Total expected duration: {total_duration:.1f} seconds
The clip may be longer than this — only use the portion that contains the actual content.

Find the exact start and end time for each scene based on its cut_requirement.
The scenes are in chronological order — they happen one after another in the clip.

Return ONLY a valid JSON array with one object per scene:
[
  {{
    "scene": <scene number>,
    "start": <float, seconds from clip beginning>,
    "end": <float, seconds from clip beginning>,
    "reason": "<what you see at this cut point>"
  }}
]

Rules:
- Scene N's end time must be <= Scene N+1's start time
- Each duration (end-start) must equal the scene's target duration exactly
- start >= 0.0
- Avoid AI artifacts or unstable frames at cut points"""

    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            file_data=types.FileData(
                                file_uri=clip_gcs_uri,
                                mime_type="video/mp4",
                            ),
                            video_metadata=types.VideoMetadata(fps=8),
                        ),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
            config=types.GenerateContentConfig(temperature=0.2),
        )

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        json_start = text.find("[")
        json_end = text.rfind("]") + 1
        results = json.loads(text[json_start:json_end])

        cut_points = []
        for i, (scene, result) in enumerate(zip(scenes, results)):
            start = float(result.get("start", 0.0))
            duration = float(scene["duration"])
            end = start + duration
            reason = result.get("reason", "")
            print(f"[Gemini] Scene {scene['scene']} cut: {start:.2f}s → {end:.2f}s | {reason}")
            cut_points.append((start, end))

        return cut_points

    except Exception as e:
        print(f"[Gemini] find_scene_cuts failed ({e}), using sequential fallback")
        # Fallback: sequential cuts starting from 0
        cut_points = []
        cursor = 0.0
        for scene in scenes:
            duration = float(scene["duration"])
            cut_points.append((cursor, cursor + duration))
            cursor += duration
        return cut_points

async def generate_storyboard_image(veo_prompt: str, scene_num: int) -> str | None:
    """
    Generate a single storyboard concept image for a director script scene.
    Uses gemini-3.1-flash-image-preview for interleaved image output.
    Returns base64 data URL or None on failure.
    """
    IMAGE_MODEL = "gemini-3.1-flash-image-preview"

    prompt = f"""You are a storyboard artist. Create a single cinematic storyboard frame for this scene.

Scene {scene_num} visual brief:
{veo_prompt}

Generate a photorealistic storyboard illustration that captures the key visual moment of this scene.
The image should feel like a professional film storyboard or mood board frame."""

    try:
        response = await client.aio.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                temperature=0.7,
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                import base64
                b64 = base64.b64encode(part.inline_data.data).decode("utf-8")
                return f"data:{part.inline_data.mime_type};base64,{b64}"

        return None
    except Exception as e:
        print(f"[Gemini] Storyboard image generation failed for scene {scene_num}: {e}")
        return None