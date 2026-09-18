import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { errText, useToast } from "../main";
import { Badge, Bar, Field, Modal, Notice, Panel, Skeleton } from "../ui";

/**
 * The Auto-Clip engine, as a panel instead of a second app.
 *
 * `src/app.py` (a Jinja dashboard on :8001 with its own config.json) did exactly
 * this: upload a long video → score candidate highlights → crop one to vertical with
 * face tracking, optional narration ducking and burned captions. The engines are
 * unchanged; what changed is that the work now runs through the studio's API, with
 * the studio's settings (there is no second LLM config to fall out of sync) and the
 * studio's job conventions — including "this job is no longer in memory" when the
 * server restarted, instead of a progress bar frozen at 40%.
 */

type Engine = {
  available: boolean; missing: string[]; install: string;
  capabilities: { crop: boolean; face_model: boolean; whisper: boolean; kokoro_voice: boolean };
  note?: string; caption_styles: string[]; max_upload_mb?: number;
};
type Video = { video: string; bytes: number; analyzed: boolean; clips: number; modified: number };
type Clip = { index: number; start: number; end: number; score?: number; reason?: string; text?: string };
type Job = {
  job_id: string; kind: string; status: string; stage: string; progress: number;
  // analyse progress lines and export step receipts share one shape here
  steps?: { step?: string; ok?: boolean; why?: string; style?: string; srt?: string;
            faces?: boolean; t?: number; stage?: string; progress?: number; error?: string }[];
  result?: any; error?: string; meta?: any; elapsed?: number;
};

