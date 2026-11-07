import { useState, useEffect } from "react";
import { Play, Pause, RotateCcw, Calendar } from "lucide-react";

export interface TemporalScrubberProps {
  currentDate: string;
  onDateChange: (date: string) => void;
  minDate?: string;
  maxDate?: string;
}

export function TemporalScrubber({
  currentDate,
  onDateChange,
  minDate = "2026-01-01",
  maxDate = "2026-04-12",
}: TemporalScrubberProps) {
  const [isPlaying, setIsPlaying] = useState(false);

  // Convert dates to timestamps for smooth slider math
  const minTime = new Date(minDate).getTime();
  const maxTime = new Date(maxDate).getTime();
  const currentTime = new Date(currentDate).getTime();

  // Playback timer
  useEffect(() => {
    if (!isPlaying) return;

    const interval = setInterval(() => {
      const nextTime = currentTime + 86400000 * 3; // advance 3 days per tick
      if (nextTime >= maxTime) {
        setIsPlaying(false);
        onDateChange(maxDate);
      } else {
        const nextDateStr = new Date(nextTime).toISOString().slice(0, 10);
        onDateChange(nextDateStr);
      }
    }, 400);

    return () => clearInterval(interval);
  }, [isPlaying, currentTime, maxTime, maxDate, onDateChange]);

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Number(e.target.value);
    const dateStr = new Date(val).toISOString().slice(0, 10);
    onDateChange(dateStr);
  };

  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 px-3.5 py-2 rounded-xl border border-zinc-800/80 bg-zinc-950/85 backdrop-blur-md shadow-2xl flex items-center gap-3 select-none text-xs">
      <div className="flex items-center gap-1.5 text-zinc-400">
        <Calendar className="h-3.5 w-3.5 text-amber-400" />
        <span className="font-mono text-[11px] text-zinc-300">As of:</span>
        <span className="font-mono font-medium text-[11px] text-amber-300 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/30">
          {currentDate}
        </span>
      </div>

      {/* Play/Pause */}
      <button
        onClick={() => setIsPlaying(!isPlaying)}
        className="p-1 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors cursor-pointer"
        title={isPlaying ? "Pause Timeline" : "Play Timeline Evolution"}
      >
        {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
      </button>

      {/* Range slider */}
      <div className="w-36 sm:w-48 flex items-center">
        <input
          type="range"
          min={minTime}
          max={maxTime}
          step={86400000}
          value={currentTime}
          onChange={handleSliderChange}
          className="w-full accent-amber-500 cursor-pointer h-1 bg-zinc-800 rounded-lg appearance-none"
        />
      </div>

      {/* Reset to latest */}
      <button
        onClick={() => {
          setIsPlaying(false);
          onDateChange(maxDate);
        }}
        className="p-1 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors cursor-pointer"
        title="Reset to Present"
      >
        <RotateCcw className="h-3 w-3" />
      </button>
    </div>
  );
}
