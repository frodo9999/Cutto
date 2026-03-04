"use client";

import { useState, useRef, useCallback } from "react";
import UploadZone from "@/components/UploadZone";
import AnalysisStream from "@/components/AnalysisStream";
import GeneratePanel from "@/components/GeneratePanel";
import ResultPlayer from "@/components/ResultPlayer";

export type AppStage = "upload" | "analyzing" | "analyzed" | "generating" | "done";

export interface AnalysisData {
  hook_strategy: string;
  pacing: string;
  visual_style: string;
  audio_style: string;
  caption_style: string;
  viral_factors: string[];
  storyboard: Array<{
    scene: number;
    duration: number;
    description: string;
    visual_prompt: string;
    timing_note: string;
  }>;
}

export default function Home() {
  const [stage, setStage] = useState<AppStage>("upload");
  const [jobId, setJobId] = useState<string | null>(null);
  const [analysisText, setAnalysisText] = useState("");
  const [analysisData, setAnalysisData] = useState<AnalysisData | null>(null);
  const [storyboardImages, setStoryboardImages] = useState<string[]>([]);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const currentJobIdRef = useRef<string | null>(null);

  const handleUploadAndAnalyze = useCallback(
    async (viralVideo: File, requirements: string) => {
      setStage("analyzing");
      setAnalysisText("");
      setStoryboardImages([]);
      currentJobIdRef.current = null;

      const formData = new FormData();
      formData.append("viral_video", viralVideo);
      formData.append("user_requirements", requirements);

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/analyze`,
        { method: "POST", body: formData }
      );

      if (!res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));

            if (event.type === "job_id") {
              setJobId(event.content);
              currentJobIdRef.current = event.content;
            } else if (event.type === "text_chunk") {
              setAnalysisText((prev) => prev + event.content.replace(/\\n/g, '\n'));
            } else if (event.type === "storyboard_image_ready") {
              // Fetch image via separate HTTP request to avoid SSE size limits
              const jid = currentJobIdRef.current;
              if (jid) {
                fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/storyboard/${jid}/${event.index}`)
                  .then(r => r.json())
                  .then(data => {
                    console.log(`[Image] Fetched image ${event.index} successfully`);
                    setStoryboardImages((prev) => [...prev, data.image]);
                  })
                  .catch(e => console.error(`[Image] Failed to fetch image ${event.index}:`, e));
              }
            } else if (event.type === "analysis_complete") {
              setAnalysisData(event.content);
            } else if (event.type === "done") {
              setStage("analyzed");
            } else if (event.type === "error") {
              console.error("Analysis error:", event.content);
            }
          } catch (e) {
            console.error("[SSE Parse Error]", e, "Line:", line.slice(0, 100));
          }
        }
      }
    },
    []
  );

  const handleGenerate = useCallback(
    async (customDesc: string, userReqs: string, customAsset?: File) => {
      if (!jobId) return;
      setStage("generating");

      const formData = new FormData();
      formData.append("custom_assets_description", customDesc);
      formData.append("user_requirements", userReqs);
      if (customAsset) formData.append("custom_asset", customAsset);

      await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/generate/${jobId}`,
        { method: "POST", body: formData }
      );

      const poll = setInterval(async () => {
        const statusRes = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/status/${jobId}`
        );
        const status = await statusRes.json();
        if (status.status === "done") {
          clearInterval(poll);
          setResultUrl(status.result_url);
          setStage("done");
        } else if (status.status === "error") {
          clearInterval(poll);
          alert("Generation failed: " + status.message);
          setStage("analyzed");
        }
      }, 3000);
    },
    [jobId]
  );

  return (
    <main className="min-h-screen bg-[#080808] text-white font-mono">
      <header className="border-b border-white/5 px-8 py-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 bg-[#FF3B00] rotate-45" />
          <span className="text-xl font-bold tracking-[0.2em] uppercase">
            Cutto
          </span>
        </div>
        <span className="text-xs text-white/30 tracking-widest uppercase">
          Viral Video Replicator
        </span>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-12">
        {stage === "upload" && (
          <UploadZone onAnalyze={handleUploadAndAnalyze} />
        )}

        {(stage === "analyzing" || stage === "analyzed") && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <AnalysisStream
              text={analysisText}
              storyboardImages={storyboardImages}
              isStreaming={stage === "analyzing"}
            />
            {stage === "analyzed" && analysisData && (
              <GeneratePanel
                analysis={analysisData}
                onGenerate={handleGenerate}
              />
            )}
          </div>
        )}

        {stage === "generating" && jobId && (
          <GeneratingScreen jobId={jobId} />
        )}

        {stage === "done" && resultUrl && (
          <ResultPlayer url={resultUrl} onReset={() => setStage("upload")} />
        )}
      </div>
    </main>
  );
}

function GeneratingScreen({ jobId }: { jobId: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8">
      <div className="relative">
        <div className="w-24 h-24 border border-[#FF3B00]/30 rotate-45 animate-spin"
          style={{ animationDuration: "3s" }} />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-3 h-3 bg-[#FF3B00]" />
        </div>
      </div>
      <div className="text-center">
        <p className="text-lg tracking-widest uppercase text-white/60">Veo is generating your clips</p>
        <p className="text-xs text-white/30 mt-2">This may take 2-5 minutes</p>
      </div>
    </div>
  );
}