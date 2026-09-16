import React, { useState, useCallback } from "react";

interface ManualControlPanelProps {
  script: string;
  onScriptChange: (script: string) => void;
  scenes: any[];
  selectedScenes: number[];
  onSelectedScenesChange: (indices: number[]) => void;
  defaultAction: string;
  onDefaultActionChange: (action: string) => void;
  defaultEmotion: string;
  onDefaultEmotionChange: (emotion: string) => void;
  defaultVisual: string;
  onDefaultVisualChange: (visual: string) => void;
  defaultBackground: string;
  onDefaultBackgroundChange: (bg: string) => void;
  enabledStages: string[];
  onEnabledStagesChange: (stages: string[]) => void;
  outputFormat: string;
  onOutputFormatChange: (format: string) => void;
  resolution: string;
  onResolutionChange: (res: string) => void;
  fps: number;
  onFpsChange: (fps: number) => void;
  parallelWorkers: number;
  onParallelWorkersChange: (workers: number) => void;
  skipQA: boolean;
  onSkipQAChange: (skip: boolean) => void;
  previewOnly: boolean;
  onPreviewOnlyChange: (preview: boolean) => void;
  onReset: () => void;
  onRun: () => void;
  rvcAvailable?: boolean;
  gpuAvailable?: boolean;
}

const ALL_STAGES = [
  { key: "breakdown", label: "Scene Breakdown", requiresGpu: false },
  { key: "voice_base", label: "Khmer Voice (Edge-TTS)", requiresGpu: false },
  { key: "rvc", label: "RVC Voice Clone", requiresGpu: true },
  { key: "talking_head", label: "Talking Head", requiresGpu: true },
  { key: "video_gen", label: "AI Video Generation", requiresGpu: true },
  { key: "sfx", label: "SFX & Ambience", requiresGpu: false },
  { key: "subtitles", label: "Subtitles (HarfBurn ASS)", requiresGpu: false },
  { key: "qa", label: "QA Gate", requiresGpu: false },
  { key: "assemble", label: "Final Assembly", requiresGpu: false },
];

