import React, { useCallback, useEffect, useRef, useState } from "react";
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


/* ─────────────────────────── one-screen workspace atoms ───────────────────────────
   The shell used to be nine pages you navigated between; these are the pieces that
   let one screen hold them all: a slide-over drawer, toggle chips, a debounced text
   field that says when it saved, skeletons for the first paint, and the two hooks
   that make focus/visibility survive a reload. */

/** localStorage-backed state. Panel open/closed and drawer width are the two things
 *  nobody wants to set again on every reload — and a corrupt value must not blank
 *  the screen, so every read is guarded. */
export function useSticky<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const [val, setVal] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch { return initial; }
  });
  const set = useCallback((v: T | ((p: T) => T)) => {
    setVal((prev) => {
      const next = typeof v === "function" ? (v as (p: T) => T)(prev) : v;
      try { window.localStorage.setItem(key, JSON.stringify(next)); } catch { /* private mode */ }
      return next;
    });
  }, [key]);
  return [val, set];
}

/** Global shortcuts for the shell. `enabled` keeps the palette from stealing keys
 *  while a modal is open, and typing in a field never triggers a jump. */
export function useHotkeys(map: Record<string, (e: KeyboardEvent) => void>, enabled = true) {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      const combo = `${e.metaKey || e.ctrlKey ? "mod+" : ""}${e.altKey ? "alt+" : ""}${e.shiftKey ? "shift+" : ""}${e.key.toLowerCase()}`;
      const fn = ref.current[combo];
      if (!fn) return;
      // ⌘-combos always win (they cannot be typing); a bare key is ignored while a
      // field has focus, so a digit still types into the box. Escape is the one
      // exception: closing an overlay from inside its search field is the point.
      if (typing && !combo.startsWith("mod+") && e.key !== "Escape") return;
      e.preventDefault();
      fn(e);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}

export const Chip = ({ on, children, onClick, title, kbd, className = "" }: {
  on?: boolean; children: React.ReactNode; onClick?: () => void; title?: string;
  kbd?: string; className?: string;
}) => (
  <button type="button" className={`chip ${on ? "on" : ""} ${className}`} onClick={onClick}
    title={title} data-active={on ? "1" : undefined}>
    <span className="chip-body">{children}</span>
    {kbd ? <kbd>{kbd}</kbd> : null}
  </button>
);

/** Slide-over for everything that is not the current project (settings, team,
 *  history, gallery…). It is a dialog for a11y reasons, so Esc closes it. */
export const Drawer = ({ open, onClose, title, children, width, onWidth, testid }: {
  open: boolean; onClose: () => void; title: React.ReactNode; children: React.ReactNode;
  width: number; onWidth: (w: number) => void; testid?: string;
}) => {
  const drag = useRef<{ x: number; w: number } | null>(null);
  useEffect(() => {
    if (!open) return;
    const move = (e: MouseEvent) => {
      if (!drag.current) return;
      onWidth(Math.max(340, Math.min(900, Math.round(drag.current.w - (e.clientX - drag.current.x)))));
    };
    const up = () => { drag.current = null; document.body.classList.remove("resizing"); };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, [open, onWidth]);
  if (!open) return null;
  return (
    <div className="drawer-scrim" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside className="drawer" style={{ width }} data-testid={testid} role="dialog" aria-modal="true">
        <div className="drawer-grip" title="drag to resize"
          onMouseDown={(e) => { drag.current = { x: e.clientX, w: width }; document.body.classList.add("resizing"); }} />
        <div className="drawer-h spread"><h3>{title}</h3>
          <button className="ghost" onClick={onClose} title="close (Esc)">×</button></div>
        <div className="drawer-b">{children}</div>
      </aside>
    </div>
  );
};

export const Skeleton = ({ rows = 3 }: { rows?: number }) => (
  <div className="skel" aria-hidden="true">
    {Array.from({ length: rows }).map((_, i) => <div key={i} className="skel-row" style={{ width: `${92 - i * 11}%` }} />)}
  </div>
);

/** A label + control that tells you when it wrote to the server. The old forms
 *  changed a value with no feedback, so you could not tell "saved" from "ignored". */
export const Field = ({ label, hint, children, saved, error }: {
  label: string; hint?: string; children: React.ReactNode; saved?: boolean; error?: string;
}) => (
  <label className={`field ${error ? "bad" : ""}`}>
    <span className="field-h"><span>{label}</span>
      {error ? <em className="field-state err">{error}</em>
        : saved ? <em className="field-state ok">saved</em> : null}
    </span>
    {children}
    {hint ? <span className="field-hint">{hint}</span> : null}
  </label>
);

/** Empty state with a reason and the action that fixes it — a bare "no data" is how
 *  a broken feature gets mistaken for an unused one. */
export const Notice = ({ kind = "info", title, children, action }: {
  kind?: "info" | "warn" | "err" | "ok"; title?: React.ReactNode; children?: React.ReactNode; action?: React.ReactNode;
}) => (
  <div className={`notice ${kind}`} role="status">
    <span className="notice-mark">{kind === "ok" ? "✓" : kind === "err" ? "✕" : kind === "warn" ? "⚠" : "ℹ"}</span>
    <div className="notice-body">
      {title ? <b>{title}</b> : null}
      {children ? <div className="notice-text">{children}</div> : null}
    </div>
    {action ? <div className="notice-action">{action}</div> : null}
  </div>
);
