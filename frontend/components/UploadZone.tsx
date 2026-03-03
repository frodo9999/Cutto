"use client";

import { useState, useRef, DragEvent } from "react";

interface Props {
  onAnalyze: (viralVideo: File, requirements: string) => void;
}

export default function UploadZone({ onAnalyze }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [viralVideo, setViralVideo] = useState<File | null>(null);
  const [requirements, setRequirements] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("video/")) setViralVideo(file);
  };

  return (
    <div className="flex flex-col items-center gap-12">
      {/* Hero text */}
      <div className="text-center space-y-4">
        <h1 className="text-5xl font-bold tracking-tight leading-none">
          Upload a viral video.
          <br />
          <span className="text-[#FF3B00]">Make it yours.</span>
        </h1>
        <p className="text-white/40 text-lg max-w-xl mx-auto">
          Cutto analyzes what makes a video go viral and replicates the formula with your brand.
        </p>
      </div>

      {/* Upload area */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => fileRef.current?.click()}
        className={`w-full max-w-2xl border-2 border-dashed rounded-none p-16 flex flex-col items-center gap-4 cursor-pointer transition-all duration-200
          ${dragOver ? "border-[#FF3B00] bg-[#FF3B00]/5" : "border-white/10 hover:border-white/30"}
          ${viralVideo ? "border-[#FF3B00]/50 bg-[#FF3B00]/5" : ""}
        `}
      >
        <input
          ref={fileRef}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && setViralVideo(e.target.files[0])}
        />
        {viralVideo ? (
          <>
            <div className="w-12 h-12 bg-[#FF3B00] flex items-center justify-center">
              <svg className="w-6 h-6" fill="white" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            </div>
            <div className="text-center">
              <p className="text-white font-medium">{viralVideo.name}</p>
              <p className="text-white/40 text-sm mt-1">
                {(viralVideo.size / 1024 / 1024).toFixed(1)} MB
              </p>
            </div>
          </>
        ) : (
          <>
            <div className="w-16 h-16 border border-white/20 flex items-center justify-center">
              <svg className="w-8 h-8 text-white/30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <p className="text-white/40 text-sm tracking-widest uppercase">
              Drop viral video here or click to browse
            </p>
          </>
        )}
      </div>

      {/* Requirements input */}
      <div className="w-full max-w-2xl space-y-2">
        <label className="text-xs text-white/40 tracking-widest uppercase block">
          Your brand / requirements (optional)
        </label>
        <textarea
          value={requirements}
          onChange={(e) => setRequirements(e.target.value)}
          placeholder="e.g. I sell handmade candles, warm aesthetic, earthy tones, target women 25-35..."
          rows={3}
          className="w-full bg-white/5 border border-white/10 p-4 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/30 resize-none font-mono"
        />
      </div>

      {/* CTA */}
      <button
        disabled={!viralVideo}
        onClick={() => viralVideo && onAnalyze(viralVideo, requirements)}
        className={`px-12 py-4 text-sm tracking-[0.3em] uppercase font-bold transition-all duration-200
          ${viralVideo
            ? "bg-[#FF3B00] text-white hover:bg-[#FF5500] cursor-pointer"
            : "bg-white/5 text-white/20 cursor-not-allowed"
          }`}
      >
        Analyze & Replicate →
      </button>
    </div>
  );
}
