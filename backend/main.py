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
    """Safely encode SSE event, escaping content that could break SSE framing."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

load_dotenv()

from models.schemas import JobStatus, GenerationRequest, AnalysisResult
from services import gemini_service, veo_service, ffmpeg_service, storage_service

# In-memory job store (use Redis in production)
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
    """
    Upload a viral video and stream back Gemini's analysis with interleaved output.
    Returns a streaming response with text chunks and storyboard images.
    """
    # Upload viral video to GCS
    video_bytes = await viral_video.read()
    gcs_uri, job_id = await storage_service.upload_file(
        video_bytes, viral_video.filename, viral_video.content_type or "video/mp4"
    )

    # Initialize job
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
        storyboard_images = []

        async for event in gemini_service.analyze_viral_video_stream(gcs_uri):
            if event["type"] == "text_chunk":
                yield sse_event(event)
            elif event["type"] == "storyboard_image":
                storyboard_images.append(event["content"])
                # 不通过SSE发送图片，存到job里
                yield sse_event({"type": "storyboard_image_ready", "index": len(storyboard_images) - 1})
            elif event["type"] == "analysis_complete":
                analysis_data = event["content"]
                yield sse_event(event)
            elif event["type"] == "error":
                yield sse_event(event)

        # Save analysis to job
        if analysis_data:
            jobs[job_id] = JobStatus(
                job_id=job_id,
                status="analyzed",
                progress=40,
                message="Analysis complete! Ready to generate your video.",
                analysis=AnalysisResult(**analysis_data),
                storyboard_images=storyboard_images,
            )
        yield f"data: {json.dumps({'type': 'done', 'job_id': job_id})}\n\n"

    return StreamingResponse(
        stream_analysis(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/generate/{job_id}")
async def generate_video(
    job_id: str,
    custom_assets_description: str = Form(default=""),
    user_requirements: str = Form(default=""),
    custom_asset: UploadFile = File(default=None),
):
    """
    Generate the final video based on analysis + user customization.
    Runs Veo generation + FFmpeg compositing as a background task.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if not job.analysis:
        raise HTTPException(status_code=400, detail="Analysis not complete")

    # Upload custom asset if provided
    custom_asset_uri = None
    if custom_asset:
        asset_bytes = await custom_asset.read()
        custom_asset_uri, _ = await storage_service.upload_file(
            asset_bytes, custom_asset.filename, custom_asset.content_type or "video/mp4"
        )

    # Start background generation
    asyncio.create_task(
        _run_generation(job_id, job.analysis, custom_assets_description, user_requirements, custom_asset_uri)
    )

    return {"job_id": job_id, "status": "generating"}


async def _run_generation(
    job_id: str,
    analysis: AnalysisResult,
    custom_assets_description: str,
    user_requirements: str,
    custom_asset_uri: str | None,
):
    """Background task: generate video clips with Veo, then composite with FFmpeg."""
    gcs_bucket = os.getenv("GCS_BUCKET_NAME", "cutto-videos")

    try:
        # Step 1: Generate Veo prompts
        jobs[job_id].status = "generating"
        jobs[job_id].progress = 50
        jobs[job_id].message = "Generating Veo prompts from analysis..."

        veo_prompts = await gemini_service.generate_veo_prompts(
            analysis, custom_assets_description, user_requirements
        )

        scene_durations = [s["duration"] for s in analysis.storyboard]
        # Ensure lengths match
        if len(scene_durations) != len(veo_prompts):
            scene_durations = [5] * len(veo_prompts)

        # Step 2: Generate clips with Veo
        jobs[job_id].progress = 60
        jobs[job_id].message = f"Veo is generating {len(veo_prompts)} video clips..."

        clip_uris = await veo_service.generate_all_clips(
            veo_prompts, scene_durations, gcs_bucket, job_id
        )

        # Step 3: Gemini finds best cut points for each clip
        jobs[job_id].progress = 75
        jobs[job_id].message = "Gemini is finding the best cut points..."

        cut_points = []
        for i, (clip_uri, scene_duration) in enumerate(zip(clip_uris, scene_durations)):
            scene = analysis.storyboard[i] if i < len(analysis.storyboard) else {}
            scene_dict = scene.model_dump() if hasattr(scene, "model_dump") else dict(scene)
            start, end = await gemini_service.find_best_cut(clip_uri, scene_dict, float(scene_duration))
            cut_points.append((start, end))

        # Step 4: Composite with FFmpeg using smart cut points
        jobs[job_id].progress = 85
        jobs[job_id].message = "Compositing final video with FFmpeg..."

        final_uri = await ffmpeg_service.composite_video(
            clip_uris, custom_asset_uri, job_id, gcs_bucket,
            cut_points=cut_points,
        )

        # Step 4: Generate signed URL
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
    """Poll job status for video generation progress."""
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
    # 直接返回 base64 data URL
    return {"image": job.storyboard_images[index]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)