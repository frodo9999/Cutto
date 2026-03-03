"use client";

import { useState, useRef } from "react";
import { AnalysisData } from "@/app/page";

interface Props {
  analysis: AnalysisData;
  onGenerate: (customDesc: string, userReqs: string, customAsset?: File) => void;
}

export default function GeneratePanel({ analysis, onGenerate }: Props) {
  const [customDesc, setCustomDesc] = useState("");
  const [userReqs, setUserReqs] = useState("");
  const [customAsset, setCustomAsset] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  return (
    <div className="space-y-6">
      <h2 className="text-xs tracking-[0.3em] uppercase text-white/40">
        Viral Formula Detected
      </h2>

      {/* Analysis summary */}
      <div className="space-y-3">
        {[
          { label: "Hook", value: analysis.hook_strategy },
          { label: "Pacing", value: analysis.pacing },
          { label: "Visual", value: analysis.visual_style },
          { label: "Audio", value: analysis.audio_style },
        ].map(({ label, value }) => (
          <div key={label} className="flex gap-4 border-b border-white/5 pb-3">
            <span className="text-xs text-[#FF3B00] tracking-widest uppercase w-16 shrink-0 pt-0.5">
              {label}
            </span>
            <span className="text-xs text-white/60 leading-relaxed">{value}</span>
          </div>
        ))}

        <div className="flex gap-2 flex-wrap pt-2">
          {analysis.viral_factors.map((f, i) => (
            <span
              key={i}
              className="text-xs border border-white/10 px-3 py-1 text-white/40"
            >
              {f}
            </span>
          ))}
        </div>
      </div>

      {/* Customization inputs */}
      <div className="space-y-4 pt-4 border-t border-white/5">
        <h3 className="text-xs tracking-[0.3em] uppercase text-white/40">
          Customize for your brand
        </h3>

        <div className="space-y-2">
          <label className="text-xs text-white/30 tracking-wider uppercase block">
            Your brand / product description
          </label>
          <textarea
            value={customDesc}
            onChange={(e) => setCustomDesc(e.target.value)}
            placeholder="e.g. Premium coffee brand, dark roast, urban professional audience..."
            rows={3}
            className="w-full bg-white/5 border border-white/10 p-3 text-xs text-white placeholder-white/20 focus:outline-none focus:border-white/30 resize-none font-mono"
          />
        </div>

        <div className="space-y-2">
          <label className="text-xs text-white/30 tracking-wider uppercase block">
            Style adjustments
          </label>
          <textarea
            value={userReqs}
            onChange={(e) => setUserReqs(e.target.value)}
            placeholder="e.g. Make it 15 seconds, add more close-up shots, use warmer tones..."
            rows={2}
            className="w-full bg-white/5 border border-white/10 p-3 text-xs text-white placeholder-white/20 focus:outline-none focus:border-white/30 resize-none font-mono"
          />
        </div>

        {/* Custom asset upload */}
        <div
          onClick={() => fileRef.current?.click()}
          className="border border-dashed border-white/10 p-4 flex items-center gap-4 cursor-pointer hover:border-white/20 transition-colors"
        >
          <input
            ref={fileRef}
            type="file"
            accept="video/*,image/*"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && setCustomAsset(e.target.files[0])}
          />
          <div className="w-8 h-8 border border-white/20 flex items-center justify-center shrink-0">
            <span className="text-white/40 text-lg">+</span>
          </div>
          <div>
            <p className="text-xs text-white/40">
              {customAsset ? customAsset.name : "Upload your brand assets (optional)"}
            </p>
            <p className="text-xs text-white/20 mt-0.5">Video or image to incorporate</p>
          </div>
        </div>
      </div>

      <button
        onClick={() => onGenerate(customDesc, userReqs, customAsset || undefined)}
        className="w-full bg-[#FF3B00] py-4 text-sm tracking-[0.3em] uppercase font-bold hover:bg-[#FF5500] transition-colors"
      >
        Generate My Video →
      </button>

      <p className="text-xs text-white/20 text-center">
        Powered by Veo 3.1 · Est. 2–5 minutes
      </p>
    </div>
  );
}
