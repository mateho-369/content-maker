import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { errText, useToast } from "../main";
import { Badge, Chip, Field, Notice, Panel, Skeleton } from "../ui";

/**
 * Assets: the two things the deleted :8001/:8002 pages used to own, now inside the
 * one workspace — open-licence still hunting and the shared SFX folder.
 *
 * Both cards write through the SAME fields the render reads (`scene.meta.image`
 * custom still, `scene.sfx_prompt`), so a pick here changes the pixels/wav and not
 * just this panel. Where a capability is missing on this machine the panel says so
 * instead of showing a grid of nothing.
 */

interface Found {
  found: boolean; file?: string; url?: string; query: string; source?: string; note?: string;
}
interface Sfx { name: string; desc: string; builtin: boolean; url: string }

export function AssetsPanel({ projectId, scenes, selScene, onAssigned }: {
  projectId: string; scenes: any[]; selScene: number; onAssigned?: () => void;
}) {
  const [hits, setHits] = useState<Found[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState("");
  const [sfx, setSfx] = useState<Sfx[] | null>(null);
  const [sfxDir, setSfxDir] = useState("");
  const [sfxErr, setSfxErr] = useState("");
  const [playing, setPlaying] = useState("");
  const audio = useRef<HTMLAudioElement | null>(null);
  const toast = useToast();
  const scene = scenes[selScene];

  useEffect(() => () => { audio.current?.pause(); }, []);

  const search = async () => {
    const query = q.trim();
    if (!query) { toast("type what the still should show", "warn"); return; }
    setBusy("search");
    try {
      const r = await api<Found>("/images/search", { method: "POST", json: { query } });
      setHits((h) => [r, ...h.filter((x) => x.query !== r.query)].slice(0, 24));
      if (!r.found) toast(r.note || "nothing came back for that phrase", "warn");
    } catch (e) { toast(errText(e), "err"); }
    setBusy("");
  };

  const useForScene = async (f: Found) => {
    if (!scene) { toast("pick a row on the board first — the still goes on that scene", "warn"); return; }
    setBusy("assign");
    try {
      const r = await api<{ note?: string }>(`/projects/${projectId}/scenes/${scene.idx ?? selScene}/image-cache`,
        { method: "POST", json: { file: f.file } });
      toast(r.note || "scene still set", "ok");
      onAssigned?.();
    } catch (e) { toast(errText(e), "err"); }
    setBusy("");
  };

  const assignSfx = async (s: Sfx) => {
    if (!scene) { toast("pick a row on the board first", "warn"); return; }
    const idx = scene.idx ?? selScene;
    setBusy("sfx");
    try {
      // POST /scenes REPLACES the board, so this reads it back first and sends the
      // whole list with one field changed — a partial body would drop every other
      // scene, which is exactly the kind of "editing one row lost the others" bug
      // this app has a test file for.
      const fresh = await api<{ scenes: any[] }>(`/projects/${projectId}/scenes`);
      const rows = (fresh.scenes || []).map((r) => (
        (r.idx ?? 0) === idx ? { ...r, idx: undefined, sfx_prompt: s.name } : { ...r, idx: undefined }
      ));
      if (!rows.some((r) => (r.sfx_prompt || "") === s.name)) {
        toast("the row disappeared while saving — nothing was written", "warn");
        onAssigned?.(); setBusy(""); return;
      }
      await api(`/projects/${projectId}/scenes`, { method: "POST", json: { scenes: rows } });
      toast(`scene ${idx + 1} will use “${s.name}” on the next sfx stage`, "ok");
      onAssigned?.();
    } catch (e) { toast(errText(e), "err"); }
    setBusy("");
  };

  const loadSfx = useCallback(async () => {
    try {
      const r = await api<{ dir: string; sfx: Sfx[] }>("/sfx");
      setSfx(r.sfx || []); setSfxDir(r.dir || ""); setSfxErr("");
    } catch (e) { setSfx([]); setSfxErr(errText(e)); }
  }, []);
  useEffect(() => { loadSfx(); }, [loadSfx]);

  const play = (s: Sfx) => {
    audio.current?.pause();
    if (playing === s.name) { setPlaying(""); return; }
    const a = new Audio(s.url);
    a.onended = () => setPlaying("");
    a.play().catch(() => toast("this browser blocked the sound — use the download link", "warn"));
    audio.current = a;
    setPlaying(s.name);
  };

  return (
    <div className="assets-grid">
      <Panel title="🖼 Supporting stills (open licence)" className="asset-card">
        <Field label="what should the picture show" hint="only Creative-Commons / public-domain results are kept, cached under the studio data folder">
          <div className="row" style={{ gap: 6 }}>
            <input className="input" placeholder="e.g. farmer checking rice leaves at dawn" value={q}
              onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") search(); }} />
            <button className="btn primary" disabled={!!busy} onClick={search} data-testid="img-search">
              {busy === "search" ? <Skeleton rows={1} /> : "search"}
            </button>
          </div>
        </Field>
        {busy === "assign" ? <Skeleton rows={1} /> : null}
        {hits.length === 0 ? (
          <Notice kind="info" title="nothing searched yet">
            A search returns one still, because that is what a scene needs. “🤖 placeholder” means the
            web was unreachable and the engine drew one locally — it is labelled, never passed off as found.
          </Notice>
        ) : (
          <div className="hitgrid" data-testid="img-hits">
            {hits.map((h, i) => (
              <figure key={i} className="hit">
                {h.found ? <img src={h.url} alt={h.query} loading="lazy" />
                  : <div className="hit-miss">✕<span>{h.note || "no image"}</span></div>}
                <figcaption>
                  <span className="hint">{h.query.slice(0, 40)}</span>
                  <Badge kind={h.source === "ai" ? "warn" : ""}>{h.source === "ai" ? "🤖 placeholder" : "cc found"}</Badge>
                </figcaption>
                {h.found ? (
                  <button className="btn tiny" disabled={!!busy} onClick={() => useForScene(h)}
                    title={scene ? `write this as the still for scene ${(scene.idx ?? selScene) + 1}` : "select a board row first"}
                    data-testid={`img-use-${i}`}>
                    use for scene {(scene?.idx ?? selScene) + 1}
                  </button>
                ) : null}
              </figure>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="🔊 Sound effects" className="asset-card"
        right={<Chip onClick={loadSfx} title="re-read the folder">⟳</Chip>}>
        {sfx === null ? <Skeleton rows={4} /> : sfxErr ? (
          <Notice kind="err" title="the sfx library is unreachable">{sfxErr}</Notice>
        ) : sfx.length === 0 ? (
          <Notice kind="warn" title="no sounds in the folder">
            the render would fall back to its procedural ambience too
          </Notice>
        ) : (
          <>
            <div className="hint" style={{ marginBottom: 6 }}>
              {sfx.length} sounds in <code>{sfxDir.split(/[\\/]/).slice(-1)[0]}</code> — clicking one writes
              <b> sfx_prompt</b> on {scene ? `scene ${(scene.idx ?? selScene) + 1}` : "the selected scene"},
              which is the field the render reads.
            </div>
            <div className="sfxlist" data-testid="sfx-list">
              {sfx.map((s) => (
                <div key={s.name} className={`sfxrow ${playing === s.name ? "on" : ""}`}>
                  <button className="btn tiny" onClick={() => play(s)} title="play in the browser"
                    data-testid={`sfx-play-${s.name}`}>{playing === s.name ? "■" : "▶"}</button>
                  <span className="sfxname">{s.name}{s.builtin ? null : <Badge>custom</Badge>}</span>
                  <span className="hint sfxdesc">{s.desc}</span>
                  <button className="btn tiny" disabled={!!busy} onClick={() => assignSfx(s)}
                    data-testid={`sfx-use-${s.name}`}>use</button>
                </div>
              ))}
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}
