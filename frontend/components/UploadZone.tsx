"use client";

import { useCallback, useState } from "react";

interface Props {
  onDone: (file: File) => void;
}

const HINTS = [
  { icon: "🎯", label: "Hook analysis" },
  { icon: "🎵", label: "Audio detection" },
  { icon: "📐", label: "Pacing breakdown" },
  { icon: "🎬", label: "Scene storyboard" },
];

export default function UploadZone({ onDone }: Props) {
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");

  const handleFile = useCallback(
    (file: File) => {
      if (!file.type.startsWith("video/")) return;
      setFileName(file.name);
      const url = URL.createObjectURL(file);
      setPreview(url);
      // Small delay for preview animation
      setTimeout(() => onDone(file), 800);
    },
    [onDone]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div className="fade-up" style={{
      maxWidth: 560, margin: "0 auto", padding: "0 20px",
      display: "flex", flexDirection: "column", alignItems: "center", gap: 24,
      paddingTop: 48,
    }}>
      {/* Heading */}
      <div style={{ textAlign: "center" }}>
        <h1 style={{
          fontFamily: "var(--font-syne)", fontWeight: 800, fontSize: 32,
          color: "#f3f0ff", letterSpacing: "-0.5px", lineHeight: 1.2, marginBottom: 10,
        }}>
          Replicate what goes viral
        </h1>
        <p style={{ fontSize: 14, color: "rgba(196,181,253,0.65)", lineHeight: 1.7 }}>
          Drop a viral video. Gemini analyzes the formula. Veo adapts it to your brand.
        </p>
      </div>

      {/* Upload card */}
      <div className="glass-card" style={{ width: "100%", padding: 24 }}>
        <label
          htmlFor="video-upload"
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          style={{
            display: "flex", flexDirection: "column", alignItems: "center", gap: 14,
            border: `1.5px dashed ${dragging ? "rgba(167,139,250,0.65)" : "rgba(167,139,250,0.3)"}`,
            background: dragging ? "rgba(109,40,217,0.18)" : "rgba(109,40,217,0.08)",
            borderRadius: 12, padding: "36px 24px", cursor: "pointer",
            transition: "all 0.2s",
          }}
        >
          {preview ? (
            <>
              <video
                src={preview} muted playsInline autoPlay
                style={{ width: "100%", maxHeight: 180, borderRadius: 8, objectFit: "cover" }}
              />
              <span style={{ fontSize: 12, color: "rgba(196,181,253,0.6)" }}>{fileName}</span>
            </>
          ) : (
            <>
              {/* Icon */}
              <div style={{
                width: 52, height: 52,
                background: "rgba(167,139,250,0.15)",
                border: "1px solid rgba(167,139,250,0.3)",
                borderRadius: 14,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 22,
              }}>▶</div>
              <div style={{ textAlign: "center" }}>
                <div style={{
                  fontFamily: "var(--font-syne)", fontWeight: 700, fontSize: 15,
                  color: "#f3f0ff", marginBottom: 4,
                }}>
                  Drop your viral video here
                </div>
                <div style={{ fontSize: 12, color: "rgba(196,181,253,0.5)" }}>
                  or click to browse · MP4, MOV, WebM up to 500MB
                </div>
              </div>
            </>
          )}
        </label>
        <input
          id="video-upload" type="file" accept="video/*"
          style={{ display: "none" }} onChange={onInputChange}
        />

        {/* Hint tags */}
        <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
          {HINTS.map((h) => (
            <div key={h.label} className="hint-tag">
              {h.icon} {h.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
