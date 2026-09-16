import React from "react";

interface LiveProgressProps {
  currentScene?: number;
  totalScenes?: number;
  sceneText?: string;
  stageName?: string;
  progressPct?: number;
  overallPct?: number;
  elapsedSec?: number;
  etaSec?: number;
  speedPerMin?: number;
  status?: string;
  onPause?: () => void;
  onSkip?: () => void;
  onCancel?: () => void;
}

export function LiveProgress({
  currentScene = 1,
  totalScenes = 10,
  sceneText = "",
  stageName = "",
  progressPct = 0,
  overallPct = 0,
  elapsedSec = 0,
  etaSec = 0,
  speedPerMin = 0,
  status = "running",
  onPause,
  onSkip,
  onCancel,
}: LiveProgressProps) {
  const formatTime = (sec: number) => {
    if (sec < 60) return `${Math.round(sec)}s`;
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return `${m}m ${s}s`;
  };

  return (
    <div style={{
      border: "1px solid #30363d", borderRadius: 8, padding: 16,
      background: "#0d1117", marginBottom: 12
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>
        🎬 Rendering Scene {currentScene}/{totalScenes}: "{sceneText?.slice(0, 40) || "..."}"
      </div>

      {/* Scene Progress Bar */}
      <div style={{
        height: 20, background: "#161b22", borderRadius: 4, overflow: "hidden",
        marginBottom: 8, position: "relative"
      }}>
        <div style={{
          width: `${progressPct}%`, height: "100%",
          background: "linear-gradient(90deg, #238636, #2ea043)",
          transition: "width 0.3s ease"
        }} />
        <div style={{
          position: "absolute", inset: 0, display: "flex", alignItems: "center",
          justifyContent: "center", fontSize: 11, fontWeight: 600, color: "#c9d1d9"
        }}>
          {Math.round(progressPct)}%
        </div>
      </div>

      {/* Stage Info */}
      <div style={{ fontSize: 12, color: "#8b949e", marginBottom: 8 }}>
        Stage: {stageName || "Initializing..."}
      </div>

      {/* Stats Row */}
      <div style={{
        display: "flex", gap: 16, fontSize: 11, color: "#8b949e", marginBottom: 8
      }}>
        <span>Elapsed: {formatTime(elapsedSec)}</span>
        <span>ETA: {formatTime(etaSec)} remaining</span>
        <span>Speed: {speedPerMin.toFixed(1)} scenes/min</span>
      </div>

      {/* Action Buttons */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {onPause && (
          <button className="btn tiny" onClick={onPause} disabled={status !== "running"}>
            ⏸ Pause
          </button>
        )}
        {onSkip && (
          <button className="btn tiny" onClick={onSkip}>
            ⏭ Skip Scene
          </button>
        )}
        {onCancel && (
          <button className="btn tiny warn" onClick={onCancel}>
            ✖ Cancel
          </button>
        )}
      </div>

      {/* Overall Progress */}
      <div style={{ fontSize: 12, marginBottom: 4 }}>Overall Progress:</div>
      <div style={{ height: 12, background: "#161b22", borderRadius: 4, overflow: "hidden" }}>
        <div style={{
          width: `${overallPct}%`, height: "100%",
          background: "linear-gradient(90deg, #1f6feb, #388bfd)",
          transition: "width 0.3s ease"
        }} />
      </div>
      <div style={{ textAlign: "right", fontSize: 11, color: "#8b949e", marginTop: 2 }}>
        {Math.round(overallPct)}%
      </div>
    </div>
  );
}
