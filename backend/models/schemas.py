from pydantic import BaseModel
from typing import Optional, List


class AnalysisResult(BaseModel):
    hook_strategy: str
    pacing: str
    visual_style: str
    audio_style: str
    caption_style: str
    viral_factors: List[str]
    storyboard: List[dict]  # [{scene, duration, description, visual_prompt, ...}]


class GenerationRequest(BaseModel):
    analysis: AnalysisResult
    custom_assets_description: str
    user_requirements: str
    duration_seconds: int = 30


class DirectorScene(BaseModel):
    scene: int
    duration: float
    description: str        # what happens in this scene
    veo_prompt: str         # detailed Veo generation prompt
    cut_requirement: str    # what find_best_cut should look for
    continuous_group_id: int = 0  # scenes with same id form a continuous group


class JobStatus(BaseModel):
    job_id: str
    status: str  # pending | analyzing | analyzed | director_ready | generating | done | error
    progress: int  # 0-100
    message: str
    result_url: Optional[str] = None
    analysis: Optional[AnalysisResult] = None
    storyboard_images: Optional[List[str]] = None
    director_scenes: Optional[List[DirectorScene]] = None