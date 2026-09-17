import React, { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { useToast, errText } from "./main";

/**
 * Background picker — the control behind "choose White Studio vs Black Studio".
 *
 * Nothing about background vocabulary is hardcoded here: `GET /api/backgrounds`
 * returns the catalog (types, the inputs each type reveals, their defaults) and
 * the tiles are the *rendered* plate from `GET /api/backgrounds/preview`, i.e.
 * the same code path the video renderer uses. A new background type is one dict
 * in `ai_studio/backgrounds.py`, and this component shows it with no edit.
 *
 * The value it emits is what the pipeline reads: `settings.background` on the
 * project, or `scene.meta.background` for a per-scene override.
 */
export interface Bg {
  type?: string; template?: string; a?: string; b?: string;
  path?: string; prompt?: string; seed?: number;
}

interface BgField {
  name: string; label: string; kind: string; default?: any; accept?: string;
}

interface BgType {
  key: string; label: string; emoji: string; one_liner?: string; note?: string;
  /** what still has to be filled in before this type is a usable background */
  needs?: string;
  fields?: BgField[]; default?: Bg;
}

interface Catalog {
  default?: Bg; types?: BgType[];
  templates?: { key: string; label: string; emoji?: string; one_liner?: string }[];
  error?: string;
}

export function backgroundLabel(bg: Bg | null | undefined, cat?: Catalog): string {
  if (!bg || !bg.type) {
    // "unset" is not white — it is whatever the catalog says the default is, which
    // today is the scene's own palette (backgrounds.label() calls it "auto")
    const d = cat?.default?.type;
    if (!d) return "project default";
    const t = (cat?.types || []).find((x) => x.key === d);
    return t ? `${t.emoji} ${t.label} (project default)` : `${d} (project default)`;
  }
  const t = (cat?.types || []).find((x) => x.key === bg.type);
  const base = t ? `${t.emoji || ""} ${t.label}` : bg.type;
  if (bg.type === "template" && bg.template) {
    const tp = (cat?.templates || []).find((x) => x.key === bg.template);
    return `🎨 ${tp ? tp.label : bg.template}`;
  }
  if (bg.type === "image") return `🖼️ ${String(bg.path || "").split("/").pop() || "no image yet"}`;
  if (bg.type === "ai_prompt") return `🤖 ${String(bg.prompt || "no prompt yet").slice(0, 34)}`;
  return base;
}

/** Preview URL for a value — the plate as the renderer will actually paint it. */
export function backgroundPreviewUrl(bg: Bg, w = 200, h = 356): string {
  const q = new URLSearchParams({ type: bg.type || "white_studio", width: String(w), height: String(h) });
  if (bg.template) q.set("template", bg.template);
  if (bg.a) q.set("a", bg.a);
  if (bg.b) q.set("b", bg.b);
  return `/api/backgrounds/preview?${q.toString()}`;
}

/** Small swatch for a board row / the summary modal. */
export function BackgroundChip({ bg, size = 26 }: { bg?: Bg | null; size?: number }) {
  if (!bg || !bg.type) {
    return (
      <span className="bgchip" title="no background of its own — inherits the project setting"
        style={{ width: size, height: size }}>↩</span>
    );
  }
  const imgable = !["image", "ai_prompt"].includes(bg.type);
  return (
    <span className="bgchip" title={backgroundLabel(bg)} style={{ width: size, height: size }}>
      {imgable
        ? <img src={backgroundPreviewUrl({ ...bg, type: bg.type === "template" ? "template" : bg.type,
                                          template: bg.template }, 80, 80)} alt="" />
        : <span style={{ fontSize: Math.round(size * 0.45) }}>{bg.type === "image" ? "🖼️" : "🤖"}</span>}
    </span>
  );
}

export function BackgroundPicker({ value, onChange, projectId = "", dense = false }: {
  value?: Bg | null;
  onChange: (next: Bg) => void;
  projectId?: string;
  dense?: boolean;
}) {
  const toast = useToast();
  const [cat, setCat] = useState<Catalog | null>(null);
  const [busy, setBusy] = useState("");
  const cur = value || {};

  useEffect(() => {
    api<Catalog>(`/backgrounds${projectId ? `?project_id=${projectId}` : ""}`)
      .then(setCat)
      .catch((e) => setCat({ error: errText(e), types: [], templates: [] }));
  }, [projectId]);

  const types = cat?.types || [];
  const selected = types.find((t) => t.key === cur.type);
  const fields = useMemo(() => selected?.fields || [], [selected]);

  const setField = (name: string, v: any) => onChange({ ...cur, [name]: v });
  const pickType = (t: BgType) => {
    // choosing a type keeps whatever the user already typed for it
    const keep: Bg = { ...(t.default || { type: t.key }) };
    fields.filter((f) => cur[f.name] !== undefined).forEach((f) => { keep[f.name] = cur[f.name]; });
    keep.type = t.key;
    if (t.key === "template" && !keep.template) keep.template = cat?.templates?.[0]?.key || "studio";
    onChange(keep);
  };

  const upload = async (f: File) => {
    setBusy("upload");
    const fd = new FormData();
    fd.append("file", f);
    if (projectId) fd.append("project_id", projectId);
    try {
      const r = await api<{ background: Bg; note?: string }>("/backgrounds/upload", { method: "POST", form: fd });
      onChange({ ...r.background, prompt: cur.prompt, seed: cur.seed });
      toast(r.note || "plate stored on the server", "ok");
    } catch (e) { toast(errText(e), "err"); }
    setBusy("");
  };

  if (cat?.error) return <div className="errbar">⚠ backgrounds unavailable: {cat.error}</div>;
  if (!cat) return <div className="hint">loading backgrounds…</div>;

  return (
    <div className="bgpick" data-testid="background-picker">
      <div className={`bgpick-grid ${dense ? "dense" : ""}`}>
        {types.map((t) => {
          const on = cur.type === t.key;
          return (
            <button key={t.key} type="button" className={`bgtile ${on ? "on" : ""} ${t.needs ? "needs" : ""}`}
              title={[t.one_liner, t.note, t.needs].filter(Boolean).join(" · ")} onClick={() => pickType(t)}
              data-testid={`bg-${t.key}`}>
              {t.needs ? <span className="bgtile-flag">
                needs {t.needs.includes("upload") ? "an upload" : t.needs.includes("prompt") ? "a prompt" : "input"}
              </span> : null}
              <img className="bgtile-img" alt="" loading="lazy"
                src={backgroundPreviewUrl({ ...(t.default || { type: t.key }), type: t.key }, 160, 220)} />
              <span className="bgtile-cap"><span>{t.emoji}</span> {t.label}</span>
            </button>
          );
        })}
      </div>

      {selected?.needs ? (
        <div className="hint bgneeds" style={{ fontSize: 10.5, marginTop: 5 }}>⚠ {selected.needs}</div>
      ) : null}
      {cur.type === "template" && (
        <div className="row" style={{ gap: 4, marginTop: 6, flexWrap: "wrap" }}>
          {(cat.templates || []).map((tp) => (
            <button key={tp.key} type="button" className={`btn tiny ${cur.template === tp.key ? "primary" : ""}`}
              title={tp.one_liner} onClick={() => onChange({ ...cur, template: tp.key })}>
              {tp.emoji} {tp.label}
            </button>
          ))}
        </div>
      )}

      {fields.length > 0 && (
        <div className="row bgpick-fields" style={{ gap: 6, marginTop: 6, flexWrap: "wrap" }}>
          {fields.map((f) => {
            if (f.kind === "color") {
              return (
                <label key={f.name} className="bgfield">
                  <span>{f.label}</span>
                  <input type="color" value={/^\#[0-9a-f]{6}$/i.test(String(cur[f.name] ?? f.default)) ? String(cur[f.name] ?? f.default) : "#000000"}
                    onChange={(e) => setField(f.name, e.target.value)} />
                </label>
              );
            }
            if (f.kind === "upload") {
              return (
                <label key={f.name} className="bgfield">
                  <span>{f.label}</span>
                  <span className="row" style={{ gap: 4 }}>
                    <button type="button" className="btn tiny" disabled={!!busy} onClick={() => {
                      const i = document.createElement("input");
                      i.type = "file"; i.accept = f.accept || "image/*";
                      i.onchange = () => i.files?.[0] && upload(i.files[0]);
                      i.click();
                    }}>{busy === "upload" ? "uploading…" : "⬆ choose image"}</button>
                    <code style={{ fontSize: 10 }}>{String(cur.path || "").split("/").pop() || "none"}</code>
                  </span>
                </label>
              );
            }
            if (f.kind === "choice") {
              // `template` is the one choice field, and it is already rendered as a
              // grid of the six built-in plates right above — no duplicate control
              if (f.name === "template") return null;
              const opts = [];
              return (
                <label key={f.name} className="bgfield">
                  <span>{f.label}</span>
                  <select value={String(cur[f.name] ?? "")}
                    onChange={(e) => setField(f.name, e.target.value)}>
                    {opts.map((o) => <option key={o.key} value={o.key}>{o.emoji} {o.label}</option>)}
                  </select>
                </label>
              );
            }
            if (f.kind === "number") {
              return (
                <label key={f.name} className="bgfield">
                  <span>{f.label}</span>
                  <input type="number" value={Number(cur[f.name] ?? f.default ?? 0)}
                    onChange={(e) => setField(f.name, Number(e.target.value) || 0)} />
                </label>
              );
            }
            return (
              <label key={f.name} className="bgfield" style={{ flex: "1 1 220px" }}>
                <span>{f.label}</span>
                <input className="input" placeholder="clean, low-detail backdrop that leaves room for the subject"
                  value={String(cur[f.name] ?? f.default ?? "")}
                  onChange={(e) => setField(f.name, e.target.value)} />
              </label>
            );
          })}
          {cur.type === "ai_prompt" && (
            <div className="hint" style={{ flexBasis: "100%", fontSize: 10 }}>
              the plate is drawn once by the image engine, cached under the project, and reused for
              every frame — the seed pins it so a re-render gives the same room.
            </div>
          )}
        </div>
      )}

      <div className="row" style={{ gap: 6, marginTop: 6, justifyContent: "space-between" }}>
        {selected?.note ? (
          <span className="hint" style={{ fontSize: 10, color: "var(--warn, #f0b754)" }}>
            ⚠ {selected?.note}
          </span>
        ) : (
        <span className="hint" style={{ fontSize: 10 }}>
          {backgroundLabel(cur, cat)} · applies to every scene that has no background of its own
        </span>)}
        {cur.type ? (
          <button type="button" className="btn tiny" title="back to the project default"
            onClick={() => onChange({})}>use project default</button>
        ) : null}
      </div>
    </div>
  );
}
