import os
import json
import uuid
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

load_dotenv()

from models.schemas import JobStatus, GenerationRequest, AnalysisResult, DirectorScene
from services import gemini_service, veo_service, ffmpeg_service, storage_service

jobs: dict[str, JobStatus] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage_service.ensure_bucket_exists()
    yield


app = FastAPI(title="Cutto API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.run.app", "https://cutto.vercel.app", "https://*.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "project": os.getenv("GOOGLE_CLOUD_PROJECT")}


@app.post("/api/analyze")
async def analyze_video(
    viral_video: UploadFile = File(...),
    user_requirements: str = Form(default=""),
):
    video_bytes = await viral_video.read()
    gcs_uri, job_id = await storage_service.upload_file(
        video_bytes, viral_video.filename, viral_video.content_type or "video/mp4"
    )

    jobs[job_id] = JobStatus(
        job_id=job_id,
        status="analyzing",
        progress=10,
        message="Uploading video to analysis pipeline...",
    )

    async def stream_analysis():
        yield f"data: {json.dumps({'type': 'job_id', 'content': job_id})}\n\n"
        yield f"data: {json.dumps({'type': 'status', 'content': 'Gemini is analyzing your viral video...'})}\n\n"

        analysis_data = None

        async for event in gemini_service.analyze_viral_video_stream(gcs_uri):
            if event["type"] == "text_chunk":
                yield sse_event(event)
            elif event["type"] == "analysis_complete":
                analysis_data = event["content"]
                yield sse_event(event)
            elif event["type"] == "keyframe_timestamps":
                timestamps = event["timestamps"]
                try:
                    frame_urls = await ffmpeg_service.extract_keyframes(
                        gcs_uri, timestamps, job_id,
                        os.getenv("GCS_BUCKET_NAME", "cutto-videos")
                    )
                    for i, url in enumerate(frame_urls):
                        if url:
                            yield sse_event({
                                "type": "storyboard_frame",
                                "index": i,
                                "url": url,
                            })
                except Exception as e:
                    print(f"[Keyframe] Extraction failed: {e}")
            elif event["type"] == "error":
                yield sse_event(event)

        if analysis_data:
            jobs[job_id] = JobStatus(
                job_id=job_id,
                status="analyzed",
                progress=40,
                message="Analysis complete! Ready to generate your video.",
                analysis=AnalysisResult(**analysis_data),
                storyboard_images=[],
            )
        yield f"data: {json.dumps({'type': 'done', 'job_id': job_id})}\n\n"

    return StreamingResponse(
        stream_analysis(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/director/{job_id}")
async def create_director_script(
    job_id: str,
    custom_assets_description: str = Form(default=""),
    user_requirements: str = Form(default=""),
):
    """
    Step 1 of generation: create director script + storyboard images via SSE.
    Streams: script_ready → storyboard_image (one per scene) → done
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    if not job.analysis:
        raise HTTPException(status_code=400, detail="Analysis not complete")

    async def stream_director():
        # Step 1: Generate director script (text)
        director_scenes = await gemini_service.generate_director_script(
            job.analysis, custom_assets_description, user_requirements
        )

        # Save to job
        def parse_duration(v) -> float:
            if isinstance(v, str):
                v = v.lower().replace("s", "").strip()
            return float(v)

        jobs[job_id].director_scenes = [
            DirectorScene(
                scene=s["scene"],
                duration=parse_duration(s["duration"]),
                description=s["description"],
                veo_prompt=s["veo_prompt"],
                cut_requirement=s["cut_requirement"],
                continuous_group_id=s.get("continuous_group_id", idx + 100),
            )
            for idx, s in enumerate(director_scenes)
        ]
        jobs[job_id].status = "director_ready"
        jobs[job_id].message = "Director script ready for review."

        # Stream script to frontend
        yield sse_event({
            "type": "script_ready",
            "scenes": [
                {
                    "scene": s["scene"],
                    "duration": s["duration"],
                    "description": s["description"],
                    "veo_prompt": s.get("veo_prompt", ""),
                }
                for s in director_scenes
            ]
        })

        # Step 2: Generate storyboard images in parallel (interleaved output)
        async def gen_image(s, idx):
            img = await gemini_service.generate_storyboard_image(
                s.get("veo_prompt", s.get("description", "")), s["scene"]
            )
            return idx, img

        tasks = [gen_image(s, i) for i, s in enumerate(director_scenes)]
        for coro in asyncio.as_completed(tasks):
            idx, img = await coro
            if img:
                yield sse_event({
                    "type": "director_frame",
                    "index": idx,
                    "image": img,
                })

        yield sse_event({"type": "done", "job_id": job_id})

    return StreamingResponse(
        stream_director(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/generate/{job_id}")
async def generate_video(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if not job.analysis:
        raise HTTPException(status_code=400, detail="Analysis not complete")
    if not job.director_scenes:
        raise HTTPException(status_code=400, detail="Director script not found. Call /api/director first.")

    asyncio.create_task(
        _run_generation(job_id, job.analysis, None)
    )

    return {"job_id": job_id, "status": "generating"}


async def _run_generation(
    job_id: str,
    analysis: AnalysisResult,
    custom_asset_uri: str | None,
):
    gcs_bucket = os.getenv("GCS_BUCKET_NAME", "cutto-videos")

    try:
        # Step 1: Load director script
        jobs[job_id].status = "generating"
        jobs[job_id].progress = 50
        jobs[job_id].message = "Starting video generation..."

        director_scenes = [
            s.model_dump() if hasattr(s, "model_dump") else dict(s)
            for s in jobs[job_id].director_scenes
        ]

        veo_prompts = await gemini_service.generate_veo_prompts(director_scenes)

        scene_durations = [float(s["duration"]) for s in director_scenes]
        if len(scene_durations) != len(veo_prompts):
            scene_durations = [2.0] * len(veo_prompts)

        # Step 2: Group scenes by continuous_group_id and generate clips
        jobs[job_id].progress = 60
        jobs[job_id].message = f"Veo is generating video clips..."

        # Build groups: {group_id: [scene_indices]}
        from collections import defaultdict
        groups = defaultdict(list)
        for i, scene in enumerate(director_scenes):
            gid = scene.get("continuous_group_id", i + 100)  # unique id for independent scenes
            groups[gid].append(i)

        # clip_uris[i] = GCS URI of the clip for scene i
        # group_clip_map[i] = (clip_uri, is_group) — group clips shared by multiple scenes
        clip_uris = [None] * len(director_scenes)
        cut_points = [None] * len(director_scenes)

        # Step 2a: Generate clips per group
        for gid, scene_indices in sorted(groups.items()):
            group_prompts = [veo_prompts[i] for i in scene_indices]

            if len(scene_indices) == 1:
                # Independent scene — generate normally
                i = scene_indices[0]
                output_uri = f"gs://{gcs_bucket}/jobs/{job_id}/clips/scene_{i:02d}.mp4"
                print(f"[Veo] Scene {i+1}: generating independently...")
                uri = await veo_service.generate_video_clip(group_prompts[0], 8, output_uri)
                clip_uris[i] = uri
            else:
                # Continuous group — generate one long clip
                print(f"[Veo] Group {gid}: generating continuous clip for scenes {[i+1 for i in scene_indices]}...")
                long_uri = await veo_service.generate_continuous_group_clip(
                    group_prompts, gcs_bucket, job_id, gid
                )
                # All scenes in this group share the same long clip
                for i in scene_indices:
                    clip_uris[i] = long_uri

        print(f"[DEBUG] clip_uris ({len(clip_uris)} entries):")
        for i, uri in enumerate(clip_uris):
            print(f"  [{i}] {uri}")

        # Step 3: Find cut points per group
        jobs[job_id].progress = 75
        jobs[job_id].message = "Gemini is finding the best cut points..."

        for gid, scene_indices in sorted(groups.items()):
            if len(scene_indices) == 1:
                # Single scene — use find_best_cut
                i = scene_indices[0]
                scene_dict = director_scenes[i]
                start, end = await gemini_service.find_best_cut(
                    clip_uris[i], scene_dict, float(scene_durations[i])
                )
                cut_points[i] = (start, end)
            else:
                # Continuous group — use find_scene_cuts on the shared long clip
                group_scenes = [director_scenes[i] for i in scene_indices]
                group_cuts = await gemini_service.find_scene_cuts(
                    clip_uris[scene_indices[0]], group_scenes
                )
                for i, (start, end) in zip(scene_indices, group_cuts):
                    cut_points[i] = (start, end)

        # Step 4: Composite with FFmpeg
        jobs[job_id].progress = 85
        jobs[job_id].message = "Compositing final video with FFmpeg..."

        # Transition types from original analysis
        transitions = []
        for scene in analysis.storyboard:
            scene_dict = scene.model_dump() if hasattr(scene, "model_dump") else dict(scene)
            transitions.append(scene_dict.get("transition_out", "cut"))
        transitions = transitions[:len(clip_uris) - 1]

        final_uri = await ffmpeg_service.composite_video(
            clip_uris, custom_asset_uri, job_id, gcs_bucket,
            cut_points=cut_points,
            transitions=transitions,
        )

        signed_url = await ffmpeg_service.generate_signed_url(final_uri)

        jobs[job_id].status = "done"
        jobs[job_id].progress = 100
        jobs[job_id].message = "Your video is ready!"
        jobs[job_id].result_url = signed_url

    except Exception as e:
        jobs[job_id].status = "error"
        jobs[job_id].message = f"Error: {str(e)}"


@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str) -> JobStatus:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.get("/api/storyboard/{job_id}/{index}")
async def get_storyboard_image(job_id: str, index: int):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    if not job.storyboard_images or index >= len(job.storyboard_images):
        raise HTTPException(status_code=404, detail="Image not found")
    return {"image": job.storyboard_images[index]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)