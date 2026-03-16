"use client";

import { useState } from "react";
import UploadZone from "@/components/UploadZone";
import AnalysisStream from "@/components/AnalysisStream";
import ResultPlayer from "@/components/ResultPlayer";

export type AppStage = "upload" | "analysis" | "brand" | "generate" | "result";

const STEPS = ["Upload", "Analysis", "Brand", "Generate", "Export"];

export default function Home() {
  const [stage, setStage] = useState<AppStage>("upload");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string>("");
  const [resultUrl, setResultUrl] = useState<string>("");

  const activeStep =
    stage === "upload" ? 0 :
    stage === "analysis" ? 1 :
    stage === "brand" ? 2 :
    stage === "generate" ? 3 : 4;

  function handleUploadDone(file: File) {
    setVideoFile(file);
    setStage("analysis");
  }

  function handleResultReady(url: string, id: string) {
    setResultUrl(url);
    setJobId(id);
    setStage("result");
  }

  function handleReset() {
    setStage("upload");
    setVideoFile(null);
    setJobId("");
    setResultUrl("");
  }

  return (
    <div style={{ minHeight: "100vh", position: "relative", overflow: "hidden" }}>
      {/* ── Background ── */}
      <div style={{
        position: "fixed", inset: 0, zIndex: 0,
        background: "linear-gradient(140deg, #1a0533 0%, #2e1065 40%, #3b0764 70%, #4c1d95 100%)",
      }} />
      {/* Orbs */}
      <div style={{
        position: "fixed", top: -120, right: -80, width: 420, height: 420, zIndex: 0, pointerEvents: "none",
        background: "radial-gradient(circle, rgba(139,92,246,0.35) 0%, transparent 65%)",
      }} />
      <div style={{
        position: "fixed", bottom: -60, left: -60, width: 300, height: 300, zIndex: 0, pointerEvents: "none",
        background: "radial-gradient(circle, rgba(109,40,217,0.3) 0%, transparent 65%)",
      }} />
      <div style={{
        position: "fixed", top: "40%", left: "38%", width: 220, height: 220, zIndex: 0, pointerEvents: "none",
        background: "radial-gradient(circle, rgba(167,139,250,0.15) 0%, transparent 65%)",
      }} />

      {/* ── Nav ── */}
      <nav style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 50, height: 52,
        background: "rgba(0,0,0,0.28)", backdropFilter: "blur(32px)", WebkitBackdropFilter: "blur(32px)",
        borderBottom: "1px solid rgba(255,255,255,0.09)",
        display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 28px",
      }}>
        {/* Logo */}
        <span style={{ fontFamily: "var(--font-syne)", fontWeight: 800, fontSize: 18, color: "#f3f0ff", letterSpacing: "-0.5px" }}>
          Cut<span style={{ color: "#a78bfa" }}>to</span>
        </span>

        {/* Steps */}
        <div style={{ display: "flex", alignItems: "center" }}>
          {STEPS.map((label, i) => {
            const done = i < activeStep;
            const active = i === activeStep;
            return (
              <div key={label} style={{ display: "flex", alignItems: "center" }}>
                <div style={{
                  display: "flex", alignItems: "center", gap: 6,
                  fontSize: 11, padding: "0 9px",
                  color: done ? "rgba(255,255,255,0.7)" : active ? "#e9d5ff" : "rgba(255,255,255,0.3)",
                }}>
                  <div style={{
                    width: 19, height: 19, borderRadius: "50%", flexShrink: 0,
                    border: `1.5px solid ${done ? "#a78bfa" : active ? "#a78bfa" : "rgba(255,255,255,0.25)"}`,
                    background: done ? "#a78bfa" : active ? "rgba(167,139,250,0.2)" : "transparent",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 9.5, fontWeight: 600,
                    color: done ? "#1e0a3c" : active ? "#e9d5ff" : "rgba(255,255,255,0.3)",
                  }}>
                    {done ? "✓" : i + 1}
                  </div>
                  {label}
                </div>
                {i < STEPS.length - 1 && (
                  <div style={{ width: 14, height: 1, background: "rgba(255,255,255,0.12)" }} />
                )}
              </div>
            );
          })}
        </div>

        {/* Live dot */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "rgba(196,181,253,0.6)" }}>
          <span className="dot-live" />
          Connected
        </div>
      </nav>

      {/* ── Main ── */}
      <main style={{ position: "relative", zIndex: 1, paddingTop: 68, paddingBottom: 32 }}>
        {stage === "upload" && (
          <UploadZone onDone={handleUploadDone} />
        )}
        {(stage === "analysis" || stage === "brand" || stage === "generate") && videoFile && (
          <AnalysisStream
            videoFile={videoFile}
            onResult={handleResultReady}
            onStageChange={setStage}
          />
        )}
        {stage === "result" && (
          <ResultPlayer
            videoUrl={resultUrl}
            onReset={handleReset}
          />
        )}
      </main>
    </div>
  );
}
