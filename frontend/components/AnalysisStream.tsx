"use client";

import { useEffect, useRef, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://cutto-backend-846822745809.us-central1.run.app";

interface Props {
  videoFile: File;
  onResult: (url: string, jobId: string) => void;
}

interface Analysis {
  hook?: string;
  pacing?: string;
  visual_style?: string;
  audio?: string;
  storyboard?: { scene: number; description: string; duration: number }[];
}

type GenStep = "prompts" | "veo" | "ffmpeg" | "done";

const GEN_STEPS: { key: GenStep; label: string }[] = [
  { key: "prompts", label: "Generating Veo prompts" },
  { key: "veo",     label: "Generating video clips with Veo 3.1" },
  { key: "ffmpeg",  label: "Compositing with FFmpeg" },
  { key: "done",    label: "Done" },
];

export default function AnalysisStream({ videoFile, onResult }: Props) {
  // Analysis state
  const [logs, setLogs] = useState<string[]>([]);
  const [analysis, setAnalysis] = useState<Analysis>({});
  const [storyboardImgs, setStoryboardImgs] = useState<(string | null)[]>([]);
  const [jobId, setJobId] = useState("");
  const [analysisDone, setAnalysisDone] = useState(false);

  // Brand form state
  const [brandDesc, setBrandDesc] = useState("");
  const [styleAdj, setStyleAdj] = useState("");

  // Generation state
  const [generating, setGenerating] = useState(false);
  const [genStep, setGenStep] = useState<GenStep | null>(null);
  const [genError, setGenError] = useState("");

  const logRef = useRef<HTMLDivElement>(null);

  // ── Run SSE analysis on mount ──
  useEffect(() => {
    const formData = new FormData();
    formData.append("viral_video", videoFile);

    const ctrl = new AbortController();

    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/analyze`, {
          method: "POST", body: formData, signal: ctrl.signal,
        });
        if (!res.body) return;

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw || raw === "[DONE]") continue;
            try {
              const evt = JSON.parse(raw);
              handleEvent(evt);
            } catch {/* ignore parse errors */}
          }
        }
        setAnalysisDone(true);
      } catch (err: unknown) {
        if ((err as Error).name !== "AbortError") {
          setLogs((l) => [...l, "Error: " + (err as Error).message]);
        }
      }
    })();

    return () => ctrl.abort();
  }, [videoFile]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  function handleEvent(evt: Record<string, unknown>) {
    const type = evt.type as string;

    // backend uses "content" field for payloads, not named fields
    if (type === "job_id") {
      const id = (evt.content ?? evt.job_id) as string;
      setJobId(id);
    } else if (type === "text_chunk") {
      const text = ((evt.content ?? evt.text) as string) ?? "";
      setLogs((l) => [...l, text]);
    } else if (type === "analysis_complete") {
      const data = (evt.content ?? evt.analysis) as Analysis;
      setAnalysis(data);
      const count = data.storyboard?.length ?? 0;
      if (count > 0) setStoryboardImgs(Array(count).fill(null));
    } else if (type === "storyboard_image_ready") {
      // backend: { type: "storyboard_image_ready", index: N }
      const idx = evt.index as number;
      setJobId((currentId) => {
        if (currentId) fetchStoryboardImage(currentId, idx);
        return currentId;
      });
    } else if (type === "done") {
      const id = (evt.job_id ?? evt.content) as string;
      if (id) setJobId(id);
    } else if (type === "error") {
      const msg = ((evt.content ?? evt.message) as string) ?? "Unknown error";
      setLogs((l) => [...l, "⚠ " + msg]);
    }
  }

  async function fetchStoryboardImage(id: string, idx: number) {
    try {
      const res = await fetch(`${API_BASE}/api/storyboard/${id}/${idx}`);
      if (!res.ok) return;
      // backend returns { image: "data:image/...;base64,..." }
      const data = await res.json();
      const src = data.image as string;
      if (!src) return;
      setStoryboardImgs((prev) => {
        const next = [...prev];
        next[idx] = src;
        return next;
      });
    } catch {/* ignore */}
  }

  // ── Generate ──
  async function handleGenerate() {
    if (!brandDesc.trim() || !jobId) return;
    setGenerating(true);
    setGenError("");
    setGenStep("prompts");

    try {
      // POST /api/generate/{job_id} with form data
      const form = new FormData();
      form.append("custom_assets_description", brandDesc);
      form.append("user_requirements", styleAdj);

      const res = await fetch(`${API_BASE}/api/generate/${jobId}`, {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Generation failed");

      // Poll /api/status/{job_id} until done
      setGenStep("veo");
      await pollStatus();
    } catch (err: unknown) {
      setGenError((err as Error).message);
      setGenerating(false);
      setGenStep(null);
    }
  }

  async function pollStatus() {
    const INTERVAL = 4000;
    const MAX_WAIT = 8 * 60 * 1000; // 8 min
    const start = Date.now();

    while (Date.now() - start < MAX_WAIT) {
      await new Promise((r) => setTimeout(r, INTERVAL));
      try {
        const res = await fetch(`${API_BASE}/api/status/${jobId}`);
        if (!res.ok) continue;
        const status = await res.json();

        if (status.progress >= 85) setGenStep("ffmpeg");
        else if (status.progress >= 60) setGenStep("veo");

        if (status.status === "done" && status.result_url) {
          setGenStep("done");
          onResult(status.result_url, jobId);
          return;
        }
        if (status.status === "error") {
          throw new Error(status.message ?? "Generation failed");
        }
      } catch (err: unknown) {
        if ((err as Error).message !== "Generation failed") continue;
        throw err;
      }
    }
    throw new Error("Generation timed out");
  }

  // ── Generating overlay ──
  if (generating) {
    return (
      <div className="fade-in" style={{
        maxWidth: 440, margin: "60px auto", padding: "0 20px",
        display: "flex", flexDirection: "column", alignItems: "center", gap: 32,
      }}>
        <div className="glass-card" style={{ width: "100%", padding: 36, textAlign: "center" }}>
          <div className="spinner-ring" style={{ margin: "0 auto 24px" }} />
          <h2 style={{ fontFamily: "var(--font-syne)", fontWeight: 700, fontSize: 18, color: "#f3f0ff", marginBottom: 8 }}>
            Generating your video
          </h2>
          <p style={{ fontSize: 12, color: "rgba(196,181,253,0.6)", marginBottom: 28 }}>
            This usually takes 2–4 minutes
          </p>

          {/* Step checklist */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10, textAlign: "left" }}>
            {GEN_STEPS.filter((s) => s.key !== "done").map((s) => {
              const idx = GEN_STEPS.findIndex((x) => x.key === s.key);
              const activeIdx = GEN_STEPS.findIndex((x) => x.key === genStep);
              const isDone = idx < activeIdx;
              const isActive = s.key === genStep;
              return (
                <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{
                    width: 20, height: 20, borderRadius: "50%", flexShrink: 0,
                    border: `1.5px solid ${isDone ? "#a78bfa" : isActive ? "#a78bfa" : "rgba(167,139,250,0.2)"}`,
                    background: isDone ? "#a78bfa" : "transparent",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 9, color: isDone ? "#1e0a3c" : "transparent",
                  }}>
                    {isDone ? "✓" : isActive ? <span className="dot-live" style={{ width: 6, height: 6 }} /> : ""}
                  </div>
                  <span style={{
                    fontSize: 12,
                    color: isDone ? "rgba(196,181,253,0.7)" : isActive ? "#e9d5ff" : "rgba(196,181,253,0.35)",
                  }}>
                    {s.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // ── Main analysis UI ──
  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "0 20px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>

        {/* ① Stream log */}
        <div className="glass-card fade-up" style={{ padding: 20 }}>
          <div className="card-label">
            <span className="dot-live" style={{ marginRight: 6, verticalAlign: "middle" }} />
            Gemini analysis
          </div>
          <div
            ref={logRef}
            className="inset-surface"
            style={{
              padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 11,
              color: "rgba(196,181,253,0.85)", lineHeight: 1.9, minHeight: 90,
              maxHeight: 140, overflowY: "auto",
            }}
          >
            {logs.length === 0 && (
              <span style={{ color: "rgba(196,181,253,0.35)" }}>Connecting to Gemini…</span>
            )}
            {logs.map((l, i) => <div key={i}>{l}<br /></div>)}
            {!analysisDone && <span style={{ animation: "stream-cursor 0.9s step-end infinite" }}>▌</span>}
          </div>

          {/* Formula cards */}
          {analysisDone && analysis.hook && (
            <div className="fade-up-1" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7, marginTop: 12 }}>
              {[
                { label: "Hook",   value: analysis.hook },
                { label: "Pacing", value: analysis.pacing },
                { label: "Visual", value: analysis.visual_style },
                { label: "Audio",  value: analysis.audio },
              ].map((f) => f.value && (
                <div key={f.label} className="formula-card">
                  <div className="label">{f.label}</div>
                  <div className="value">{f.value}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ② Brand form */}
        <div className="glass-card fade-up-1" style={{ padding: 20, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <div className="card-label">Brand requirements</div>
            <div style={{ fontSize: 10, color: "var(--text-faint)", marginBottom: 4 }}>Describe your brand</div>
            <textarea
              className="glass-input"
              rows={3}
              placeholder="e.g. Minimalist skincare brand, calm & trustworthy, targets 25-35F…"
              value={brandDesc}
              onChange={(e) => setBrandDesc(e.target.value)}
            />
            <div style={{ fontSize: 10, color: "var(--text-faint)", marginBottom: 4, marginTop: 10 }}>Style adjustments</div>
            <input
              className="glass-input"
              placeholder="e.g. Warmer tones, no fast cuts, add logo at end…"
              value={styleAdj}
              onChange={(e) => setStyleAdj(e.target.value)}
            />
          </div>

          <div>
            {/* Status chips */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7, marginTop: 14, marginBottom: 12 }}>
              <div className="status-chip">
                {analysisDone ? "✓ Analysis ready" : "⏳ Analyzing…"}
              </div>
              <div className="status-chip">
                {brandDesc.trim() ? "✓ Brand set" : "— Brand needed"}
              </div>
            </div>

            {genError && (
              <div style={{ fontSize: 11, color: "#f87171", marginBottom: 8 }}>⚠ {genError}</div>
            )}

            <button
              className="btn-primary"
              onClick={handleGenerate}
              disabled={!analysisDone || !brandDesc.trim()}
            >
              Generate with Veo 3.1 →
            </button>
          </div>
        </div>

        {/* ③ Storyboard — full width */}
        {storyboardImgs.length > 0 && (
          <div className="glass-card fade-up-2" style={{ gridColumn: "1 / -1", padding: 20 }}>
            <div className="card-label">Storyboard · {storyboardImgs.length} scenes</div>
            <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 4 }}>
              {storyboardImgs.map((src, i) => {
                const scene = analysis.storyboard?.[i];
                return (
                  <div key={i} style={{ flexShrink: 0, width: 110 }}>
                    <div
                      className="film-frame-img"
                      style={{ width: 110, height: 70 }}
                    >
                      {src ? (
                        <img
                          src={src} alt={`Scene ${i + 1}`}
                          style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: 7 }}
                        />
                      ) : (
                        <div className="shimmer" style={{ width: "100%", height: "100%", borderRadius: 7 }} />
                      )}
                    </div>
                    <div style={{
                      fontSize: 9, color: "rgba(167,139,250,0.55)",
                      textAlign: "center", marginTop: 5, fontFamily: "var(--font-mono)",
                    }}>
                      SC.{String(i + 1).padStart(2, "0")}
                      {scene?.duration && ` · ${scene.duration}s`}
                    </div>
                    {scene?.description && (
                      <div style={{
                        fontSize: 9, color: "rgba(196,181,253,0.45)", textAlign: "center",
                        marginTop: 2, lineHeight: 1.4,
                        display: "-webkit-box", WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical", overflow: "hidden",
                      }}>
                        {scene.description}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
