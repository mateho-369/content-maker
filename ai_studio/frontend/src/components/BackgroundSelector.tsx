import React, { useState } from "react";

export type BackgroundType = "white_studio" | "black_studio" | "gradient" | "image" | "ai_generated" | "template";

export interface BackgroundChoice {
  type: BackgroundType;
  gradient_start?: string;
  gradient_end?: string;
  image_path?: string;
  ai_prompt?: string;
  template_name?: string;
}

interface BackgroundSelectorProps {
  value?: BackgroundChoice;
  onChange: (bg: BackgroundChoice) => void;
  compact?: boolean;
}

const BACKGROUND_TEMPLATES = [
  { key: "studio", label: "Studio", desc: "Clean professional look" },
  { key: "nature", label: "Nature", desc: "Green/organic backgrounds" },
  { key: "city", label: "City", desc: "Urban environments" },
  { key: "abstract", label: "Abstract", desc: "Artistic patterns" },
  { key: "music", label: "Music", desc: "Audio-themed visuals" },
];

export function BackgroundSelector({ value, onChange, compact = false }: BackgroundSelectorProps) {
  const [selectedType, setSelectedType] = useState<BackgroundType>(value?.type || "white_studio");

  const updateValue = (partial: Partial<BackgroundChoice>) => {
    onChange({ ...value, type: selectedType, ...partial });
  };

  return (
    <div style={{ border: "1px solid #30363d", borderRadius: 6, padding: compact ? 8 : 12, background: "#0d1117" }}>
      {!compact && <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>🖼️ Background Selection</div>}
      
      <div style={{ display: "grid", gridTemplateColumns: compact ? "repeat(3, 1fr)" : "repeat(6, 1fr)", gap: 6, marginBottom: 10 }}>
        <button
          className={`btn tiny ${selectedType === "white_studio" ? "primary" : ""}`}
          onClick={() => { setSelectedType("white_studio"); updateValue({ type: "white_studio" }); }}
          title="White Studio - Clean, professional">
          ⬜ White
        </button>
        <button
          className={`btn tiny ${selectedType === "black_studio" ? "primary" : ""}`}
          onClick={() => { setSelectedType("black_studio"); updateValue({ type: "black_studio" }); }}
          title="Black Studio - Dramatic, cinematic">
          ⬛ Black
        </button>
        <button
          className={`btn tiny ${selectedType === "gradient" ? "primary" : ""}`}
          onClick={() => { setSelectedType("gradient"); updateValue({ type: "gradient", gradient_start: "#4a90d9", gradient_end: "#67b26f" }); }}
          title="Gradient - Customizable colors">
          🎨 Gradient
        </button>
        <button
          className={`btn tiny ${selectedType === "image" ? "primary" : ""}`}
          onClick={() => { setSelectedType("image"); updateValue({ type: "image" }); }}
          title="Custom Image Upload">
          🖼️ Upload
        </button>
        <button
          className={`btn tiny ${selectedType === "ai_generated" ? "primary" : ""}`}
          onClick={() => { setSelectedType("ai_generated"); updateValue({ type: "ai_generated", ai_prompt: "" }); }}
          title="AI Generated from prompt">
          🤖 AI Generate
        </button>
        <button
          className={`btn tiny ${selectedType === "template" ? "primary" : ""}`}
          onClick={() => { setSelectedType("template"); updateValue({ type: "template", template_name: "studio" }); }}
          title="Template backgrounds">
          📦 Template
        </button>
      </div>

      {selectedType === "gradient" && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
          <label style={{ fontSize: 11 }}>Start:</label>
          <input
            type="color"
            value={value?.gradient_start || "#4a90d9"}
            onChange={(e) => updateValue({ gradient_start: e.target.value })}
            style={{ width: 40, height: 24, border: "none", cursor: "pointer" }}
          />
          <label style={{ fontSize: 11, marginLeft: 8 }}>End:</label>
          <input
            type="color"
            value={value?.gradient_end || "#67b26f"}
            onChange={(e) => updateValue({ gradient_end: e.target.value })}
            style={{ width: 40, height: 24, border: "none", cursor: "pointer" }}
          />
          <span style={{ fontSize: 11, color: "#8b949e" }}>
            {value?.gradient_start} → {value?.gradient_end}
          </span>
        </div>
      )}

      {selectedType === "image" && (
        <div style={{ marginTop: 8 }}>
          <input
            type="file"
            accept="image/*"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                // In a real implementation, this would upload the file
                updateValue({ image_path: `uploaded:${file.name}` });
              }
            }}
            style={{ fontSize: 11 }}
          />
          {value?.image_path && (
            <div style={{ fontSize: 11, color: "#8b949e", marginTop: 4 }}>Selected: {value.image_path}</div>
          )}
        </div>
      )}

      {selectedType === "ai_generated" && (
        <div style={{ marginTop: 8 }}>
          <input
            type="text"
            placeholder="Describe the background you want (e.g., 'sunset over mountains')"
            value={value?.ai_prompt || ""}
            onChange={(e) => updateValue({ ai_prompt: e.target.value })}
            style={{ width: "100%", padding: "6px 8px", fontSize: 12, background: "#161b22", border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9" }}
          />
        </div>
      )}

      {selectedType === "template" && (
        <div style={{ marginTop: 8 }}>
          <select
            value={value?.template_name || "studio"}
            onChange={(e) => updateValue({ template_name: e.target.value })}
            style={{ width: "100%", padding: "6px 8px", fontSize: 12, background: "#161b22", border: "1px solid #30363d", borderRadius: 4, color: "#c9d1d9" }}
          >
            {BACKGROUND_TEMPLATES.map((t) => (
              <option key={t.key} value={t.key}>{t.label} — {t.desc}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
