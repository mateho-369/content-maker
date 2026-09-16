import React, { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, Asset, Project, QAResult, Run, Scene, StageRow, StageSpec, StylePreview } from "../api";
import { useToast, errText } from "../main";
import { Badge, Bar, Empty, Modal, Panel, StatusBadge, fmtDur, fmtSize, fmtTime, Spinner } from "../ui";
import { CaptionStudio } from "./CaptionStudio";

interface Live {
  run_id?: string; status?: string; stages?: StageRow[]; overall?: { pct?: number }; events?: any[];
  error?: string; deferred_stages?: string[]; final_path?: string; duration?: number;
}

export function ProjectView({ projectId, onOpen }: { projectId: string; onOpen: (v: string, id?: string) => void }) {
  const [proj, setProj] = useState<Project | null>(null);
  const [specs, setSpecs] = useState<StageSpec[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [log, setLog] = useState<any[]>([]);
  const [selScene, setSelScene] = useState(0);
  const [selStage, setSelStage] = useState("voice_final");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [liveMode, setLiveMode] = useState("");
  const [capStyle, setCapStyle] = useState<Record<string, any> | null>(null);
  const [workflowTab, setWorkflowTab] = useState<"board" | "director" | "qa">("board");
  const toast = useToast();
  const wsRef = useRef<WebSocket | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api<{ project: Project; scenes: Scene[]; runs: Run[]; caption_style?: Record<string, any> }>(`/projects/${projectId}`);
      setProj(d.project);
      if (d.caption_style) setCapStyle(d.caption_style);
      setRun((r) => (r && d.runs?.length && r.id !== d.runs[0].id) ? d.runs[0] : (r || d.runs?.[0] || null));
      const s = await api<{ roles: StageSpec[] }>("/settings");
      setSpecs(s.roles || []);
      const a = await api<{ assets: Asset[] }>("/assets", { query: { project_id: projectId, limit: 300 } });
      setAssets(a.assets || []);
      setErr("");
    } catch (e) { setErr(errText(e)); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  // A board save returns exactly what was stored (idx renumbered, meta kept), so
  // the view adopts that instead of refetching project + settings + assets — the
  // three round trips per dropdown click were the "editing scene text lags".
  const adoptBoard = useCallback((project: Project, sc: Scene[]) => {
    setProj((prev) => ({ ...(prev as Project), ...project, scenes: sc }));
  }, []);

  // one snapshot fetch, three outcomes: data, "this run is gone", "retry".
  const refresh = useCallback(async (runId: string): Promise<Live | null | "retry"> => {
    try {
      const s = await api<Live>(`/runs/${runId}/status?since=0`);
      setLive(s); setLiveMode((m) => m || "poll");
      return s;
    } catch (e) {
      // 404 is permanent — the run row is gone (other data dir, deleted or
      // duplicated project, pruned history). Drop the live view, refetch the
      // project so the board/buttons agree with the DB, and stop asking. The old
      // `catch {}` treated it as transient, which is the 404-per-2s wall in the
      // console (1200 ticks = 40 minutes of it).
      if (e instanceof ApiError && e.status === 404) { setLive(null); setLiveMode(""); load(); return null; }
      return "retry";
    }
  }, [load]);

  const flush = useCallback(() => { /* placeholder for animation flush */ }, []);

  useEffect(() => () => { wsRef.current?.close(); }, []);

  // live WS with SSE + polling fallback
  const connect = useCallback((runId: string) => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    let ws: WebSocket;
    try { ws = new WebSocket(`${proto}://${location.host}/api/runs/${runId}/events`); }
    catch { return; }
    setLiveMode("ws");
    ws.onmessage = (ev) => {
      try {
        const m = JSON.parse(ev.data);
        if (m.kind === "snapshot") { setLive(m.payload); if (m.payload?.status) flush(); }
        else if (m.kind === "stage_update" || m.kind === "stage_failed") {
          setLive((x) => x || {}); refresh(runId);
          // scenes are written by these two stages, so the board (and the
          // "Scene board (0)" the manual workflow started from) only updates
          // when the project itself is refetched — the live snapshot alone
          // never carries them
          if (m.kind === "stage_update" && ["script", "breakdown"].includes(m.stage)
              && m.payload?.status === "done") load();
        }
        else if (m.kind === "log") { setLog((x) => [...x.slice(-200), m.payload]); }
        else if (m.kind === "run_finished") { setLive(m.payload); refresh(runId); load(); }
      } catch {}
    };
    ws.onclose = () => { setLiveMode("poll"); /* SSE + polling keep it honest */ };
    wsRef.current = ws;
    return ws;
  }, [load, refresh]);

  const startRun = async (payload: any = {}) => {
    setBusy("starting");
    try {
      const r = await api<{ run_id: string }>(`/projects/${projectId}/runs`, { method: "POST", json: payload });
      setBusy("");
      toast("run started", "ok");
      setLive({ run_id: r.run_id, status: "running" });
      connect(r.run_id);
      poll(r.run_id);
    } catch (e) { toast(errText(e), "err"); setBusy(""); }
  };

  const poll = useCallback(async (runId: string) => {
    for (let i = 0; i < 1200; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const s = await refresh(runId);
      if (s === null) return;                       // run vanished — refresh() recovered
      if (s === "retry") continue;                  // network hiccup, next tick
      if (s.status && !["running", "queued", "paused"].includes(s.status)) { load(); setLiveMode(""); return; }
    }
  }, [load, refresh]);

  const act = async (verb: string, path: string, body?: any, okMsg = "") => {
    setBusy(verb);
    try {
      const r = await api(path, { method: "POST", json: body });
      if (okMsg) toast(okMsg, "ok");
      setBusy("");
      return r as any;
    } catch (e) { toast(errText(e), "err"); setBusy(""); return null; }
  };

  if (!proj) return <div className="pad">{err && <div className="errbar">⚠ {err}</div>}<Spinner /></div>;

  if (proj.status === "draft" && proj.mode === "B" && !proj.script) {
    return <ModeBGate proj={proj} onOpen={onOpen} onChanged={load} act={act} busy={busy} />;
  }

  const runRows = (live?.stages || run?.stages || []).slice();
  const deferredCount = runRows.filter((r) => r.status === "deferred").length;
  const stages = specs.length ? specs : STAGE_FALLBACK;
  const sc = proj.scenes || [];

  const isAuto = proj.settings?.control_mode !== "manual";
  const toggleControlMode = async () => {
    const nextMode = isAuto ? "manual" : "auto";
    try {
      await api(`/projects/${proj.id}`, {
        method: "PATCH",
        json: { settings: { ...proj.settings, control_mode: nextMode } },
      });
      toast(`Switched to ${nextMode.toUpperCase()} mode`, "ok");
      load();
    } catch (e) {
      toast(errText(e), "err");
    }
  };

  return (
    <div className="pad">
      {err && <div className="errbar">⚠ {err}</div>}
      {live?.error && <div className="errbar">⚠ run error: {live.error}</div>}
      <div className="spread" style={{ marginBottom: 10 }}>
        <div className="row" style={{ gap: 8, alignItems: "center" }}>
          <h2>{proj.title}</h2>
          <button className={`btn tiny ${isAuto ? "primary" : "warn"}`} onClick={toggleControlMode}
            title="Toggle between AI Content Director and Manual Creator Override">
            {isAuto ? "🤖 AUTO Director" : "🎛️ MANUAL Override"}
          </button>
          <Badge kind="blue">{proj.mode === "A" ? "Director" : "Auto"}</Badge>
          <Badge>{proj.content_type}</Badge>
          {proj.character_id ? <Badge kind="warn">🧑 character</Badge> : null}
          <StatusBadge status={live?.status || proj.status} />
        </div>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn primary" disabled={!!busy} onClick={() => startRun({})}>{busy === "starting" ? <Spinner /> : "▶ Run Studio"}</button>
          <button className="btn" disabled={!live?.run_id || !!busy}
            onClick={() => act("pause", `/runs/${live!.run_id}/pause`)}>⏸</button>
          <button className="btn" disabled={!live?.run_id || !!busy}
            onClick={() => act("resume", `/runs/${live!.run_id}/resume`)}>▶</button>
          <button className="btn" disabled={!live?.run_id || !!busy}
            onClick={() => act("cancel", `/runs/${live!.run_id}/cancel`)}>■</button>
          <button className="btn" disabled={!live?.run_id || !!busy}
            onClick={() => act("continue", `/runs/${live!.run_id}/continue`)}>continue</button>
          <span className={`dot ${liveMode ? "on" : ""}`} title={liveMode ? `live via ${liveMode}` : "offline"} />
          <button className="btn warn" disabled={!!busy || !(deferredCount > 0)}
            title="re-render the deferred GPU stages, then QA + assembly (voice reused)"
            onClick={() => act("catchup", `/projects/${proj.id}/catchup`, {}, "GPU catch-up started")}>
            🖥 GPU catch-up{(deferredCount > 0) ? ` (${deferredCount})` : ""}</button>
        </div>
      </div>

      {/* Promax Workflow Step Tabs */}
      <div className="tabs" style={{ marginBottom: 12 }}>
        <button className={workflowTab === "board" ? "on" : ""} onClick={() => setWorkflowTab("board")}>
          🎬 Storyboard & Production
        </button>
        <button className={workflowTab === "director" ? "on" : ""} onClick={() => setWorkflowTab("director")}>
          🤖 Content Director & Hook Advisor
        </button>
        <button className={workflowTab === "qa" ? "on" : ""} onClick={() => setWorkflowTab("qa")}>
          🛡️ Automated QA Gate
        </button>
      </div>

      <div className="split wide-right" style={{ gridTemplateColumns: "minmax(0,1fr) 430px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {workflowTab === "director" && (
            <ContentDirectorPanel proj={proj} scenes={sc} onChanged={load} />
          )}
          {workflowTab === "qa" && (
            <QAGatePanel proj={proj} scenes={sc} assets={assets} />
          )}
          {workflowTab === "board" && (
            <>
              <PipelineDAG stages={stages} rows={runRows} onStage={(k) => setSelStage(k)} />
              <CaptionStudio projectId={proj.id} initial={capStyle} onChanged={load} />
              <SceneBoard proj={proj} scenes={sc} rows={runRows} assets={assets} sel={selScene}
                onSel={setSelScene} onChanged={load} onAdopt={adoptBoard} act={act} busy={busy} />
              <ScriptPanel proj={proj} onChanged={load} act={act} busy={busy} />
              <EventLog log={log} rows={runRows} />
            </>
          )}
        </div>
        <Inspector proj={proj} scenes={sc} stage={selStage} scene={selScene} assets={assets}
          rows={runRows} onChanged={load} act={act} busy={busy} specs={stages} />
      </div>
    </div>
  );
}

