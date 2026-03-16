# Cutto — Viral Video Replicator

> Built for the **Gemini Live Agent Challenge** · Category: Creative Storyteller

Cutto analyzes any viral video and generates a brand-new version featuring your products — in the same visual style, pacing, and energy. It uses Gemini's multimodal capabilities to understand what makes a video go viral, then recreates that formula for your brand using Veo 3.1.

**Live demo:** https://cutto.vercel.app  
**Backend:** https://cutto-backend-846822745809.us-central1.run.app

---

## How it works

**1. Upload a viral video**  
Cutto accepts any short-form video (TikTok, Reels, etc.) and uploads it to Google Cloud Storage.

**2. Gemini analyzes the viral formula**  
Gemini 3.1 Pro watches the video at 6 FPS and extracts: hook strategy, pacing, visual style, audio energy, scene-by-scene storyboard with continuity flags, and transition types. Results stream back in real time via SSE.

**3. Browse the original storyboard**  
Extracted keyframes from the original video are displayed in a 3D film-strip carousel. Each frame is synced with Gemini's scene analysis.

**4. Create your Director Script**  
Enter your brand description and style requirements. Gemini generates a complete director script that replicates the viral formula — adapted for your products. At the same time, `gemini-3.1-flash-image-preview` generates a concept image for each scene using **interleaved text + image output**, streamed back as they arrive and displayed in the same film carousel.

**5. Generate with Veo 3.1**  
Consecutive scenes are grouped by continuity and generated as long clips using Veo Scene Extension — preserving visual consistency across related shots. Each clip is 8 seconds, extended for continuous sequences.

**6. Smart editing**  
Gemini watches each generated clip at 8 FPS and finds the best cut point based on the director script's cut requirements. FFmpeg composites the clips with per-scene transitions into the final video.

---

## Architecture

```
Frontend (Next.js · Vercel)
    │
    ├── POST /api/analyze ──────► Gemini 3.1 Pro (video analysis, 6 FPS)
    │        SSE stream ◄──────── text_chunk → analysis_complete → keyframe_timestamps → storyboard_frame
    │
    ├── POST /api/director ─────► Gemini 3.1 Pro (director script)
    │        SSE stream ◄──────── script_ready → director_frame (interleaved image output)
    │                             gemini-3.1-flash-image-preview per scene
    │
    ├── POST /api/generate ─────► Background task (Cloud Run)
    │                             ├── Veo 3.1 Fast (8s clips + Scene Extension)
    │                             ├── Gemini 3.1 Pro (find_best_cut, 8 FPS)
    │                             └── FFmpeg (cut · composite · transitions)
    │
    └── GET /api/status ────────► Poll every 4s → result URL (GCS signed URL)

Google Cloud:
    Cloud Run   — FastAPI backend
    Cloud Storage (gs://cutto-videos) — video assets, clips, keyframes
    Vertex AI   — Gemini + Veo model endpoints
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, Tailwind CSS v4, TypeScript |
| Backend | Python 3.13, FastAPI, Cloud Run |
| AI — Analysis | Gemini 3.1 Pro (`gemini-3.1-pro-preview`) |
| AI — Image gen | Gemini Flash Image (`gemini-3.1-flash-image-preview`) |
| AI — Video gen | Veo 3.1 Fast (`veo-3.1-fast-generate-preview`) |
| Storage | Google Cloud Storage |
| Compute | Google Cloud Run (2Gi RAM, 3600s timeout) |
| SDK | `google-genai` >= 1.65.0 |

---

## Hackathon requirements

| Requirement | How Cutto meets it |
|-------------|-------------------|
| Gemini model | Gemini 3.1 Pro for analysis, director script, and cut-finding |
| Gen AI SDK | `google-genai` throughout |
| Google Cloud service | Cloud Run + Cloud Storage + Vertex AI |
| Creative Storyteller | Interleaved text + image output in `/api/director` — Gemini streams scene descriptions and concept images in a single response |
| Hosted on Google Cloud | Backend deployed to Cloud Run (us-central1) |

---

## Local development

### Prerequisites

- Python 3.13+
- Node.js 18+
- Google Cloud project with Vertex AI and Cloud Storage APIs enabled
- Authenticated with `gcloud auth application-default login`

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env
cp .env.example .env
# Fill in: GOOGLE_CLOUD_PROJECT, GCS_BUCKET_NAME

uvicorn main:app --reload --port 8080
```

### Frontend

```bash
cd frontend
npm install

# Create .env.local
echo "NEXT_PUBLIC_API_URL=http://localhost:8080" > .env.local

npm run dev
```

Open http://localhost:3000

---

## Deployment

### Backend (Cloud Run)

```bash
cd backend
gcloud run deploy cutto-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 3600 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=cutto-hackathon,GOOGLE_CLOUD_LOCATION=global,VEO_LOCATION=us-central1,GCS_BUCKET_NAME=cutto-videos,GEMINI_MODEL=gemini-3.1-pro-preview,VEO_MODEL=veo-3.1-fast-generate-preview
```

### Frontend (Vercel)

```bash
cd frontend
vercel --prod
```

---

## Project structure

```
cutto/
├── backend/
│   ├── main.py                  # FastAPI app, SSE endpoints
│   ├── requirements.txt
│   ├── .gcloudignore            # Excludes venv/ from Cloud Run source upload
│   ├── models/
│   │   └── schemas.py           # Pydantic models
│   └── services/
│       ├── gemini_service.py    # Analysis, director script, cut-finding, image gen
│       ├── veo_service.py       # Clip generation + Scene Extension
│       ├── ffmpeg_service.py    # Keyframe extraction, compositing
│       └── storage_service.py  # GCS upload/download
└── frontend/
    ├── app/
    │   ├── page.tsx             # App shell, step navigation
    │   ├── layout.tsx
    │   └── globals.css          # Glassmorphism design system
    └── components/
        ├── UploadZone.tsx       # Video upload with preview
        ├── AnalysisStream.tsx   # Film carousel, brand panel, SSE handling
        └── ResultPlayer.tsx     # Final video playback
```

---

## Key design decisions

**Continuous scene groups** — Instead of generating each scene independently, Cutto identifies sequences of physically connected actions (e.g. "open box → take out ring → put on finger") and generates them as a single long video using Veo Scene Extension. Gemini then finds each scene's cut point within this long clip — ensuring visual consistency across related shots.

**Interleaved output** — The `/api/director` endpoint uses `gemini-3.1-flash-image-preview` to generate storyboard concept images in parallel with the text director script, streaming both back as a mixed SSE stream. This is the Creative Storyteller's core interleaved output capability.

**Physical realism prompting** — The director script prompt enforces physical causality rules: every veo_prompt must describe the initial frame state, complete physical causality for every action, and explicit contact mechanics. This reduces common Veo artifacts like objects materializing from nothing or attaching themselves without hands.

**FFmpeg re-encode** — All clip concatenation uses libx264 re-encode rather than `-c copy` to ensure frame-accurate cuts. Using `-c copy` caused clips to silently drop when keyframe boundaries didn't align.

---

*Created for the Gemini Live Agent Challenge hackathon. #GeminiLiveAgentChallenge*
