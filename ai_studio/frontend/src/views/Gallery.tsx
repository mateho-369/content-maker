import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { errText, useToast } from "../main";
import { Badge, Empty, Modal, Notice, Panel, Skeleton, fmtDur, fmtSize, fmtTime } from "../ui";

/**
 * The real showcase.
 *
 * `/gallery` used to be ~210 lines of HTML + CSS inside `ai_studio/app.py` naming
 * three specific renders. This lists what actually exists: every `final` asset the
 * database knows about, in the projects that made them. A cut whose file has since
 * been deleted stays visible and is labelled `file missing`, because "your export is
 * gone" is the useful answer and an empty wall is not.
 */

type Card = {
  asset_id: string; project_id: string; title: string; content_type: string; run_id: string;
  created_at: number; duration: number; size_bytes: number; width?: number; height?: number;
  captions?: string; stream_url: string; download_url: string; poster_url: string;
  missing: boolean; verified: boolean; fps?: number; has_audio?: boolean;
};

export function GalleryPanel({ onOpen }: { onOpen?: (view: string, id?: string) => void }) {
  const [cards, setCards] = useState<Card[] | null>(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [probe, setProbe] = useState(false);
  const [kind, setKind] = useState("");
  const [play, setPlay] = useState<Card | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = useCallback(async (withProbe = false) => {
    setBusy(true);
    try {
      const r = await api<{ items: Card[]; note: string }>("/gallery", { query: { probe: withProbe ? 1 : 0 } });
      setCards(r.items || []); setNote(r.note || ""); setErr("");
      if (withProbe) toast(`${(r.items || []).filter((c: Card) => c.verified).length} file(s) opened and measured`, "ok");
    } catch (e) { setErr(errText(e)); }
    setBusy(false);
  }, [toast]);
  useEffect(() => { load(probe); }, [load, probe]);

  const kinds = useMemo(() => Array.from(new Set((cards || []).map((c) => c.content_type).filter(Boolean))), [cards]);
  const shown = (cards || []).filter((c) => !kind || c.content_type === kind);

  return (
    <Panel title={`🎞 Gallery — every finished cut (${(cards || []).length})`}
      right={<span className="row" style={{ gap: 6 }}>
        <label className="mini-field check" title="run ffmpeg on each file instead of trusting the render record">
          <input type="checkbox" checked={probe} onChange={(e) => setProbe(e.target.checked)} />
          <span>verify files</span>
        </label>
        <button className="btn tiny" onClick={() => load(probe)} disabled={busy} data-testid="gallery-refresh">⟳</button>
      </span>}>
      {err ? <Notice kind="err" title="the gallery could not be read">{err}</Notice> : null}
      {cards === null ? <Skeleton rows={4} /> : cards.length === 0 ? (
        <Empty text="nothing has finished rendering yet — a run that reaches assemble puts its cut here automatically." />
      ) : (
        <>
          <div className="row" style={{ gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
            <select value={kind} onChange={(e) => setKind(e.target.value)} style={{ width: 170 }}>
              <option value="">every content type</option>
              {kinds.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
            <span className="hint">{note}</span>
          </div>
          <div className="gallery-grid" data-testid="gallery-grid">
            {shown.map((c) => (
              <figure key={c.asset_id} className={`gcard ${c.missing ? "gone" : ""}`}>
                <div className="gthumb" onClick={() => !c.missing && setPlay(c)}>
                  {c.poster_url ? <img src={c.poster_url} alt="" loading="lazy" /> : <span>🎬</span>}
                  {!c.missing ? <span className="gplay">▶</span> : <span className="gmiss">file missing</span>}
                </div>
                <figcaption>
                  <b title={c.title}>{c.title}</b>
                  <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                    {c.content_type ? <Badge>{c.content_type}</Badge> : null}
                    <Badge kind={c.missing ? "err" : c.verified ? "ok" : ""}>
                      {c.missing ? "gone" : c.verified ? "verified" : "from record"}
                    </Badge>
                    {c.width && c.height ? <span className="hint">{c.width}×{c.height}{c.fps ? `@${c.fps}` : ""}</span> : null}
                  </div>
                  <div className="hint">
                    {fmtDur(c.duration)} · {fmtSize(c.size_bytes)} · {c.captions ? `${c.captions} captions · ` : "captions not recorded · "}
                    {fmtTime(c.created_at)}
                  </div>
                  <div className="row" style={{ gap: 4 }}>
                    <button className="btn tiny" onClick={() => onOpen?.("project", c.project_id)}
                      data-testid={`gallery-open-${c.asset_id}`}>open project</button>
                    <a className="btn tiny" href={c.download_url} download>download</a>
                  </div>
                </figcaption>
              </figure>
            ))}
          </div>
        </>
      )}
      {play ? (
        <Modal title={play.title} onClose={() => setPlay(null)}>
          <video className="gvideo" controls autoPlay src={play.stream_url} />
          <div className="hint" style={{ marginTop: 6 }}>
            streamed with range requests, so seeking works{play.has_audio === false ? " · this file has no audio stream" : ""}
          </div>
        </Modal>
      ) : null}
    </Panel>
  );
}
