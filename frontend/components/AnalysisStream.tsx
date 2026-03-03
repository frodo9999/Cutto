"use client";

function cleanText(text: string): string {
  return text
    .replace(/```json\n?/g, '')
    .replace(/```\n?/g, '')
    .trim();
}

interface Props {
  text: string;
  storyboardImages: string[];
  isStreaming: boolean;
}

export default function AnalysisStream({ text, storyboardImages, isStreaming }: Props) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h2 className="text-xs tracking-[0.3em] uppercase text-white/40">
          Gemini Analysis
        </h2>
        {isStreaming && (
          <span className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="w-1.5 h-1.5 bg-[#FF3B00] rounded-full animate-bounce"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </span>
        )}
      </div>

      <div className="bg-white/3 border border-white/5 p-6 max-h-80 overflow-y-auto">
        <pre className="text-xs text-white/70 whitespace-pre-wrap leading-relaxed font-mono">
          {cleanText(text) || "Waiting for Gemini..."}
          {isStreaming && <span className="animate-pulse text-[#FF3B00]">▊</span>}
        </pre>
      </div>

      {storyboardImages.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs tracking-[0.3em] uppercase text-white/40">
            Storyboard — Gemini Interleaved Output
          </h3>
          <div className="grid grid-cols-2 gap-3">
            {storyboardImages.map((img, i) => (
              <div key={i} className="border border-white/10 overflow-hidden">
                <img src={img} alt={`Storyboard frame ${i + 1}`} className="w-full" />
                <div className="px-3 py-2 bg-white/3">
                  <span className="text-xs text-white/30">Scene {i + 1}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {isStreaming && storyboardImages.length === 0 && cleanText(text).length > 100 && (
        <div className="flex items-center gap-3 text-xs text-white/30">
          <span className="animate-pulse">⬜</span>
          Generating storyboard visuals...
        </div>
      )}
    </div>
  );
}