const ACTIONS = [
  "talking", "pointing", "surprised", "happy", "sad", "thinking", "confused",
  "laughing", "crying", "shocked", "walking", "sitting", "reacting",
  "celebrating", "frustrated", "explaining", "holding_phone", "holding_coffee",
  "holding_book", "holding_money", "holding_shield"
];

const PROPS = ["none", "phone", "coffee", "book", "money", "shield", "microphone", "sparkles"];

const EMOTIONS = [
  "calm", "soft", "strong", "happy", "sad", "serious", "excited", "surprised", "storytelling", "emotional"
];

const MEMES = [
  "reaction_shock", "reaction_laugh", "reaction_crying", "reaction_mindblown", "reaction_facepalm", "meme_dramatic_zoom"
];

function ContentDirectorPanel({ proj, scenes, onChanged }: { proj: Project; scenes: Scene[]; onChanged: () => void }) {
  const [analysis, setAnalysis] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  const analyze = async () => {
    setLoading(true);
    try {
      const res = await api<any>("/content-director/analyze", {
        method: "POST",
        json: { topic: proj.topic_hint || proj.title, script: proj.script },
      });
      setAnalysis(res);
      toast("Content Director evaluation complete", "ok");
    } catch (e) {
      toast(errText(e), "err");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { analyze(); }, [proj.id]);

  return (
    <Panel title="Content Director Intelligence & Viral Hooks" right={
      <button className="btn tiny primary" onClick={analyze} disabled={loading}>
        {loading ? "Analyzing…" : "🤖 Refresh Analysis"}
      </button>
    }>
      <div className="panel-b">
        {analysis ? (
          <div>
            <div className="spread" style={{ marginBottom: 12 }}>
              <div>
                <b>Director Recommendation: </b>
                <Badge kind={analysis.approved ? "ok" : "warn"}>
                  {analysis.approved ? `Retention Rating: ${analysis.retention_score}/100` : "Needs Polish"}
                </Badge>
              </div>
              <div className="hint">Optimal Format: <b>{analysis.content_type_label}</b></div>
            </div>

            <div className="cards" style={{ gridTemplateColumns: "1fr 1fr", marginBottom: 12 }}>
              <div className="ct-card">
                <b>🎯 1-3s Viral Hook Suggestion</b>
                <p lang="km" style={{ marginTop: 6, fontSize: 13, color: "var(--tx)", lineHeight: 1.5 }}>
                  {analysis.hook_suggestion}
                </p>
              </div>
              <div className="ct-card">
                <b>🎭 Recommended Action & Emotion</b>
                <div style={{ marginTop: 6, fontSize: 12 }}>
                  <div><b>Character Action:</b> {analysis.recommended_character_action} {analysis.recommended_prop !== "none" ? `(Prop: ${analysis.recommended_prop})` : ""}</div>
                  <div><b>Voice Emotion:</b> {analysis.recommended_emotion}</div>
                  <div><b>Visual Default:</b> {analysis.recommended_visual_source}</div>
                  <div><b>Meme Moment:</b> {analysis.use_meme ? `Yes (${analysis.meme_type})` : "No"}</div>
                </div>
              </div>
            </div>

            {analysis.use_meme && (
              <div style={{ background: "#1c2128", border: "1px solid #30363d", borderRadius: 4, padding: 8, marginBottom: 8, fontSize: 12 }}>
                <b>⚡ Meme Reasoning:</b> {analysis.meme_reasoning}
              </div>
            )}

            {analysis.critique.length > 0 && (
              <div className="errbar" style={{ background: "#2e2a1d", color: "var(--yellow)" }}>
                <b>Director Critique:</b> {analysis.critique.join(" ")}
              </div>
            )}
          </div>
        ) : (
          <div className="hint">Evaluating project topic and script structure…</div>
        )}
      </div>
    </Panel>
  );
}

function QAGatePanel({ proj, scenes }: { proj: Project; scenes: Scene[]; assets: Asset[] }) {
  const [qaRes, setQaRes] = useState<QAResult | null>(null);
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  const runQA = async (announce = true) => {
    setLoading(true);
    try {
      const res = await api<QAResult>(`/qa/project/${proj.id}`);
      setQaRes(res);
      // Only an explicit click may toast. The mount-time call fires for every
      // draft project, and "QA Gate flagged issues" on a project nobody has
      // rendered yet is noise dressed up as a defect.
      if (!announce || res?.pending) return;
      toast(res.approved ? "QA Gate Passed: Ready to Ship!" : "QA Gate flagged issues", res.approved ? "ok" : "warn");
    } catch (e) {
      if (announce) toast(errText(e), "err");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { runQA(false); }, [proj.id]);

  // Never assume a field survived the round trip: reading `.some()` on an
  // absent `failures` array used to blank the whole view.
  const failures: any[] = qaRes?.failures || [];
  const warnings: any[] = qaRes?.warnings || [];
  const flagged = (list: any[], check: string) => list.some((x) => x?.check === check);

  return (
    <Panel title="Automated QA Gate · Pre-Delivery Compliance" right={
      <button className="btn tiny primary" onClick={() => runQA(true)} disabled={loading}>
        {loading ? "Auditing…" : "🛡️ Run Full QA Audit"}
      </button>
    }>
      <div className="panel-b">
        {qaRes?.pending ? (
          <div className="hint">
            Nothing to audit yet — this project has no scenes. Run the pipeline (Stage 1 breaks
            the script into scenes) and the gate will check Khmer clusters, hook pacing, voice
            levels and the final MP4 container.
          </div>
        ) : qaRes ? (
          <div>
            <div className="spread" style={{ marginBottom: 12 }}>
              <div>
                <b>Gate Status: </b>
                <Badge kind={qaRes.approved ? "ok" : "err"}>
                  {qaRes.approved ? "✅ APPROVED FOR EXPORT" : "❌ ISSUES DETECTED"}
                </Badge>
              </div>
              <div className="hint">
                {qaRes.total_scenes ?? scenes.length} scenes · {failures.length} failures · {warnings.length} warnings
              </div>
            </div>

            {/* Checklist */}
            <div className="cards" style={{ gridTemplateColumns: "repeat(3, 1fr)", marginBottom: 14 }}>
              <div className="ct-card">
                <b>1. Khmer Typography & Subscripts</b>
                <div style={{ marginTop: 4, color: flagged(failures, "khmer_clusters") ? "var(--red)" : "var(--green)" }}>
                  {flagged(failures, "khmer_clusters") ? "❌ Broken Consonant Cluster" : "✓ Subscripts & HarfBuzz Normalization Valid"}
                </div>
              </div>
              <div className="ct-card">
                <b>2. Script & Viral Hook</b>
                <div style={{ marginTop: 4, color: flagged(warnings, "hook_pacing") ? "var(--yellow)" : "var(--green)" }}>
                  {flagged(warnings, "hook_pacing") ? "⚠️ Scene 1 Hook Needs Tightening" : "✓ 1-3s Hook Optimized"}
                </div>
              </div>
              <div className="ct-card">
                <b>3. Final MP4 Container</b>
                <div style={{ marginTop: 4, color: qaRes.mp4_verified ? "var(--green)" : "var(--tx2)" }}>
                  {qaRes.mp4_verified ? "✓ 9:16 Vertical Video Valid"
                    : qaRes.mp4_checked ? "❌ A render was found but it failed its checks"
                    : "○ Nothing exported yet"}
                </div>
              </div>
            </div>

            {failures.length > 0 && (
              <div className="errbar" style={{ marginBottom: 8 }}>
                <b>Failures:</b>
                <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
                  {failures.map((f: any, idx: number) => (
                    <li key={idx}>[{f?.check}] Scene {f?.scene_idx !== undefined ? f.scene_idx + 1 : "General"}: {f?.issue}</li>
                  ))}
                </ul>
              </div>
            )}

            {warnings.length > 0 && (
              <div style={{ background: "#2e2a1d", border: "1px solid #665020", borderRadius: 4, padding: 8, color: "var(--yellow)" }}>
                <b>Warnings:</b>
                <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
                  {warnings.map((w: any, idx: number) => (
                    <li key={idx}>[{w?.check}] Scene {w?.scene_idx !== undefined ? w.scene_idx + 1 : "General"}: {w?.issue}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="hint">{loading ? "Auditing…" : "Click \"Run Full QA Audit\" to verify all script clusters, voice loudness, and video assets."}</div>
        )}
      </div>
    </Panel>
  );
}

const STAGE_FALLBACK: StageSpec[] = [
  "script", "breakdown", "voice_base", "voice_final", "talking_head", "video", "video_fit", "sfx", "qa", "assemble",
].map((k, i) => ({ key: k, title: k.replace(/_/g, " "), emoji: "▪", role: "", blurb: "", model: "",
  per_scene: true, requires_gpu: false, resource: "cpu", depends: [], deferrable: false }));

function PipelineDAG({ stages, rows, onStage }: {
  stages: StageSpec[]; rows: StageRow[]; onStage: (k: string) => void;
}) {
  const byStage: Record<string, StageRow[]> = {};
  rows.forEach((r) => { (byStage[r.stage] = byStage[r.stage] || []).push(r); });
  const stFor = (k: string) => {
    const rs = byStage[k] || [];
    const counts: Record<string, number> = {};
    rs.forEach((r) => { counts[r.status] = (counts[r.status] || 0) + 1; });
    if (counts.failed || counts.blocked) return "failed";
    if (rs.some((r) => ["running", "queued"].includes(r.status))) return "running";
    if (counts.done === rs.length && rs.length) return "done";
    if (counts.deferred === rs.length && rs.length) return "deferred";
    return "";
  };
  return (
    <Panel title="Pipeline" right={<span className="hint">click a stage → inspector</span>}>
      <div className="dag">
        {stages.map((s) => {
          const st = stFor(s.key);
          return (
            <div key={s.key} className={`node ${st}`} onClick={() => onStage(s.key)}>
              <div className="t">{s.emoji} {s.title}</div>
              <div className="m">{st || "waiting"}{(byStage[s.key]?.length || 0) > 1 ? ` · ${byStage[s.key].length} scenes` : ""}</div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

const BLANK_SCENE: Scene = { idx: 0, text: "", visual_prompt: "", mood_tag: "calm-warm",
  estimated_duration_sec: 0, audio_duration: 0, sfx_prompt: "", meta: {} };

function SceneBoard({ proj, scenes, rows, assets, sel, onSel, onChanged, onAdopt, act, busy }: {
  proj: Project; scenes: Scene[]; rows: StageRow[]; assets: Asset[]; sel: number; onSel: (i: number) => void;
  onChanged: () => void; onAdopt?: (project: Project, scenes: Scene[]) => void;
  act: (v: string, p: string, b?: any, ok?: string) => Promise<any>; busy: string;
}) {
  const toast = useToast();
  const [draft, setDraft] = useState<Scene[]>(scenes);
  const [dirty, setDirty] = useState(false);
  const [importing, setImporting] = useState(false);
  const [paste, setPaste] = useState("");
  const draftRef = useRef(draft); draftRef.current = draft;   // a queued save must post the latest rows
  const timer = useRef<number | null>(null);
  // re-seed only when the stored content changes: `scenes` got a new array
  // identity on every live tick, which used to wipe half-typed narration
  const sig = scenes.map((s) => `${s.text}\u0001${JSON.stringify(s.meta || {})}`).join("\u0002");
  useEffect(() => { setDraft(scenes); setDirty(false); }, [sig]);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  const save = useCallback(async (announce = true) => {
    if (timer.current) { window.clearTimeout(timer.current); timer.current = null; }
    const body = { scenes: draftRef.current.map((d) => ({ ...d, idx: undefined })) };
    if (!body.scenes.length) {
      toast("the board is empty — “+ add scene” makes a row, “⤓ import script” makes one per line", "warn");
      return;
    }
    try {
      const r = await api<any>(`/projects/${proj.id}/scenes`, { method: "POST", json: body });
      setDraft(r.scenes || []); setDirty(false);
      if (r.project && onAdopt) onAdopt(r.project, r.scenes || []); else onChanged();
      if (announce) toast(r.note || "storyboard saved", "ok");
    } catch (e) { toast(errText(e), "err"); }   // a failed autosave still says so
  }, [proj.id, onChanged, onAdopt]);

  const queueSave = useCallback(() => {
    setDirty(true);
    if (timer.current) window.clearTimeout(timer.current);
    // An unfinished row makes the whole save invalid (the server refuses rather
    // than dropping it), so autosave waits for the Director to press save board —
    // otherwise every picker click would answer with an error toast.
    if (draftRef.current.some((r) => !String(r.text || "").trim())) return;
    timer.current = window.setTimeout(() => { timer.current = null; save(false); }, 700);
  }, [save]);

  const edit = (mutate: (list: Scene[]) => Scene[], autosave = false) => {
    setDraft(mutate(draftRef.current)); setDirty(true);
    if (autosave) queueSave();
  };
  const addScene = (at?: number) => {
    const i = at === undefined ? draftRef.current.length : at;
    edit((x) => { const c = [...x]; c.splice(i, 0, { ...BLANK_SCENE, meta: {} }); return c; });
    onSel(i);
  };
  const duplicateScene = (i: number) => edit((x) => {
    const c = [...x]; c.splice(i + 1, 0, { ...c[i], meta: { ...(c[i].meta || {}) } }); return c;
  });
  const removeScene = (i: number) => {
    edit((x) => x.filter((_, j) => j !== i));
    toast("row removed — save board to drop it from the project", "info");
  };
  const moveScene = (i: number, dir: number) => edit((x) => {
    const j = i + dir; if (j < 0 || j >= x.length) return x;
    const c = [...x]; [c[i], c[j]] = [c[j], c[i]]; return c;
  });
  const importPaste = () => {
    const lines = paste.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (!lines.length) return;
    edit((x) => [...x, ...lines.map((text) => ({ ...BLANK_SCENE, text, meta: {} }))]);
    setPaste(""); setImporting(false);
    toast(`${lines.length} scene(s) added — save board to store them`, "ok");
  };
  const uploadImage = async (idx: number, f: File) => {
    const fd = new FormData(); fd.append("image", f);
    try { await api(`/projects/${proj.id}/scenes/${idx}/image`, { method: "POST", form: fd }); toast("scene image uploaded", "ok"); onChanged(); }
    catch (e) { toast(errText(e), "err"); }
  };
  const patchScene = (idx: number, meta: Record<string, any>) =>
    edit((x) => x.map((s, i) => i === idx ? { ...s, meta: { ...s.meta, ...meta } } : s), true);
  const stageFor = (idx: number, stage: string) => rows.find((r) => r.stage === stage && r.scene_idx === idx);

  // content-type structure grouping: compare → A / B / summary; word_nuance → meaning-1 / meaning-2 / contrast
  const groupKey = (s: Scene): string => {
    const side = s.meta?.side || "";
    if (proj.content_type === "compare") return side === "summary" ? "summary" : side ? "side " + side : "";
    if (proj.content_type === "word_nuance") return side || "";
    return "";
  };
  const groupLabel = (k: string) => {
    if (!k) return "";
    if (proj.content_type === "compare") return k === "summary" ? "⚖ summary" : k === "side A" ? "⚖ side A" : "⚖ side B";
    if (proj.content_type === "word_nuance") return "🔤 " + k;
    return k;
  };
  const grouped: { label: string; items: number[] }[] = [];
  draft.forEach((s, i) => {
    const k = groupKey(s);
    const last = grouped[grouped.length - 1];
    if (!k || (last && last.label === groupLabel(k))) {
      if (last) last.items.push(i); else grouped.push({ label: "", items: [i] });
    } else {
      grouped.push({ label: groupLabel(k), items: [i] });
    }
  });

  return (
    <Panel title={`Scene board (${draft.length}${dirty ? " · unsaved" : ""})`}
      right={<div className="row" style={{ gap: 4 }}>
        <button className="btn tiny" onClick={() => addScene()} title="append one empty scene">+ add scene</button>
        <button className="btn tiny" onClick={() => setImporting(true)} title="paste a script: one line = one scene">⤓ import script</button>
        <button className={`btn tiny ${dirty ? "primary" : ""}`} onClick={() => save(true)} disabled={busy === "board"}>
          {dirty ? "save board ●" : "save board"}
        </button>
      </div>}>
      {!draft.length ? (
        <div className="panel-b" style={{ padding: "20px 12px", textAlign: "center" }}>
          <div className="hint" style={{ marginBottom: 10 }}>
            Nothing on the board yet — one line of narration per scene.{" "}
            {proj.script ? "“⤓ import script” turns the saved script into rows." : " Paste the script first, then import it."}
          </div>
          <div className="row" style={{ justifyContent: "center", gap: 6 }}>
            <button className="btn tiny primary" onClick={() => addScene(0)}>+ add scene</button>
            <button className="btn tiny" onClick={() => setImporting(true)}>⤓ import script</button>
          </div>
        </div>
      ) : (
      <table className="grid">
        <thead>
          <tr>
            <th style={{ width: 76 }}>#</th>
            <th>narration</th>
            <th style={{ width: 140 }}>action & prop</th>
            <th style={{ width: 110 }}>emotion</th>
            <th style={{ width: 130 }}>visual source</th>
            <th style={{ width: 62 }}>⏱</th>
            <th style={{ width: 110 }}>production</th>
          </tr>
        </thead>
        <tbody>
          {grouped.map((g, gi) => (
            <React.Fragment key={gi}>
              {g.label && <tr className="group-head"><td colSpan={7}>{g.label}</td></tr>}
              {g.items.map((si) => {
                // `grouped[].items` holds SCENE INDICES. The row used to treat that
                // number as the scene object and use the group-relative counter as
                // the row id — so on a grouped board (compare / word_nuance /
                // myth_vs_fact / choose) every cell read `undefined`, the pickers
                // showed defaults, and each edit wrote to the wrong scene.
                const s = draft[si];
                if (!s) return null;
                const vs = s.meta?.visual_source || (hasChar(proj, s) ? "character_action" : "illustration");
                const stop = (e: React.MouseEvent) => e.stopPropagation();
                const sel2 = (fn: () => void) => (e: React.MouseEvent) => { stop(e); fn(); };
                return (
                  <tr key={si} onClick={() => onSel(si)} style={{ cursor: "pointer", background: sel === si ? "#242a35" : undefined }}>
                    <td>
                      <b>{si + 1}</b>
                      {s.meta?.side ? <><br /><Badge>{s.meta.side}</Badge></> : null}
                      <div className="row" style={{ gap: 2, marginTop: 3 }}>
                        <button className="btn tiny" title="duplicate this scene" onClick={sel2(() => duplicateScene(si))}>⧉</button>
                        <button className="btn tiny" title="move up" onClick={sel2(() => moveScene(si, -1))}>↑</button>
                        <button className="btn tiny" title="move down" onClick={sel2(() => moveScene(si, 1))}>↓</button>
                        <button className="btn tiny" title="remove this row (save board to apply)" onClick={sel2(() => removeScene(si))}>✕</button>
                      </div>
                    </td>
                    <td>
                      <textarea className="scene-text" lang="km" spellCheck={false} value={s.text} rows={2}
                        onChange={(e) => edit((x) => x.map((y, j) => j === si ? { ...y, text: e.target.value } : y))} />
                      {s.meta?.character_id ? <div className="hint">🧑 {s.meta.character_id.slice(0, 10)}</div> : null}
                    </td>
                    <td>
                      <select value={s.meta?.character_action || "talking"} style={{ width: "100%", padding: "2px 4px", fontSize: 11 }}
                        onChange={(e) => patchScene(si, { character_action: e.target.value })}>
                        {ACTIONS.map((a) => <option key={a} value={a}>🎭 {a}</option>)}
                      </select>
                      <select value={s.meta?.prop || "none"} style={{ width: "100%", padding: "2px 4px", fontSize: 11, marginTop: 3 }}
                        onChange={(e) => patchScene(si, { prop: e.target.value })}>
                        {PROPS.map((pr) => <option key={pr} value={pr}>📦 {pr}</option>)}
                      </select>
                    </td>
                    <td>
                      {/* a mood slug ("calm-warm", "rain-soft") is NOT an emotion style:
                          feeding it to this select gave a controlled value with no matching
                          option, so the row displayed "calm" while the DB said something else.
                          Show the style that will actually be applied, keep the mood visible. */}
                      <select value={s.meta?.emotion_style || (EMOTIONS.includes(s.mood_tag) ? s.mood_tag : "calm")}
                        style={{ width: "100%", padding: "2px 4px", fontSize: 11 }}
                        onChange={(e) => patchScene(si, { emotion_style: e.target.value })}>
                        {EMOTIONS.map((em) => <option key={em} value={em}>🎙️ {em}</option>)}
                      </select>
                      {s.mood_tag && s.mood_tag !== s.meta?.emotion_style ? <div className="hint" style={{ fontSize: 10 }}>mood: {s.mood_tag}</div> : null}
                    </td>
                    <td>
                      <VisualSourceControl value={vs} hasChar={hasChar(proj, s)}
                        onChange={(v) => patchScene(si, { visual_source: v })} />
                      {vs === "meme" && (
                        <select value={s.meta?.meme_type || "reaction_shock"} style={{ width: "100%", padding: "2px 4px", fontSize: 11, marginTop: 3 }}
                          onChange={(e) => patchScene(si, { meme_type: e.target.value })}>
                          {MEMES.map((m) => <option key={m} value={m}>⚡ {m.replace("reaction_", "")}</option>)}
                        </select>
                      )}
                    </td>
                    <td className="mono">
                      {fmtDur(s.estimated_duration_sec)}
                      <input type="number" min={1} max={30} step={0.5} title="planned scene length (s)"
                        value={s.estimated_duration_sec || ""} style={{ width: "100%", marginTop: 3, padding: "1px 4px", fontSize: 11 }}
                        onChange={(e) => edit((x) => x.map((y, j) => j === si ? { ...y, estimated_duration_sec: Number(e.target.value) || 0 } : y))} />
                    </td>
                    <td>
                      {hasChar(proj, s) && (
                        <div className="row" style={{ marginBottom: 3 }}>
                          <select value={s.meta?.render_mode || "broll"} style={{ width: "100%", padding: "2px 4px", fontSize: 11 }}
                            onChange={(e) => patchScene(si, { render_mode: e.target.value })}>
                            <option value="broll">b-roll</option><option value="talking_head">talking head</option>
                          </select>
                        </div>
                      )}
                      <div className="row" style={{ gap: 4 }}>
                        <input type="file" accept="image/*" style={{ display: "none" }} id={`img-${si}`}
                          onChange={(e) => e.target.files?.[0] && uploadImage(si, e.target.files[0])} />
                        <button className="btn tiny" onClick={sel2(() => document.getElementById(`img-${si}`)?.click())}>⬆ img</button>
                        <a className="btn tiny" href={`/api/projects/${proj.id}/scene/${si}/download`} onClick={stop}>zip</a>
                      </div>
                      <div className="hint" style={{ marginTop: 3, fontSize: 10 }}>
                        {["voice_final", "video", "video_fit", "ambient"].map((k) => {
                          const r = stageFor(si, k);
                          return r ? <span key={k}>{k.replace("_final", "").replace("_fit", "")}:{r.status[0]} </span> : null;
                        })}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </React.Fragment>
          ))}
        </tbody>
      </table>
      )}
      {importing && (
        <Modal title="import a script · one line = one scene" onClose={() => setImporting(false)}>
          <textarea className="scene-text" lang="km" rows={12} style={{ width: "100%", fontFamily: "inherit" }}
            value={paste} onChange={(e) => setPaste(e.target.value)}
            placeholder={"each non-empty line becomes one scene\nMode A keeps your wording exactly — nothing is rewritten"} />
          <div className="spread" style={{ marginTop: 10 }}>
            <span className="hint">
              {paste.split(/\r?\n/).filter((l) => l.trim()).length} scene(s) · appended after scene {draft.length}
            </span>
            <div className="row" style={{ gap: 6 }}>
              <button className="btn" onClick={() => setImporting(false)}>cancel</button>
              <button className="btn primary" onClick={importPaste}
                disabled={!paste.split(/\r?\n/).filter((l) => l.trim()).length}>add to board</button>
            </div>
          </div>
        </Modal>
      )}
    </Panel>
  );
}

function hasChar(p: Project, s: Scene) { return !!p.character_id || !!s.meta?.character_id; }

export function VisualSourceControl({ value, hasChar, onChange }: {
  value: string; hasChar: boolean; onChange: (v: string) => void;
}) {
  const opts = [
    ["character_action", "🎭 character action"],
    ["illustration", "🖼 illustration"],
    ["meme", "⚡ meme / reaction"],
    ["generated_video", "🎞 AI video (optional)"],
  ] as const;
  return (
    <select value={value || (hasChar ? "character_action" : "illustration")} style={{ width: "auto", padding: "2px 6px", fontSize: 11 }}
      onChange={(e) => onChange(e.target.value)}>
      {opts.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
    </select>
  );
}

function ScriptPanel({ proj, onChanged, act, busy }: {
  proj: Project; onChanged: () => void; act: (v: string, p: string, b?: any, ok?: string) => Promise<any>; busy: string;
}) {
  const [text, setText] = useState(proj.script);
  const toast = useToast();
  useEffect(() => setText(proj.script), [proj.script]);
  const save = async () => {
    try {
      await api(`/projects/${proj.id}`, { method: "PATCH", json: { script: text, director_override: true } });
      toast("script updated", "ok"); onChanged();
    } catch (e) { toast(errText(e), "err"); }
  };
  return (
    <Panel title={proj.mode === "A" ? "Script (Director-locked)" : "Script (draft)"}
      right={<div className="row">
        {proj.mode === "B" && <button className="btn tiny"
          onClick={() => act("idea", `/projects/${proj.id}/regenerate-script`, {}, "new draft from the Controller")}
          title="ask the Controller for a fresh draft">regenerate script</button>}
        {proj.mode === "B" && <button className="btn tiny" onClick={() => act("idea", `/projects/${proj.id}/generate-idea`)}>auto-idea</button>}
        {proj.mode === "B" && <button className="btn tiny primary" onClick={() => act("approve", `/projects/${proj.id}/approve-script`, {}, "script approved")}>approve → run</button>}
        <button className="btn tiny" onClick={save}>save</button>
      </div>}>
      <textarea rows={6} style={{ margin: 10, width: "calc(100% - 20px)" }} value={text}
        onChange={(e) => setText(e.target.value)} />
      <div className="hint" style={{ padding: "0 12px 10px" }}>
        {proj.script_locked ? "Mode A: wording is verified against this paste — the studio never rewrites it." : "Mode B: edit before approving; production starts after approval."}
      </div>
    </Panel>
  );
}

function Waveform({ assetId }: { assetId: string }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const toast = useToast();
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = await api<{ peaks: number[]; duration?: number }>(`/assets/${assetId}/waveform`);
        const cv = ref.current;
        if (!cv || !alive) return;
        const ctx = cv.getContext("2d");
        if (!ctx) return;
        const w = (cv.width = (cv.clientWidth || 480) * (window.devicePixelRatio || 1));
        const h = (cv.height = 34 * (window.devicePixelRatio || 1));
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = "var(--green)";
        const pk = d.peaks || [];
        const bw = w / Math.max(1, pk.length);
        pk.forEach((v, i) => {
          const hh = Math.max(1, Math.min(1, v) * h * 0.92);
          ctx.fillRect(i * bw, (h - hh) / 2, Math.max(1, bw * 0.7), hh);
        });
      } catch (e) {
        if (alive) toast(errText(e), "err");   // never hide an audible failure
      }
    })();
    return () => { alive = false; };
  }, [assetId]);
  return <canvas ref={ref} className="wave" title="audio waveform" style={{ height: 34, width: 140, flex: "0 0 140px" }} />;
}

function EventLog({ log, rows }: { log: any[]; rows: StageRow[] }) {
  return (
    <Panel title="Event log" scroll>
      <div className="log">
        {rows.filter((r) => r.error).map((r) => (
          <div key={r.id} className="l-err">[{r.stage}#{r.scene_idx}] {r.error}</div>
        ))}
        {rows.filter((r) => r.message).slice(-40).map((r) => (
          <div key={r.id} className={`l-${r.status === "failed" ? "err" : r.status === "done" ? "ok" : ""}`}>
            [{r.stage}#{r.scene_idx}] {r.status}: {r.message}
          </div>
        ))}
        {log.slice(-120).map((l, i) => (
          <div key={i} className={`l-${l.level || ""}`}>{(l.text || l.line || JSON.stringify(l)).slice(0, 400)}</div>
        ))}
      </div>
    </Panel>
  );
}

function Inspector({ proj, scenes, stage, scene, assets, rows, onChanged, act, busy, specs }: {
  proj: Project; scenes: Scene[]; stage: string; scene: number; assets: Asset[];
  rows: StageRow[]; onChanged: () => void; act: (v: string, p: string, b?: any, ok?: string) => Promise<any>;
  busy: string; specs: StageSpec[];
}) {
  const toast = useToast();
  const s = scenes[scene];
  const spec = specs.find((x) => x.key === stage);
  const stageRows = rows.filter((r) => r.stage === stage && r.scene_idx === scene);
  const row = stageRows[0];
  const a = (kind: string) => assets.find((x) => x.scene_idx === scene && x.kind === kind);
  const zips = {};

  const regen = async () => {
    if (!proj.last_run_id && !row) { toast("no run yet — run the pipeline first, then regenerate per stage", "warn"); return; }
    const runId = row?.run_id || proj.last_run_id;
    try {
      const r = await api<{ run_id: string }>(`/runs/${runId}/stages/${stage}/regenerate`, {
        method: "POST", json: { scene_idx: scene },
      });
      toast(`regenerating ${stage} #${scene}…`, "ok"); onChanged();
    } catch (e) { toast(errText(e), "err"); }
  };

  const media = a("video_fit") || a("video") || a("talking_head");
  const voice = a("voice_final") || a("voice");
  const amb = a("ambient");
  const qa = a("qa");
  // the captioned cut when one exists — never silently play the uncaptioned one
  const finals = assets.filter((x) => x.kind === "final" || x.kind === "final_uncaptioned");
  const capFinal = finals.find((x) => x.kind === "final");
  const all = capFinal || finals[0] || assets.find((x) => x.kind === "video_fit");
  const srt = assets.find((x) => x.kind === "srt");
  const instProps = (x: Asset | undefined) => x && (
    <details key={x.kind} style={{ marginBottom: 6 }}>
      {/* the engine lives in meta.engine (there is no top-level column) — reading
          x.engine printed an empty label for every asset, always */}
      <summary className="hint">{x.kind} · {x.meta?.engine || ""} · {fmtDur(x.duration)}</summary>
      <video controls preload="metadata" src={`/api/assets/${x.id}/stream`} style={{ marginTop: 4 }} />
      <div className="row" style={{ gap: 4, marginTop: 4 }}>
        <a className="btn tiny" href={`/api/assets/${x.id}/download`}>download</a>
        <a className="btn tiny" href={`/api/assets/${x.id}/stream`} target="_blank" rel="noreferrer">stream</a>
        {x.kind.startsWith("voice") || x.kind === "ambient" ? <Waveform assetId={x.id} /> : null}
      </div>
    </details>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Panel title={`Scene ${scene + 1} · ${s?.text?.slice(0, 40) || "—"}`} scroll>
        {s ? (
          <div className="panel-b">
            <div className="kv">
              <dt>mood</dt><dd><Badge>{s.mood_tag || "—"}</Badge></dd>
              <dt>est / audio</dt><dd className="mono">{fmtDur(s.estimated_duration_sec)} / {fmtDur(s.audio_duration || s.estimated_duration_sec)}</dd>
              <dt>visual source</dt><dd>{s.meta?.visual_source || "generated_video"}</dd>
              <dt>render mode</dt><dd>{s.meta?.render_mode || "broll"}</dd>
              <dt>character</dt><dd>{s.meta?.character_id || proj.character_id || "none"}</dd>
              <dt>visual prompt</dt><dd className="hint">{s.visual_prompt || "—"}</dd>
              <dt>sfx</dt><dd className="hint">{s.sfx_prompt || "—"}</dd>
            </div>
            <div style={{ marginTop: 10 }}>
              {instProps(media)}{instProps(voice)}{instProps(amb)}
              {qa && (
                <details>
                  <summary className="hint">QA json</summary>
                  <pre className="fix" style={{ maxHeight: 220, overflow: "auto" }}>
                    {JSON.stringify(a("qa")?.meta, null, 1) || "—"}
                  </pre>
                </details>
              )}
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <button className="btn tiny" onClick={regen} disabled={!!busy}>⟳ regenerate {stage}#{scene}</button>
              <a className="btn tiny" href={`/api/runs/${row?.run_id || proj.last_run_id || ""}/scenes/${scene}/bundle`}>bundle</a>
            </div>
          </div>
        ) : <Empty text="no scene" />}
      </Panel>
      <Panel title={`Stage ${stage}`} scroll>
        <div className="panel-b">
          <div className="kv">
            <dt>label</dt><dd>{spec?.title || stage}</dd>
            <dt>resource</dt><dd>{spec?.resource} {spec?.requires_gpu ? "· GPU" : ""}</dd>
            <dt>model</dt><dd>{spec?.model || "—"}</dd>
            <dt>status</dt><dd>{row ? <StatusBadge status={row.status} /> : "not run"}</dd>
            <dt>engine</dt><dd>{row?.engine || "—"}</dd>
            <dt>attempts</dt><dd>{row?.attempt || 0}</dd>
            <dt>took</dt><dd>{row?.duration_ms ? `${(row.duration_ms / 1000).toFixed(1)}s` : "—"}</dd>
          </div>
          {row?.error && <div className="errbar" style={{ marginTop: 8 }}>⚠ {row.error}</div>}
          {row?.message && <div className="hint" style={{ marginTop: 8 }}>{row.message}</div>}
          <div style={{ marginTop: 8 }}>
            {scenes.map((x, i) => {
              const r = rows.find((y) => y.stage === stage && y.scene_idx === i);
              return (
                <div key={i} className={`scene-chip ${r ? "st-" + r.status : ""}`} style={{ display: "inline-block", margin: 3 }}>
                  {i + 1}{r ? ":" + r.status[0] : ""}
                </div>
              );
            })}
          </div>
        </div>
      </Panel>
      <Panel title="Final cut" scroll>
        <div className="panel-b">
          {all ? (
            <>
              {all.kind === "final" && (all.meta?.captions === "burned") &&
                <div className="badge ok" style={{ marginBottom: 6 }}>
                  ✓ burned captions · {all.meta?.caption_preset || ""} · {all.meta?.caption_font || ""}
                </div>}
              {all.kind === "final" && all.meta?.captions !== "burned" &&
                <div className="badge warn" style={{ marginBottom: 6 }}>no burned captions</div>}
              <video controls preload="metadata" src={`/api/assets/${all.id}/stream`} />
              <div className="row" style={{ marginTop: 6 }}>
                <a className="btn tiny primary" href={`/api/assets/${all.id}/download`}>⬇ final mp4{srt ? "" : " (uncaptioned)"}</a>
                {srt && <a className="btn tiny" href={`/api/assets/${srt.id}/download`}>⬇ .srt</a>}
                <a className="btn tiny" href={`/api/projects/${proj.id}/download?kind=all`}>project zip</a>
                <a className="btn tiny" href={`/api/projects/${proj.id}/download?kind=bundle`}>.json</a>
              </div>
              <div className="hint" style={{ marginTop: 6 }}>
                {fmtDur(all.duration)} · {fmtSize(all.size_bytes)}
                {all.meta?.caption_timing ? ` · timing: ${all.meta.caption_timing}` : ""}
              </div>
            </>
          ) : <Empty text="no final cut yet" />}
        </div>
      </Panel>
    </div>
  );
}

function ModeBGate({ proj, onOpen, onChanged, act, busy }: {
  proj: Project; onOpen: (v: string, id?: string) => void; onChanged: () => void;
  act: (v: string, p: string, b?: any, ok?: string) => Promise<any>; busy: string;
}) {
  const [script, setScript] = useState(proj.script || "");
  const approve = async () => {
    const r = await act("approve", `/projects/${proj.id}/approve-script`, { script, start: true }, "approved — production running");
    if (r?.project) onChanged();
  };
  return (
    <div className="pad">
      <div className="errbar" style={{ background: "#2e2a1d" }}>
        ⚠ Auto mode: the Controller writes a draft; you must approve it before any GPU work starts.
      </div>
      <Panel title="Draft script (approve before production)">
        <div className="panel-b">
          <textarea rows={10} value={script} style={{ fontFamily: "inherit" }}
            onChange={(e) => setScript(e.target.value)} placeholder="generating…" />
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn primary" disabled={!script || !!busy}
              onClick={() => act("idea", `/projects/${proj.id}/generate-idea`)}>regenerate draft</button>
            <button className="btn primary" disabled={!script || !!busy} onClick={approve}>✅ approve & run</button>
          </div>
        </div>
      </Panel>
    </div>
  );
}