export function ManualControlPanel({
  script,
  onScriptChange,
  scenes,
  selectedScenes,
  onSelectedScenesChange,
  defaultAction,
  onDefaultActionChange,
  defaultEmotion,
  onDefaultEmotionChange,
  defaultVisual,
  onDefaultVisualChange,
  defaultBackground,
  onDefaultBackgroundChange,
  enabledStages,
  onEnabledStagesChange,
  outputFormat,
  onOutputFormatChange,
  resolution,
  onResolutionChange,
  fps,
  onFpsChange,
  parallelWorkers,
  onParallelWorkersChange,
  skipQA,
  onSkipQAChange,
  previewOnly,
  onPreviewOnlyChange,
  onReset,
  onRun,
  rvcAvailable = false,
  gpuAvailable = false,
}: ManualControlPanelProps) {
  const [autoSplitting, setAutoSplitting] = useState(false);

  const handleAutoSplit = useCallback(() => {
    setAutoSplitting(true);
    // This would trigger a callback to parent to split script into scenes
    setTimeout(() => setAutoSplitting(false), 500);
  }, []);

  const toggleSceneSelection = (idx: number) => {
    if (selectedScenes.includes(idx)) {
      onSelectedScenesChange(selectedScenes.filter((i) => i !== idx));
    } else {
      onSelectedScenesChange([...selectedScenes, idx]);
    }
  };

  const selectAll = () => onSelectedScenesChange(scenes.map((_, i) => i));
  const deselectAll = () => onSelectedScenesChange([]);
  const invertSelection = () => {
    const allIndices = scenes.map((_, i) => i);
    const inverted = allIndices.filter((i) => !selectedScenes.includes(i));
    onSelectedScenesChange(inverted.length === 0 ? allIndices : inverted);
  };

  const toggleStage = (key: string) => {
    if (enabledStages.includes(key)) {
      onEnabledStagesChange(enabledStages.filter((k) => k !== key));
    } else {
      onEnabledStagesChange([...enabledStages, key]);
    }
  };

  return (
    <div style={{
      border: "1px solid #30363d", borderRadius: 8, padding: 16,
      background: "#0d1117", marginBottom: 12
    }}>
      <h3 style={{ margin: "0 0 16px", fontSize: 16 }}>🎛️ MANUAL CONTROL PANEL</h3>

      {/* Script Input */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>📝 Script Input:</div>
        <textarea
          value={script}
          onChange={(e) => onScriptChange(e.target.value)}
          placeholder="Paste your script here - one line per scene"
          rows={4}
          style={{
            width: "100%", padding: 8, fontSize: 12, background: "#161b22",
            border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9", resize: "vertical"
          }}
        />
        <button
          className="btn tiny"
          onClick={handleAutoSplit}
          disabled={autoSplitting || !script.trim()}
          style={{ marginTop: 6 }}
        >
          {autoSplitting ? "Splitting..." : "🔄 Auto-split into scenes"}
        </button>
      </div>

      {/* Scene Selection */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>🎬 Scene Selection:</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
          {scenes.slice(0, 20).map((_, i) => (
            <label key={i} style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
              <input
                type="checkbox"
                checked={selectedScenes.includes(i)}
                onChange={() => toggleSceneSelection(i)}
              />
              Scene {i + 1}
            </label>
          ))}
          {scenes.length > 20 && (
            <span style={{ fontSize: 11, color: "#8b949e" }}>...and {scenes.length - 20} more</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn tiny" onClick={selectAll}>Select All</button>
          <button className="btn tiny" onClick={deselectAll}>Deselect All</button>
          <button className="btn tiny" onClick={invertSelection}>Invert</button>
        </div>
      </div>

      {/* Default Settings */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16
      }}>
        <div>
          <div style={{ fontSize: 11, marginBottom: 4 }}>🎭 Default Action:</div>
          <select
            value={defaultAction}
            onChange={(e) => onDefaultActionChange(e.target.value)}
            style={{ width: "100%", padding: "4px 6px", fontSize: 11, background: "#161b22", border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9" }}
          >
            <option value="talking">talking</option>
            <option value="explaining">explaining</option>
            <option value="thinking">thinking</option>
            <option value="surprised">surprised</option>
            <option value="happy">happy</option>
            <option value="neutral">neutral</option>
          </select>
        </div>
        <div>
          <div style={{ fontSize: 11, marginBottom: 4 }}>🎙️ Default Emotion:</div>
          <select
            value={defaultEmotion}
            onChange={(e) => onDefaultEmotionChange(e.target.value)}
            style={{ width: "100%", padding: "4px 6px", fontSize: 11, background: "#161b22", border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9" }}
          >
            <option value="calm">calm</option>
            <option value="storytelling">storytelling</option>
            <option value="excited">excited</option>
            <option value="emotional">emotional</option>
            <option value="neutral">neutral</option>
          </select>
        </div>
        <div>
          <div style={{ fontSize: 11, marginBottom: 4 }}>🖼️ Default Visual:</div>
          <select
            value={defaultVisual}
            onChange={(e) => onDefaultVisualChange(e.target.value)}
            style={{ width: "100%", padding: "4px 6px", fontSize: 11, background: "#161b22", border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9" }}
          >
            <option value="illustration">illustration</option>
            <option value="character_action">character action</option>
            <option value="meme">meme / reaction</option>
            <option value="generated_video">AI video</option>
          </select>
        </div>
        <div>
          <div style={{ fontSize: 11, marginBottom: 4 }}>⬜ Default Background:</div>
          <select
            value={defaultBackground}
            onChange={(e) => onDefaultBackgroundChange(e.target.value)}
            style={{ width: "100%", padding: "4px 6px", fontSize: 11, background: "#161b22", border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9" }}
          >
            <option value="white_studio">White Studio</option>
            <option value="black_studio">Black Studio</option>
            <option value="gradient">Gradient</option>
            <option value="template">Template</option>
          </select>
        </div>
      </div>

      {/* Pipeline Stages */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>⚙️ Pipeline Stages to Run:</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6 }}>
          {ALL_STAGES.map((stage) => {
            const isDisabled = (stage.requiresGpu && !gpuAvailable) || (stage.key === "rvc" && !rvcAvailable);
            return (
              <label
                key={stage.key}
                style={{
                  fontSize: 11, display: "flex", alignItems: "center", gap: 6,
                  opacity: isDisabled ? 0.5 : 1, cursor: isDisabled ? "not-allowed" : "pointer"
                }}
              >
                <input
                  type="checkbox"
                  checked={enabledStages.includes(stage.key)}
                  onChange={() => !isDisabled && toggleStage(stage.key)}
                  disabled={isDisabled}
                />
                {stage.label}{isDisabled ? " (unavailable)" : ""}
              </label>
            );
          })}
        </div>
      </div>

      {/* Output Settings */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16
      }}>
        <div>
          <div style={{ fontSize: 11, marginBottom: 4 }}>Format:</div>
          <select
            value={outputFormat}
            onChange={(e) => onOutputFormatChange(e.target.value)}
            style={{ width: "100%", padding: "4px 6px", fontSize: 11, background: "#161b22", border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9" }}
          >
            <option value="mp4">MP4</option>
            <option value="webm">WebM</option>
          </select>
        </div>
        <div>
          <div style={{ fontSize: 11, marginBottom: 4 }}>Resolution:</div>
          <select
            value={resolution}
            onChange={(e) => onResolutionChange(e.target.value)}
            style={{ width: "100%", padding: "4px 6px", fontSize: 11, background: "#161b22", border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9" }}
          >
            <option value="720x1280">720x1280 (Vertical)</option>
            <option value="1080x1920">1080x1920 (Full HD Vertical)</option>
            <option value="1280x720">1280x720 (Horizontal)</option>
            <option value="1920x1080">1920x1080 (Full HD Horizontal)</option>
          </select>
        </div>
        <div>
          <div style={{ fontSize: 11, marginBottom: 4 }}>FPS:</div>
          <select
            value={fps}
            onChange={(e) => onFpsChange(Number(e.target.value))}
            style={{ width: "100%", padding: "4px 6px", fontSize: 11, background: "#161b22", border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9" }}
          >
            <option value={24}>24</option>
            <option value={30}>30</option>
            <option value={60}>60</option>
          </select>
        </div>
        <div>
          <div style={{ fontSize: 11, marginBottom: 4 }}>Audio:</div>
          <select
            value="44.1kHz"
            onChange={() => {}}
            style={{ width: "100%", padding: "4px 6px", fontSize: 11, background: "#161b22", border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9" }}
          >
            <option value="44.1kHz">44.1kHz</option>
            <option value="48kHz">48kHz</option>
          </select>
        </div>
      </div>

      {/* Performance */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>⚡ Performance:</div>
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}>
            Parallel workers:
            <select
              value={parallelWorkers}
              onChange={(e) => onParallelWorkersChange(Number(e.target.value))}
              style={{ padding: "4px 6px", fontSize: 11, background: "#161b22", border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9" }}
            >
              <option value={1}>1</option>
              <option value={2}>2</option>
              <option value={4}>4</option>
            </select>
          </label>
          <label style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}>
            <input
              type="checkbox"
              checked={skipQA}
              onChange={(e) => onSkipQAChange(e.target.checked)}
            />
            Skip QA (faster)
          </label>
          <label style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}>
            <input
              type="checkbox"
              checked={previewOnly}
              onChange={(e) => onPreviewOnlyChange(e.target.checked)}
            />
            Preview only (first 3 scenes)
          </label>
        </div>
      </div>

      {/* Action Buttons */}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button className="btn" onClick={onReset}>🔄 Reset to Defaults</button>
        <button className="btn primary" onClick={onRun}>▶ RUN SELECTED</button>
      </div>
    </div>
  );
}
