# Cutto ✂️
**Viral Video Replicator** — Upload any viral video, get a version made for your brand.

Built for the Gemini Live Agent Challenge Hackathon.

## Architecture
```
Frontend (Next.js) → FastAPI Backend (Cloud Run)
                           ↓
                  Gemini 3.1 Pro (Video Analysis + Interleaved Output)
                           ↓
                  Veo 3.1 (Video Generation via Vertex AI)
                           ↓
                  FFmpeg (Compositing)
                           ↓
                  Cloud Storage (Output)
```

## Local Development

### Prerequisites
- Python 3.10+
- Node.js 18+
- FFmpeg
- Google Cloud CLI (authenticated)

### Backend
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your GCP project details

uvicorn main:app --reload --port 8080
```

### Frontend
```bash
cd frontend
npm install
# Edit .env.local if needed
npm run dev
```

Open http://localhost:3000

## Deploy to Google Cloud

### Backend (Cloud Run)
```bash
cd backend
gcloud run deploy cutto-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=cutto-hackathon,GCS_BUCKET_NAME=cutto-videos
```

### Frontend (Cloud Run or Vercel)
```bash
cd frontend
# Set NEXT_PUBLIC_API_URL to your Cloud Run backend URL
vercel deploy
```

## Tech Stack
- **Gemini 3.1 Pro Preview** — Multimodal video analysis with interleaved text + image output
- **Veo 3.1** — AI video generation via Vertex AI
- **FFmpeg** — Video compositing and transitions
- **Google Cloud Storage** — Asset and output storage
- **Cloud Run** — Serverless backend deployment
- **FastAPI** — Backend API
- **Next.js** — Frontend
