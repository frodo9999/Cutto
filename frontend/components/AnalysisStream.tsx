"use client";

import { useEffect, useRef, useState, useCallback } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://cutto-backend-846822745809.us-central1.run.app";

interface Props {
  videoFile: File;
  onResult: (url: string, jobId: string) => void;
  onStageChange?: (stage: "analysis" | "brand" | "generate") => void;
}

interface StoryboardScene {
  scene: number;
  description: string;
  duration: number;
  visual_prompt?: string;
  timing_note?: string;
  transition_out?: string;
  continuous_with_next?: boolean;
}

interface Analysis {
  hook_strategy?: string;
  pacing?: string;
  visual_style?: string;
  audio_style?: string;
  caption_style?: string;
  viral_factors?: string[];
  storyboard?: StoryboardScene[];
}

interface DirectorScene {
  scene: number;
  duration: number;
  description: string;
  veo_prompt?: string;
}

type GenStep = "veo" | "ffmpeg" | "done";

const GEN_STEPS: { key: GenStep; label: string }[] = [
  { key: "veo",    label: "Generating video clips with Veo 3.1" },
  { key: "ffmpeg", label: "Compositing with FFmpeg" },
  { key: "done",   label: "Done" },
];

const HOLE_COUNT = 7;

function FilmCard({
  index, src, label, desc, offsetIdx, onClick,
}: {
  index: number; src: string | null; label: string; desc: string;
  offsetIdx: number; onClick: () => void;
}) {
  const holes = Array(HOLE_COUNT).fill(0);

  let transform = "";
  let opacity = 1;
  let brightness = 1;
  let zIndex = 1;
  let pointerEvents: "auto" | "none" = "auto";
  let borderColor = "rgba(167,139,250,0.15)";
  let boxShadow = "none";

  if (offsetIdx === 0) {
    transform = "translate(-50%,-50%) translateZ(0) rotateY(0deg) scale(1)";
    opacity = 1; brightness = 1; zIndex = 10;
    borderColor = "rgba(167,139,250,0.65)";
    boxShadow = "0 0 0 2px rgba(139,92,246,0.3)";
  } else if (offsetIdx === 1) {
    transform = "translate(calc(-50% + 162px),-50%) translateZ(-55px) rotateY(-40deg) scale(0.83)";
    opacity = 0.55; brightness = 0.6; zIndex = 5;
  } else if (offsetIdx === -1) {
    transform = "translate(calc(-50% - 162px),-50%) translateZ(-55px) rotateY(40deg) scale(0.83)";
    opacity = 0.55; brightness = 0.6; zIndex = 5;
  } else {
    const sign = offsetIdx > 0 ? 1 : -1;
    transform = `translate(calc(-50% + ${sign * 320}px),-50%) translateZ(-120px) rotateY(${sign * -58}deg) scale(0.55)`;
    opacity = 0; pointerEvents = "none";
  }

  const SprocketStrip = () => (
    <div style={{ display: "flex", alignItems: "center", padding: "4px 5px", background: "#060210", gap: 3 }}>
      {holes.map((_, i) => (
        <div key={i} style={{ width: 8, height: 6, borderRadius: 2, background: "#0a0510", border: "0.5px solid rgba(255,255,255,0.06)", flexShrink: 0 }} />
      ))}
      <div style={{ flex: 1 }} />
      <span style={{ fontSize: 7, color: "rgba(255,255,255,0.15)", fontFamily: "var(--font-mono)", letterSpacing: "0.05em" }}>
        {String(index + 1).padStart(2, "0")}A
      </span>
    </div>
  );

  return (
    <div
      onClick={onClick}
      style={{
        position: "absolute", left: "50%", top: "50%",
        width: 180, cursor: pointerEvents === "none" ? "default" : "pointer",
        transform, opacity,
        filter: `brightness(${brightness})`,
        zIndex, pointerEvents,
        transition: "all 0.42s cubic-bezier(0.25,0.46,0.45,0.94)",
      }}
    >
      <div style={{
        width: "100%", borderRadius: 5, overflow: "hidden",
        background: "#0a0510",
        border: `1.5px solid ${borderColor}`,
        boxShadow,
        transition: "border-color 0.42s, box-shadow 0.42s",
      }}>
        <SprocketStrip />
        <div style={{
          width: "100%", height: 155, position: "relative", overflow: "hidden",
          background: "rgba(109,40,217,0.2)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          {src ? (
            <img src={src} alt={label} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          ) : (
            <>
              <div className="shimmer" style={{ position: "absolute", inset: 0 }} />
              <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "rgba(196,181,253,0.35)", position: "relative", zIndex: 1 }}>
                {label.split(" ")[0]}
              </span>
            </>
          )}
        </div>
        <SprocketStrip />
        <div style={{ padding: "6px 8px 7px", background: "#060210", borderTop: "0.5px solid rgba(255,255,255,0.05)" }}>
          <div style={{ fontSize: 8, color: "rgba(196,181,253,0.4)", fontFamily: "var(--font-mono)", letterSpacing: "0.08em" }}>
            {label}
          </div>
          <div style={{
            fontSize: 9.5, color: "rgba(196,181,253,0.65)", marginTop: 2, lineHeight: 1.35,
            display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
          } as React.CSSProperties}>
            {desc || "Analyzing…"}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function AnalysisStream({ videoFile, onResult, onStageChange }: Props) {
  const [analysis, setAnalysis] = useState<Analysis>({});
  const [storyboardImgs, setStoryboardImgs] = useState<(string | null)[]>([]);
  const [jobId, setJobId] = useState("");
  const [analysisDone, setAnalysisDone] = useState(false);

  const [activeIdx, setActiveIdx] = useState(0);
  const [analysisVisible, setAnalysisVisible] = useState(true);
  const [directorImgs, setDirectorImgs] = useState<(string | null)[] | null>(null);

  const [brandDesc, setBrandDesc] = useState("");
  const [styleAdj, setStyleAdj] = useState("");

  const [directorScenes, setDirectorScenes] = useState<DirectorScene[] | null>(null);
  const [directorLoading, setDirectorLoading] = useState(false);
  const [directorError, setDirectorError] = useState("");

  const [generating, setGenerating] = useState(false);
  const [genStep, setGenStep] = useState<GenStep | null>(null);
  const [genError, setGenError] = useState("");

  const jobIdRef = useRef("");

  // ── SSE ──────────────────────────────────────────────────────────────────────
  useEffect(() => {
    const ctrl = new AbortController();
    const fd = new FormData();
    fd.append("viral_video", videoFile);
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/analyze`, { method: "POST", body: fd, signal: ctrl.signal });
        if (!res.body) return;
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() ?? "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw || raw === "[DONE]") continue;
            try { handleEvent(JSON.parse(raw)); } catch { /* ignore */ }
          }
        }
        setAnalysisDone(true);
      } catch (err: unknown) {
        if ((err as Error).name !== "AbortError")
          console.error("Analysis error:", (err as Error).message);
      }
    })();
    return () => ctrl.abort();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleEvent(evt: Record<string, unknown>) {
    const type = evt.type as string;
    if (type === "job_id") {
      const id = (evt.content ?? evt.job_id) as string;
      setJobId(id); jobIdRef.current = id;
    } else if (type === "text_chunk") {
      // text_chunk — not displayed
    } else if (type === "analysis_complete") {
      const data = (evt.content ?? evt.analysis) as Analysis;
      setAnalysis(data);
      const count = data.storyboard?.length ?? 0;
      if (count > 0) setStoryboardImgs(Array(count).fill(null));
      onStageChange?.("brand");
    } else if (type === "storyboard_frame") {
      const idx = evt.index as number;
      const url = evt.url as string;
      if (url) setStoryboardImgs(prev => { const n = [...prev]; n[idx] = url; return n; });
    } else if (type === "done") {
      const id = (evt.job_id ?? evt.content) as string;
      if (id) { setJobId(id); jobIdRef.current = id; }
    } else if (type === "error") {
      // error logged to console only
      console.warn("SSE error:", (evt.content ?? evt.message));
    }
  }

  // ── Carousel ─────────────────────────────────────────────────────────────────
  const sceneCount = analysis.storyboard?.length ?? storyboardImgs.length;

  const goTo = useCallback((idx: number) => {
    const count = analysis.storyboard?.length ?? storyboardImgs.length;
    if (count === 0) return;
    const next = ((idx % count) + count) % count;
    setAnalysisVisible(false);
    setTimeout(() => { setActiveIdx(next); setAnalysisVisible(true); }, 200);
  }, [analysis.storyboard?.length, storyboardImgs.length]); // eslint-disable-line

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") goTo(activeIdx - 1);
      if (e.key === "ArrowRight") goTo(activeIdx + 1);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [activeIdx, goTo]);

  // ── Director script ──────────────────────────────────────────────────────────
  async function handleGetDirectorScript() {
    if (!brandDesc.trim() || !jobIdRef.current) return;
    setDirectorLoading(true); setDirectorError(""); setDirectorScenes(null); setDirectorImgs(null);
    try {
      const form = new FormData();
      form.append("custom_assets_description", brandDesc);
      form.append("user_requirements", styleAdj);
      const res = await fetch(`${API_BASE}/api/director/${jobIdRef.current}`, { method: "POST", body: form });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail ?? "Failed"); }
      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw || raw === "[DONE]") continue;
          try {
            const evt = JSON.parse(raw);
            if (evt.type === "script_ready") {
              setDirectorScenes(evt.scenes);
              setDirectorLoading(false);
              setDirectorImgs(Array(evt.scenes.length).fill(null));
              setActiveIdx(0);
            } else if (evt.type === "director_frame") {
              setDirectorImgs(prev => {
                if (!prev) return prev;
                const next = [...prev]; next[evt.index] = evt.image; return next;
              });
            }
          } catch { /* ignore */ }
        }
      }
    } catch (err: unknown) {
      setDirectorError((err as Error).message);
      setDirectorLoading(false);
    }
  }

  // ── Generate ──────────────────────────────────────────────────────────────────
  async function handleGenerate() {
    if (!jobIdRef.current || !directorScenes) return;
    setGenerating(true); setGenError(""); setGenStep("veo"); onStageChange?.("generate");
    try {
      const res = await fetch(`${API_BASE}/api/generate/${jobIdRef.current}`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Generation failed");
      await pollStatus();
    } catch (err: unknown) {
      setGenError((err as Error).message);
      setGenerating(false); setGenStep(null);
    }
  }

  async function pollStatus() {
    const INTERVAL = 4000;
    const MAX_WAIT = 20 * 60 * 1000;
    const start = Date.now();
    while (Date.now() - start < MAX_WAIT) {
      await new Promise(r => setTimeout(r, INTERVAL));
      try {
        const res = await fetch(`${API_BASE}/api/status/${jobIdRef.current}`);
        if (!res.ok) continue;
        const status = await res.json();
        if (status.progress >= 85) setGenStep("ffmpeg");
        else if (status.progress >= 60) setGenStep("veo");
        if (status.status === "done" && status.result_url) {
          setGenStep("done"); onResult(status.result_url, jobIdRef.current); return;
        }
        if (status.status === "error") throw new Error(status.message ?? "Generation failed");
      } catch (err: unknown) {
        if ((err as Error).message === "Generation failed") throw err;
      }
    }
    throw new Error("Generation timed out");
  }

  // ── Generating overlay ────────────────────────────────────────────────────────
  if (generating) {
    return (
      <div className="fade-in" style={{ maxWidth: 860, margin: "0 auto", padding: "0 20px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="glass-card" style={{ padding: 32, textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
          <div className="spinner-ring" style={{ margin: "0 auto 24px" }} />
          <h2 style={{ fontFamily: "var(--font-syne)", fontWeight: 700, fontSize: 18, color: "#f3f0ff", marginBottom: 8 }}>Generating your video</h2>
          <p style={{ fontSize: 12, color: "rgba(196,181,253,0.6)", marginBottom: 28 }}>This usually takes 5–10 minutes</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, textAlign: "left", width: "100%" }}>
            {GEN_STEPS.filter(s => s.key !== "done").map(s => {
              const idx = GEN_STEPS.findIndex(x => x.key === s.key);
              const activeIdx2 = GEN_STEPS.findIndex(x => x.key === genStep);
              const isDone = idx < activeIdx2;
              const isActive = s.key === genStep;
              return (
                <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 20, height: 20, borderRadius: "50%", flexShrink: 0, border: `1.5px solid ${isDone || isActive ? "#a78bfa" : "rgba(167,139,250,0.2)"}`, background: isDone ? "#a78bfa" : "transparent", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, color: isDone ? "#1e0a3c" : "transparent" }}>
                    {isDone ? "✓" : isActive ? <span className="dot-live" style={{ width: 6, height: 6 }} /> : ""}
                  </div>
                  <span style={{ fontSize: 12, color: isDone ? "rgba(196,181,253,0.7)" : isActive ? "#e9d5ff" : "rgba(196,181,253,0.35)" }}>{s.label}</span>
                </div>
              );
            })}
          </div>
        </div>
        {directorScenes && (
          <div className="glass-card" style={{ padding: 20, overflowY: "auto", maxHeight: 420 }}>
            <div className="card-label">Director script for your video · {directorScenes.length} scenes</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {directorScenes.map(s => (
                <div key={s.scene} style={{ background: "rgba(0,0,0,0.15)", borderRadius: 10, padding: "14px 16px", border: "1px solid var(--border-purple)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
                    <div style={{ flexShrink: 0, width: 22, height: 22, borderRadius: "50%", background: "rgba(139,92,246,0.25)", border: "1px solid var(--border-purple-hi)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 600, color: "var(--purple-bright)" }}>{s.scene}</div>
                    <div style={{ fontSize: 13, color: "#e9d5ff", lineHeight: 1.5 }}>{s.description}</div>
                  </div>
                  {s.veo_prompt && (
                    <div style={{ fontSize: 11, color: "rgba(196,181,253,0.6)", lineHeight: 1.7, marginBottom: 8, paddingLeft: 30 }}>{s.veo_prompt}</div>
                  )}
                  <div style={{ display: "flex", gap: 5, paddingLeft: 30 }}>
                    <span style={{ background: "rgba(109,40,217,0.25)", border: "1px solid rgba(167,139,250,0.2)", borderRadius: 5, padding: "2px 7px", fontSize: 9.5, color: "rgba(196,181,253,0.75)" }}>{s.duration}s</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  const currentScene = analysis.storyboard?.[activeIdx];
  const analysisReady = analysisDone && !!analysis.storyboard;

  // ── Main UI ───────────────────────────────────────────────────────────────────
  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "0 20px", display: "flex", flexDirection: "column", gap: 14 }}>

      {/* ① Film drum — appears once storyboard count is known */}
      {sceneCount > 0 ? (
        <div className="glass-card fade-up" style={{ padding: "20px 0 16px", overflow: "hidden" }}>
          {/* Drum stage */}
          <div style={{ position: "relative", height: 280, perspective: 900, overflow: "hidden", transformStyle: "preserve-3d" }}>
            <div style={{ position: "absolute", inset: 0 }}>
              {Array.from({ length: sceneCount }).map((_, i) => {
                let off = i - activeIdx;
                if (sceneCount > 3) {
                  if (off > Math.floor(sceneCount / 2)) off -= sceneCount;
                  if (off < -Math.floor(sceneCount / 2)) off += sceneCount;
                }
                const scene = analysis.storyboard?.[i];
                return (
                  <FilmCard
                    key={i} index={i}
                    src={(directorImgs ? directorImgs[i] : storyboardImgs[i]) ?? null}
                    label={`SC.${String(i + 1).padStart(2, "0")} · ${scene?.duration ?? "?"}s`}
                    desc={scene?.description ?? ""}
                    offsetIdx={off}
                    onClick={() => goTo(i)}
                  />
                );
              })}
            </div>
            <button onClick={() => goTo(activeIdx - 1)} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", background: "rgba(139,92,246,0.2)", border: "1px solid rgba(167,139,250,0.25)", color: "#e9d5ff", width: 28, height: 28, borderRadius: "50%", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, zIndex: 20 }}>‹</button>
            <button onClick={() => goTo(activeIdx + 1)} style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "rgba(139,92,246,0.2)", border: "1px solid rgba(167,139,250,0.25)", color: "#e9d5ff", width: 28, height: 28, borderRadius: "50%", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, zIndex: 20 }}>›</button>
          </div>

          {/* ② Scene analysis below the drum */}
          <div style={{
            padding: "16px 24px 4px", minHeight: 100,
            opacity: analysisVisible ? 1 : 0,
            transform: analysisVisible ? "translateY(0)" : "translateY(6px)",
            transition: "opacity 0.25s, transform 0.25s",
          }}>
            {(() => {
              // If director script is ready, show director scene info
              const dirScene = directorScenes?.[activeIdx];
              if (dirScene) {
                return (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                      <span className="dot-live" />
                      <span style={{ fontSize: 10, fontWeight: 600, color: "rgba(196,181,253,0.5)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
                        Director script · Scene {activeIdx + 1} of {sceneCount}
                      </span>
                    </div>
                    <div style={{ fontSize: 13, color: "#e9d5ff", marginBottom: 5, lineHeight: 1.5 }}>{dirScene.description}</div>
                    {dirScene.veo_prompt && (
                      <div style={{ fontSize: 11, color: "rgba(196,181,253,0.6)", lineHeight: 1.7, marginBottom: 8 }}>{dirScene.veo_prompt}</div>
                    )}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                      <span style={{ background: "rgba(109,40,217,0.25)", border: "1px solid rgba(167,139,250,0.2)", borderRadius: 5, padding: "2px 7px", fontSize: 9.5, color: "rgba(196,181,253,0.75)" }}>{dirScene.duration}s</span>
                    </div>
                  </>
                );
              }
              // Otherwise show original analysis
              if (analysisReady && currentScene) {
                return (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                      <span className="dot-live" />
                      <span style={{ fontSize: 10, fontWeight: 600, color: "rgba(196,181,253,0.5)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
                        Scene {activeIdx + 1} of {sceneCount}
                      </span>
                    </div>
                    <div style={{ fontSize: 13, color: "#e9d5ff", marginBottom: 5, lineHeight: 1.5 }}>{currentScene.description}</div>
                    {currentScene.visual_prompt && (
                      <div style={{ fontSize: 11, color: "rgba(196,181,253,0.6)", lineHeight: 1.7, marginBottom: 8 }}>{currentScene.visual_prompt}</div>
                    )}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                      {[
                        currentScene.duration && `${currentScene.duration}s`,
                        currentScene.transition_out,
                        currentScene.continuous_with_next && "Continuous →",
                        currentScene.timing_note,
                      ].filter(Boolean).map((tag, i) => (
                        <span key={i} style={{ background: "rgba(109,40,217,0.25)", border: "1px solid rgba(167,139,250,0.2)", borderRadius: 5, padding: "2px 7px", fontSize: 9.5, color: "rgba(196,181,253,0.75)" }}>
                          {tag as string}
                        </span>
                      ))}
                    </div>
                  </>
                );
              }
              return (
                <div style={{ fontSize: 12, color: "rgba(196,181,253,0.35)", display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="dot-live" />
                  {analysisDone ? "Analysis ready — scroll through scenes above" : "Gemini is analyzing your video…"}
                </div>
              );
            })()}
          </div>
        </div>
      ) : (
        /* Loading skeleton before storyboard arrives */
        <div className="glass-card fade-up" style={{ padding: 40, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 200, gap: 16 }}>
          <div className="spinner-ring" />
          <div style={{ fontSize: 13, color: "rgba(196,181,253,0.6)", fontFamily: "var(--font-syne)" }}>
            Analyzing your video…
          </div>
        </div>
      )}

      {/* ③ Director script — shown after creation, before generation */}
      {directorScenes && !generating && (
        <div className="glass-card fade-up-1" style={{ padding: 20 }}>
          <div className="card-label">Director script for your video · {directorScenes.length} scenes</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {directorScenes.map(s => (
              <div key={s.scene} style={{ background: "rgba(0,0,0,0.15)", borderRadius: 10, padding: "14px 16px", border: "1px solid var(--border-purple)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
                  <div style={{ flexShrink: 0, width: 22, height: 22, borderRadius: "50%", background: "rgba(139,92,246,0.25)", border: "1px solid var(--border-purple-hi)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 600, color: "var(--purple-bright)" }}>{s.scene}</div>
                  <div style={{ fontSize: 13, color: "#e9d5ff", lineHeight: 1.5 }}>{s.description}</div>
                </div>
                {s.veo_prompt && (
                  <div style={{ fontSize: 11, color: "rgba(196,181,253,0.6)", lineHeight: 1.7, marginBottom: 8, paddingLeft: 30 }}>{s.veo_prompt}</div>
                )}
                <div style={{ display: "flex", gap: 5, paddingLeft: 30 }}>
                  <span style={{ background: "rgba(109,40,217,0.25)", border: "1px solid rgba(167,139,250,0.2)", borderRadius: 5, padding: "2px 7px", fontSize: 9.5, color: "rgba(196,181,253,0.75)" }}>{s.duration}s</span>
                </div>
              </div>
            ))}
          </div>
          {genError && <div style={{ fontSize: 11, color: "#f87171", marginTop: 10 }}>⚠ {genError}</div>}
        </div>
      )}

      {/* ④ Brand panel */}
      <div className="glass-card fade-up-2" style={{ padding: 20 }}>
        <div className="card-label">Brand requirements</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 10, color: "var(--text-faint)", marginBottom: 4 }}>Describe your brand</div>
            <textarea className="glass-input" rows={3} placeholder="e.g. Minimalist skincare brand, calm & trustworthy, targets 25-35F…" value={brandDesc} onChange={e => { setBrandDesc(e.target.value); setDirectorScenes(null); }} />
          </div>
          <div>
            <div style={{ fontSize: 10, color: "var(--text-faint)", marginBottom: 4 }}>Style adjustments</div>
            <textarea className="glass-input" rows={3} placeholder="e.g. Warmer tones, no fast cuts, add logo at end…" value={styleAdj} onChange={e => { setStyleAdj(e.target.value); setDirectorScenes(null); }} />
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
          <div className="status-chip">{analysisDone ? "✓ Analysis ready" : "⏳ Analyzing…"}</div>
          <div className="status-chip">{brandDesc.trim() ? "✓ Brand set" : "— Brand needed"}</div>
        </div>
        {directorError && <div style={{ fontSize: 11, color: "#f87171", marginBottom: 8 }}>⚠ {directorError}</div>}
        {!directorScenes ? (
          <button className="btn-primary" onClick={handleGetDirectorScript} disabled={!analysisDone || !brandDesc.trim() || directorLoading}>
            {directorLoading ? "Creating script…" : "Create Director Script →"}
          </button>
        ) : (
          <button className="btn-primary" onClick={handleGenerate}>Generate with Veo 3.1 →</button>
        )}
      </div>
    </div>
  );
}
