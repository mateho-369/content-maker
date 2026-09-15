import React from "react";
import { StatusPayload, TtsVoiceStatus } from "./api";

// Verbatim user-facing copy for the Khmer-voice status badge.
export const TTS_NATIVE_TEXT = "✅ Native Khmer Voice (Meta MMS VITS) Active";
export const TTS_PLACEHOLDER_TEXT =
  "⚠️ Placeholder Audio Active. Please run 2_SETUP_KHMER_TTS.bat to enable real Khmer voice.";

export function ttsVoiceText(tts?: TtsVoiceStatus | null): string {
  return tts?.native_voice ? TTS_NATIVE_TEXT : TTS_PLACEHOLDER_TEXT;
}

/**
 * Green/yellow indicator for whether the real Meta MMS VITS Khmer voice is
 * installed. `pill` is the compact topbar version (full text in its tooltip);
 * `banner` is the full-width dashboard/settings panel.
 */
export const TtsVoiceBadge = ({ status, variant = "pill" }: {
  status?: StatusPayload | null; variant?: "pill" | "banner";
}) => {
  const tts = status?.tts;
  if (!tts) return null;
  const native = tts.native_voice;
  const setup = tts.setup_script || "2_SETUP_KHMER_TTS.bat";
  const render = tts.render_script || "3_RENDER_ALL_VIDEOS.bat";
  const title = ttsVoiceText(tts);

  if (variant === "banner") {
    return (
      <div className={`voice-banner ${native ? "ok" : "warn"}`} role="status">
        <span className="voice-dot" />
        <div className="grow">
          <b>{title}</b>
          <div className="voice-sub">
            {native ? (
              <>
                VITS model: <code>{tts.model || tts.model_dir || "model.onnx"}</code>
                {tts.model_bytes ? ` · ${(tts.model_bytes / 1e6).toFixed(0)} MB` : ""}
                {!tts.ready && (
                  <>
                    {" "}— model found, but it is not fully usable yet
                    {!tts.tokens_present && " (tokens.txt missing)"}
                    {!tts.runtime_python && !tts.runtime_cli && " (sherpa-onnx runtime missing)"}
                    ; re-run <code>{setup}</code>.
                  </>
                )}
              </>
            ) : (
              <>
                Renders currently use speech-shaped placeholder audio (“តុកៗ”), not a real Khmer
                voice. Run <code>{setup}</code> once to download the Meta MMS VITS model, then run{" "}
                <code>{render}</code> to re-render with the native voice. Expected at{" "}
                <code>models/tts/vits-mms-khm/model.onnx</code> inside the studio data folder.
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <span className={`voice-pill ${native ? "ok" : "warn"}`} title={title} role="status">
      <span className="voice-dot" />
      {native ? "Khmer voice · native" : "Khmer voice · placeholder"}
    </span>
  );
};

export const Panel = ({ title, right, children, className = "", scroll }: {
  title?: React.ReactNode; right?: React.ReactNode; children?: React.ReactNode;
  className?: string; scroll?: boolean;
}) => (
  <div className={`panel ${className}`}>
    {title !== undefined && (
      <div className="panel-h"><h3>{title}</h3>{right}</div>
    )}
    <div className={scroll ? "panel-scroll" : ""}>{children}</div>
  </div>
);

export const Badge = ({ kind = "", children, title }: { kind?: string; children: React.ReactNode; title?: string }) => (
  <span className={`badge ${kind}`} title={title}>{children}</span>
);

export const Bar = ({ pct }: { pct: number }) => (
  <div className="bar"><div style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} /></div>
);

export const Modal = ({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) => (
  <div className="modal-wrap" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="modal">
      <div className="panel-h"><h3>{title}</h3>
        <button className="ghost" onClick={onClose}>×</button></div>
      <div className="panel-b">{children}</div>
    </div>
  </div>
);

export const Spinner = () => <span className="spin" />;

export const fmtDur = (s?: number | null) => {
  if (!s && s !== 0) return "—";
  const m = Math.floor(s / 60), sec = s - m * 60;
  return m ? `${m}m ${sec.toFixed(1)}s` : `${sec.toFixed(1)}s`;
};
export const fmtSize = (b?: number) => {
  if (!b) return "0 B";
  if (b > 1e9) return `${(b / 1e9).toFixed(2)} GB`;
  if (b > 1e6) return `${(b / 1e6).toFixed(1)} MB`;
  if (b > 1e3) return `${(b / 1e3).toFixed(0)} KB`;
  return `${b} B`;
};
export const fmtTime = (ts?: number) => (ts ? new Date(ts * 1000).toLocaleString() : "—");

export const StatusBadge = ({ status }: { status: string }) => {
  const map: Record<string, [string, string]> = {
    done: ["ok", "done"], completed: ["ok", "completed"], running: ["warn", "running"],
    queued: ["", "queued"], paused: ["warn", "paused"], failed: ["err", "failed"],
    skipped: ["", "skipped"], deferred: ["", "deferred"], blocked: ["err", "blocked"],
    review: ["warn", "review"], ready: ["blue", "ready"], draft: ["", "draft"],
    needs_review: ["warn", "needs approval"], cancelled: ["err", "cancelled"],
  };
  const [k, label] = map[status] || ["", status];
  return <Badge kind={k}>{label}</Badge>;
};

export const Empty = ({ text }: { text: string }) => (
  <div className="hint" style={{ padding: 14, textAlign: "center" }}>{text}</div>
);
