"use client";

interface Props {
  videoUrl: string;
  onReset: () => void;
}

export default function ResultPlayer({ videoUrl, onReset }: Props) {
  return (
    <div className="fade-up" style={{
      maxWidth: 680, margin: "0 auto", padding: "0 20px",
      display: "flex", flexDirection: "column", gap: 16,
    }}>
      {/* Header */}
      <div style={{ textAlign: "center", marginBottom: 8 }}>
        <h2 style={{
          fontFamily: "var(--font-syne)", fontWeight: 800, fontSize: 26,
          color: "#f3f0ff", letterSpacing: "-0.3px", marginBottom: 6,
        }}>
          Your video is ready
        </h2>
        <p style={{ fontSize: 13, color: "rgba(196,181,253,0.6)" }}>
          Generated with Gemini + Veo 3.1
        </p>
      </div>

      {/* Video player card */}
      <div className="glass-card" style={{ padding: 16 }}>
        <video
          src={videoUrl}
          controls
          autoPlay
          style={{
            width: "100%", borderRadius: 10, display: "block",
            background: "rgba(0,0,0,0.4)",
          }}
        />
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 10 }}>
        <a
          href={videoUrl}
          download="cutto-output.mp4"
          style={{
            flex: 1, display: "block", textAlign: "center",
            background: "rgba(139,92,246,0.35)",
            color: "#f3f0ff",
            border: "1px solid rgba(167,139,250,0.45)",
            borderRadius: 10, padding: "11px 18px",
            fontSize: 13, fontWeight: 600,
            fontFamily: "var(--font-syne)",
            letterSpacing: "0.02em",
            textDecoration: "none",
            backdropFilter: "blur(12px)",
            boxShadow: "inset 0 1px 0 rgba(255,255,255,0.12)",
            transition: "background 0.2s",
          }}
        >
          Download MP4 ↓
        </a>
        <button
          onClick={onReset}
          style={{
            flex: 1,
            background: "rgba(255,255,255,0.06)",
            color: "rgba(196,181,253,0.8)",
            border: "1px solid rgba(167,139,250,0.2)",
            borderRadius: 10, padding: "11px 18px",
            fontSize: 13, fontWeight: 600,
            fontFamily: "var(--font-syne)",
            cursor: "pointer",
            transition: "background 0.2s",
          }}
        >
          Start over ↩
        </button>
      </div>
    </div>
  );
}
