from pydantic import BaseModel
from typing import Optional, List

class AnalysisResult(BaseModel):
    hook_strategy: str
    pacing: str
    visual_style: str
    audio_style: str
    caption_style: str
    viral_factors: List[str]
    storyboard: List[dict]  # [{scene, duration, description, visual_prompt}]

class GenerationRequest(BaseModel):
    analysis: AnalysisResult
    custom_assets_description: str
    user_requirements: str
    duration_seconds: int = 30

class JobStatus(BaseModel):
    job_id: str
    status: str  # pending | analyzing | generating | compositing | done | error
    progress: int  # 0-100
    message: str
    result_url: Optional[str] = None
    analysis: Optional[AnalysisResult] = None
    storyboard_images: Optional[List[str]] = None  # base64 images