export function ClipsPanel() {
  const toast = useToast();
  const [engine, setEngine] = useState<Engine | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [outputs, setOutputs] = useState<{ file: string; bytes: number; url: string; modified: number }[]>([]);
  const [video, setVideo] = useState("");
  const [clips, setClips] = useState<Clip[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [jobErr, setJobErr] = useState("");
  const [pick, setPick] = useState(0);
  const [busy, setBusy] = useState("");
  const [opts, setOpts] = useState({ top_n: 5, min_seconds: 15, max_seconds: 30, use_whisper: false,
                                     caption_style: "Reels", track_faces: true, voiceover_text: "",
                                     use_kokoro: false });
  const [preview, setPreview] = useState("");
  const player = useRef<HTMLVideoElement | null>(null);
  const poll = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api<{ engine: Engine; videos: Video[]; outputs: any[] }>("/clips");
      setEngine(r.engine); setVideos(r.videos || []); setOutputs(r.outputs || []);
      setVideo((v) => v || (r.videos || [])[0]?.video || "");
    } catch (e) { toast(errText(e), "err"); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => () => { if (poll.current) window.clearInterval(poll.current); }, []);

  const watch = useCallback((jobId: string, onDone: (j: Job) => void) => {
    if (poll.current) window.clearInterval(poll.current);
    poll.current = window.setInterval(async () => {
      try {
        const j = await api<Job>(`/clips/jobs/${jobId}`);
        setJob(j); setJobErr("");
        if (j.status === "done" || j.status === "failed") {
          if (poll.current) window.clearInterval(poll.current);
          poll.current = null;
          onDone(j);
        }
      } catch (e) {
        if (poll.current) window.clearInterval(poll.current);
        poll.current = null;
        setJobErr(errText(e));                     // "job is gone after a restart", not a stuck bar
      }
    }, 900);
  }, []);

  const upload = async (f: File) => {
    setBusy("upload");
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await api<{ video: string; note?: string }>("/clips/upload", { method: "POST", form: fd });
      setVideo(r.video);
      toast(r.note || "video stored", "ok");
      await load();
    } catch (e) { toast(errText(e), "err"); }
    setBusy("");
  };

  const analyze = async () => {
    if (!video) { toast("pick or upload a video first", "warn"); return; }
    setBusy("analyze"); setJobErr("");
    try {
      const r = await api<{ job_id: string }>("/clips/analyze", {
        method: "POST",
        json: { video, top_n: opts.top_n, min_seconds: opts.min_seconds, max_seconds: opts.max_seconds,
                use_whisper: !!engine?.capabilities.whisper && opts.use_whisper },
      });
      watch(r.job_id, (j) => {
        setBusy("");
        if (j.status === "failed") { toast(j.error || "analysis failed", "err"); return; }
        setClips(j.result?.clips || []);
        setPick(0);
        toast(`${(j.result?.clips || []).length} candidate clip(s) — pick one and export`, "ok");
        load();
      });
    } catch (e) { toast(errText(e), "err"); setBusy(""); }
  };

  const exportClip = async () => {
    setBusy("export"); setJobErr("");
    try {
      const r = await api<{ job_id: string }>("/clips/export", {
        method: "POST",
        json: { video, index: pick, caption_style: opts.caption_style, track_faces: opts.track_faces,
                voiceover_text: opts.voiceover_text, use_kokoro: opts.use_kokoro },
      });
      watch(r.job_id, (j) => {
        setBusy("");
        if (j.status === "failed") { toast(j.error || "render failed", "err"); return; }
        const skipped = (j.result?.steps || []).filter((s: any) => s.ok === false);
        toast(skipped.length ? `clip ready — ${skipped.map((s: any) => `${s.step}: ${s.why || "skipped"}`).join("; ")}`
                             : "clip ready", skipped.length ? "warn" : "ok");
        load();
      });
    } catch (e) { toast(errText(e), "err"); setBusy(""); }
  };

  const seekTo = (t: number) => {
    setPreview(video);
    window.setTimeout(() => { if (player.current) player.current.currentTime = t; player.current?.play?.(); }, 60);
  };

  const clip = useMemo(() => clips.find((c) => c.index === pick) || null, [clips, pick]);
  const running = !!job && job.status !== "done" && job.status !== "failed";

  return (
    <Panel title="✂️ Clip a long video (auto-clip engine)"
      right={<span className="row" style={{ gap: 6 }}>
        {engine ? <Badge kind={engine.available ? "ok" : "err"}>
          {engine.available ? "engine ready" : `missing ${engine.missing.join(", ")}`}</Badge> : null}
        <button className="btn tiny" onClick={load} title="re-read the data folder">⟳</button>
      </span>}>
      {engine === null ? <Skeleton rows={3} /> : !engine.available ? (
        <Notice kind="err" title="this machine cannot run the clip engine"
          action={<code>{engine.install}</code>}>
          It is installed as an optional extra (the clipper needs <b>moviepy</b>), so upload,
          analyze and export are switched off here rather than failing on the first click.
          Missing: {engine.missing.join(" · ")}
        </Notice>
      ) : (
        <>
          {engine.note ? <Notice kind="warn" title="degraded face tracking">{engine.note}</Notice> : null}
          <div className="clip-steps">
            <div className="clip-step">
              <span className="clip-n">1</span>
              <div className="grow">
                <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                  <label className="btn tiny file" title={`mp4 / mov / mkv / avi / webp up to ${engine.max_upload_mb} MB`}>
                    ⬆ choose video
                    <input type="file" accept=".mp4,.mov,.mkv,.avi,.webm,.m4v" hidden data-testid="clip-upload"
                      onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
                  </label>
                  <select value={video} onChange={(e) => { setVideo(e.target.value); setClips([]); }} data-testid="clip-video">
                    {videos.length === 0 ? <option value="">no video in the data folder yet</option> : null}
                    {videos.map((v) => (
                      <option key={v.video} value={v.video}>
                        {v.video.slice(0, 46)} · {(v.bytes / 1e6).toFixed(0)} MB · {v.clips} clip(s)
                      </option>
                    ))}
                  </select>
                  {busy === "upload" ? <Skeleton rows={1} /> : null}
                </div>
              </div>
            </div>

            <div className="clip-step">
              <span className="clip-n">2</span>
              <div className="grow clip-opts">
                <label className="mini-field"><span>clips</span>
                  <input type="number" min={1} max={20} value={opts.top_n}
                    onChange={(e) => setOpts({ ...opts, top_n: Number(e.target.value) || 5 })} /></label>
                <label className="mini-field"><span>min s</span>
                  <input type="number" min={3} max={120} value={opts.min_seconds}
                    onChange={(e) => setOpts({ ...opts, min_seconds: Number(e.target.value) || 15 })} /></label>
                <label className="mini-field"><span>max s</span>
                  <input type="number" min={5} max={180} value={opts.max_seconds}
                    onChange={(e) => setOpts({ ...opts, max_seconds: Number(e.target.value) || 30 })} /></label>
                <label className={`mini-field check ${engine.capabilities.whisper ? "" : "off"}`}
                  title={engine.capabilities.whisper ? "transcribe with faster-whisper, then score on speech"
                    : "whisper is not installed — speech scoring stays off, audio energy + motion only"}>
                  <input type="checkbox" disabled={!engine.capabilities.whisper} checked={!!opts.use_whisper}
                    onChange={(e) => setOpts({ ...opts, use_whisper: e.target.checked })} />
                  <span>transcribe</span>
                </label>
                <button className="btn tiny primary" disabled={!!busy || !video} onClick={analyze}
                  data-testid="clip-analyze">
                  {busy === "analyze" ? "scoring…" : "analyze"}
                </button>
              </div>
            </div>

            {job ? (
              <div className="clip-job" data-testid="clip-job">
                <div className="spread">
                  <b style={{ fontSize: 12 }}>{job.kind} · {job.status}</b>
                  <span className="hint">{job.stage}</span>
                </div>
                <Bar pct={job.progress} />
                {(job.steps || []).slice(-6).map((st, i) => (
                  <div key={i} className="hint clip-step-line">{st.t !== undefined ? `${st.t}s · ` : ""}{st.stage || st.step}</div>
                ))}
                {running ? <span className="hint">measuring… the studio keeps this job in memory only</span> : null}
              </div>
            ) : null}
            {jobErr ? <Notice kind="warn" title="job state lost">{jobErr}</Notice> : null}

            <div className="clip-step">
              <span className="clip-n">3</span>
              <div className="grow">
                {clips.length === 0 ? (
                  <div className="hint">analyze first: the candidate clips appear here with their scores and the
                    words detected in them.</div>
                ) : (
                  <table className="tbl clips-tbl" data-testid="clip-list">
                    <thead><tr><th>#</th><th>in</th><th>out</th><th>len</th><th>score</th><th>what it found</th><th /></tr></thead>
                    <tbody>
                      {clips.map((c) => (
                        <tr key={c.index} className={pick === c.index ? "on" : ""}
                          onClick={() => setPick(c.index)}>
                          <td>{c.index + 1}</td>
                          <td>{c.start.toFixed(1)}s</td>
                          <td>{c.end.toFixed(1)}s</td>
                          <td>{(c.end - c.start).toFixed(1)}s</td>
                          <td>{c.score !== undefined ? Number(c.score).toFixed(0) : "—"}</td>
                          <td className="clip-text" title={c.reason || ""}>{(c.text || c.reason || "").slice(0, 90) || "—"}</td>
                          <td className="row" style={{ gap: 4 }}>
                            <button className="btn tiny" onClick={(e) => { e.stopPropagation(); seekTo(c.start); }}>▶</button>
                            <button className="btn tiny primary" onClick={(e) => { e.stopPropagation(); setPick(c.index); exportClip(); }}
                              data-testid={`clip-export-${c.index}`}>crop this</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            <div className="clip-step">
              <span className="clip-n">4</span>
              <div className="grow clip-opts">
                <Field label="captions" hint="the caption styles this renderer implements — nothing else is offered">
                  <select value={opts.caption_style} onChange={(e) => setOpts({ ...opts, caption_style: e.target.value })}>
                    {(engine.caption_styles || []).map((st) => <option key={st}>{st}</option>)}
                  </select>
                </Field>
                <label className="mini-field check" title="MediaPipe/Haar tracking; off = centre crop">
                  <input type="checkbox" checked={opts.track_faces}
                    onChange={(e) => setOpts({ ...opts, track_faces: e.target.checked })} />
                  <span>follow faces</span>
                </label>
                <label className="mini-field check off" title="Kokoro voice is not installed on this machine">
                  <input type="checkbox" disabled={!engine.capabilities.kokoro_voice} checked={!!opts.use_kokoro}
                    onChange={(e) => setOpts({ ...opts, use_kokoro: e.target.checked })} />
                  <span>kokoro voice</span>
                </label>
                <button className="btn tiny primary" disabled={!!busy || !clip} onClick={exportClip}
                  data-testid="clip-export-go">
                  {busy === "export" ? "rendering…" : clip ? `export clip ${clip.index + 1}` : "export clip"}
                </button>
              </div>
            </div>
            <div className="clip-step">
              <span className="clip-n">5</span>
              <div className="grow">
                <Field label="narration over the clip (optional)"
                  hint="mixed under the original audio at 25%; empty means the clip keeps its own sound">
                  <textarea className="input" rows={2} value={opts.voiceover_text}
                    onChange={(e) => setOpts({ ...opts, voiceover_text: e.target.value })} />
                </Field>
              </div>
            </div>
          </div>

          <div className="row spread" style={{ marginTop: 10, gap: 8, flexWrap: "wrap" }}>
            <span className="hint">{outputs.length} rendered file(s) in the studio data folder</span>
            {preview ? (
              <span className="hint">preview seeks the streamed file — <code>#t={clip ? clip.start.toFixed(1) : "0"}</code></span>
            ) : null}
          </div>
          {preview === video && video ? (
            <video ref={player} className="clip-preview" controls src={`/api/clips/source/${encodeURIComponent(video)}`}
              data-testid="clip-preview" />
          ) : null}
          {outputs.length ? (
            <div className="clip-outs" data-testid="clip-outputs">
              {outputs.slice(0, 12).map((o) => (
                <a key={o.file} className="clip-out" href={o.url} download>
                  <span>{o.file.endsWith(".srt") ? "≡" : "🎬"} {o.file}</span>
                  <em>{(o.bytes / 1e6).toFixed(1)} MB</em>
                </a>
              ))}
            </div>
          ) : null}
        </>
      )}
      {clip && preview ? (
        <Modal title={`clip ${clip.index + 1} · ${clip.start.toFixed(1)}s → ${clip.end.toFixed(1)}s`}
          onClose={() => setPreview("")}>
          <div className="hint">{clip.text || clip.reason || "no transcript for this clip"}</div>
        </Modal>
      ) : null}
    </Panel>
  );
}
