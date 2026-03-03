"use client";

interface Props {
  url: string;
  onReset: () => void;
}

export default function ResultPlayer({ url, onReset }: Props) {
  return (
    <div className="flex flex-col items-center gap-8">
      <div className="text-center space-y-2">
        <div className="flex items-center justify-center gap-3">
          <div className="w-2 h-2 bg-[#FF3B00]" />
          <h2 className="text-xs tracking-[0.3em] uppercase text-white/60">
            Your video is ready
          </h2>
          <div className="w-2 h-2 bg-[#FF3B00]" />
        </div>
        <p className="text-3xl font-bold">Viral formula replicated.</p>
      </div>

      {/* Video player */}
      <div className="w-full max-w-sm border border-white/10">
        <video
          src={url}
          controls
          autoPlay
          loop
          className="w-full"
        />
      </div>

      <div className="flex gap-4">
        <a
          href={url}
          download="cutto-video.mp4"
          className="px-8 py-3 bg-[#FF3B00] text-sm tracking-widest uppercase font-bold hover:bg-[#FF5500] transition-colors"
        >
          Download
        </a>
        <button
          onClick={onReset}
          className="px-8 py-3 border border-white/20 text-sm tracking-widest uppercase text-white/60 hover:border-white/40 transition-colors"
        >
          New Video
        </button>
      </div>
    </div>
  );
}
