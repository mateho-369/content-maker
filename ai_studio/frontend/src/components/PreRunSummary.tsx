import React, { useState } from "react";

interface PreRunSummaryProps {
  mode: string;
  totalScenes: number;
  selectedScenes: number[];
  enabledStages: string[];
  totalStages: string[];
  background?: any;
  voice?: string;
  estimatedTime?: string;
  estimatedSize?: string;
  skippedItems?: string[];
  onCancel: () => void;
  onEdit: () => void;
  onRun: () => void;
}

export function PreRunSummary({
  mode,
  totalScenes,
  selectedScenes,
  enabledStages,
  totalStages,
  background,
  voice,
  estimatedTime,
  estimatedSize,
  skippedItems,
  onCancel,
  onEdit,
  onRun,
}: PreRunSummaryProps) {
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center"
    }}>
      <div style={{
        background: "#0d1117", border: "1px solid #30363d", borderRadius: 8,
        padding: 20, width: 480, maxWidth: "90vw", boxShadow: "0 8px 32px rgba(0,0,0,0.4)"
      }}>
        <h3 style={{ margin: "0 0 16px", fontSize: 18 }}>📋 RUN SUMMARY</h3>
        
        <div style={{ fontSize: 13, lineHeight: 1.8 }}>
          <div><b>Mode:</b> {mode === "manual" ? "🎛️ MANUAL" : "🤖 AUTO"}</div>
          <div><b>Scenes:</b> {selectedScenes.length} of {totalScenes} selected</div>
          <div><b>Stages:</b> {enabledStages.length} of {totalStages.length} enabled</div>
          <div><b>Background:</b> {background?.type || "White Studio"}</div>
          <div><b>Voice:</b> {voice || "Edge-TTS (km-KH-PisethNeural)"}</div>
          <div><b>Estimated time:</b> ~{estimatedTime || "2 minutes"}</div>
          <div><b>Estimated size:</b> ~{estimatedSize || "35 MB"}</div>
        </div>

        {skippedItems && skippedItems.length > 0 && (
          <div style={{ marginTop: 12, padding: 8, background: "#2e2a1d", borderRadius: 4, fontSize: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>⚠️ Will SKIP:</div>
            <ul style={{ margin: 0, paddingLeft: 16, color: "#c9d1d9" }}>
              {skippedItems.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        )}

        <div style={{ marginTop: 20, display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button className="btn warn" onClick={onEdit}>◀ Edit Settings</button>
          <button className="btn primary" onClick={onRun}>▶ RUN</button>
        </div>
      </div>
    </div>
  );
}
