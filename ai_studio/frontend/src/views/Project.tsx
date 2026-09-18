import React, { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, Asset, Project, QAResult, Run, Scene, StageRow, StageSpec, StylePreview } from "../api";
import { useToast, errText } from "../main";
import { Badge, Bar, Chip, Empty, Field, Modal, Notice, Panel, StatusBadge, fmtDur, fmtSize, fmtTime,
  Spinner, useHotkeys, useSticky } from "../ui";
import { AssetsPanel } from "./Assets";
import { CaptionStudio } from "./CaptionStudio";
import { BackgroundPicker, BackgroundChip, backgroundLabel, Bg } from "../BackgroundPicker";

interface Live {
  run_id?: string; status?: string; stages?: StageRow[]; overall?: { pct?: number }; events?: any[];
  error?: string; deferred_stages?: string[]; final_path?: string; duration?: number;
  // measured countdown from /runs/{id}/status — null until jobs have been timed
  eta?: { seconds?: number | null; remaining_jobs?: number; measured_jobs?: number;
          confidence?: string; scene?: number | null; scene_total?: number | null;
          avg_job_seconds?: number } | null;
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
  // One screen: the old strip swapped whole sections, so opening the QA gate hid the
  // board you had just edited. These are toggles — panels stack, and which are open
  // is remembered per project.
  const [openPan, setOpenPan] = useSticky<Record<string, boolean>>(`studio.panels.${projectId}`,
    { board: true, director: false, qa: false, assets: false });
  const togglePan = useCallback((k: string) => setOpenPan((p) => ({ ...p, [k]: !p[k] })), [setOpenPan]);
  const panOpen = (k: string) => !!openPan[k];
  useHotkeys({
    "mod+1": () => setOpenPan((p) => ({ ...p, board: true, director: false, qa: false, assets: false })),
    "mod+2": () => togglePan("director"),
    "mod+3": () => togglePan("qa"),
    "mod+4": () => togglePan("assets"),
  });
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
  // The header button and the Manual Control Panel must start the *same* run: a
  // tickbox that only works when you press the small button is the exact bug class
  // this panel exists to remove. The panel persists its two selectors onto the
  // project settings, so both entry points read one source of truth.
  const settingSkip = Array.isArray(proj.settings?.skip_stages) ? proj.settings.skip_stages : [];
  const runOff = Array.isArray(proj.settings?.run_skip_scenes) ? proj.settings.run_skip_scenes : [];
  const boardOff = sc.filter((x) => (x.meta || {}).disabled).map((x) => x.idx);
  const manualPayload = () => ({
    skip_stages: settingSkip,
    skip_scenes: Array.from(new Set([...boardOff, ...runOff])).sort((a, b) => a - b),
  });
  const clearPanelSkips = async () => {
    try {
      await api(`/projects/${proj.id}`, {
        method: "PATCH",
        json: { settings: { ...proj.settings, skip_stages: [], run_skip_scenes: [] } },
      });
      toast("the panel's switches are back to running everything", "ok");
      load();
    } catch (e) { toast(errText(e), "err"); }
  };
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
          <button className="btn primary" disabled={!!busy} data-testid="run-studio"
            onClick={() => startRun(isAuto ? {} : manualPayload())}>
            {busy === "starting" ? <Spinner /> : "▶ Run Studio"}
          </button>
          {isAuto && (settingSkip.length || runOff.length) ? (
            <button className="btn tiny warn" data-testid="clear-panel-skips"
              title="the Manual Control Panel left these switched off; AUTO mode runs everything and ignores them"
              onClick={clearPanelSkips}>
              ⚠ panel had {settingSkip.length ? `${settingSkip.join("/")} off` : "stages on"}
              {runOff.length ? ` · ${runOff.length} scene(s) off` : ""} — clear
            </button>
          ) : null}
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

      <IdentityPanel proj={proj} onChanged={load} busy={busy} act={act} />

      {/* Panels stack now — a chip that hides the board you are editing is how a
          workspace starts feeling like a slideshow */}
      <div className="chips" data-testid="panel-chips">
        <Chip on={panOpen("board")} onClick={() => togglePan("board")} kbd="⌘1"
          title="the board, the run controls, captions, the script and the log">🎬 Storyboard &amp; Production</Chip>
        <Chip on={panOpen("director")} onClick={() => togglePan("director")} kbd="⌘2"
          title="hook advice, retention score, scene structure">🤖 Content Director &amp; Hook Advisor</Chip>
        <Chip on={panOpen("qa")} onClick={() => togglePan("qa")} kbd="⌘3"
          title="the gate that audits the finished file">🛡️ Automated QA Gate</Chip>
        <Chip on={panOpen("assets")} onClick={() => togglePan("assets")} kbd="⌘4"
          title="open-licence stills and the shared sound-effect folder">🖼 Assets &amp; sounds</Chip>
        <span className="spacer" />
        <span className="hint" data-testid="panel-count">
          {[["board", "board"], ["director", "director"], ["qa", "QA"], ["assets", "assets"]]
            .filter(([k]) => panOpen(k)).map(([, n]) => n).join(" · ") || "nothing open"}
        </span>
      </div>

      <div className="split wide-right" style={{ gridTemplateColumns: "minmax(0,1fr) 430px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {panOpen("director") && (
            <ContentDirectorPanel proj={proj} scenes={sc} onChanged={load} />
          )}
          {panOpen("qa") && (
            <QAGatePanel proj={proj} scenes={sc} assets={assets} />
          )}
          {panOpen("assets") && (
            <AssetsPanel projectId={proj.id} scenes={sc} selScene={selScene} onAssigned={load} />
          )}
          {panOpen("board") && (
            <>
              <PipelineDAG stages={stages} rows={runRows} onStage={(k) => setSelStage(k)} />
              <RunControlPanel proj={proj} scenes={sc} stages={stages} live={live} busy={busy}
                onRun={startRun} onChanged={load} act={act} />
              <CaptionStudio projectId={proj.id} initial={capStyle} onChanged={load} />
              <SceneBoard proj={proj} scenes={sc} rows={runRows} assets={assets} sel={selScene}
                onSel={setSelScene} onChanged={load} onAdopt={adoptBoard} act={act} busy={busy} />
              <ScriptPanel proj={proj} onChanged={load} act={act} busy={busy} />
              <EventLog log={log} rows={runRows} />
              <BackgroundPanel proj={proj} scenes={sc} onChanged={load} act={act} busy={busy} />
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
          // the server says which step is missing (no script vs no scenes vs no
          // render); a hardcoded sentence here was wrong for two of the three
          <div className="hint">{qaRes.message || "Nothing to audit yet — run the pipeline first."}</div>
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
  const [bgRow, setBgRow] = useState(-1);      // which row has its background open
  const draftRef = useRef(draft); draftRef.current = draft;   // a queued save must post the latest rows
  const timer = useRef<number | null>(null);
  // Re-seed only when the STORED content changes: `scenes` gets a new array identity
  // on every live tick, which used to wipe half-typed narration. The signature has to
  // cover every column the board writes, not just text + meta — a field another panel
  // changed underneath (an sfx pick, a mood) would otherwise stay in the board's stale
  // draft and be silently written back over the newer value on the next save.
  const sig = scenes.map((s) => [s.text, JSON.stringify(s.meta || {}), s.sfx_prompt,
                                 s.visual_prompt, s.mood_tag, s.estimated_duration_sec,
                                 s.audio_duration].join("\u0001")).join("\u0002");
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
    timer.current = window.setTimeout(() => { timer.current = null; save(false); }, 500);
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
  // a stable (scene, key, value) sink — that is what lets a row's pickers be
  // memoized: only primitives and this one callback reach them
  const pickMeta = useCallback((idx: number, key: string, value: any) => {
    patchScene(idx, { [key]: value });
  }, [queueSave]);                                       // eslint-disable-line react-hooks/exhaustive-deps
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
            <th style={{ width: 92 }}>background</th>
            <th style={{ width: 62 }}>⏱</th>
            <th style={{ width: 110 }}>production</th>
            <th style={{ width: 46 }} title="tick to render this scene in the next run">in run</th>
          </tr>
        </thead>
        <tbody>
          {grouped.map((g, gi) => (
            <React.Fragment key={gi}>
              {g.label && <tr className="group-head"><td colSpan={9}>{g.label}</td></tr>}
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
                <React.Fragment key={si}>
                  <tr onClick={() => onSel(si)} style={{ cursor: "pointer", background: sel === si ? "#242a35" : undefined }}>
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
                      <RowPickers si={si} action={s.meta?.character_action || "talking"}
                        prop={s.meta?.prop || "none"} onPick={pickMeta} />
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
                    <td>
                      <button className="btn tiny bgbtn" title={backgroundLabel(s.meta?.background)}
                        onClick={sel2(() => setBgRow(bgRow === si ? -1 : si))} data-testid={`bg-row-${si}`}>
                        <BackgroundChip bg={s.meta?.background} size={18} />
                        <span className="bgbtn-cap">{s.meta?.background ? "override" : "default"}</span>
                      </button>
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
                        {/* the row's own text is saved with it, so one click covers
                            "I changed this line, redo just this shot" — other scenes
                            keep their finished clips and only the cut is rebuilt */}
                        {proj.last_run_id ? (
                          <button className="btn tiny" data-testid={`rerender-${si}`} disabled={!!busy}
                            title="save the board, then re-render this scene's clip and rebuild the cut"
                            onClick={sel2(async () => {
                              await save(false);
                              const r = await act("regenerate",
                                `/runs/${proj.last_run_id}/stages/video/regenerate`,
                                { scene_idx: si }, `scene ${si + 1} re-rendering`);
                              if (r?.run_id) onChanged();
                            })}>⟳</button>
                        ) : null}
                      </div>
                      <div className="hint" style={{ marginTop: 3, fontSize: 10 }}>
                        {["voice_final", "video", "video_fit", "ambient"].map((k) => {
                          const r = stageFor(si, k);
                          return r ? <span key={k}>{k.replace("_final", "").replace("_fit", "")}:{r.status[0]} </span> : null;
                        })}
                      </div>
                    </td>
                    <td>
                      <input type="checkbox" style={{ width: 15, height: 15, cursor: "pointer" }}
                        checked={!s.meta?.disabled} title={s.meta?.disabled
                          ? "deselected — every stage, the captions and the cut skip this scene"
                          : "included in the next run"}
                        data-testid={`scene-in-run-${si}`}
                        onChange={(e) => patchScene(si, { disabled: !e.target.checked })} />
                    </td>
                  </tr>
                  {/* one open row is enough: it writes scene.meta.background, which
                      every render path (previz, ComfyUI, Illux, talking head) paints
                      behind the subject — an override here beats the project setting */}
                  {bgRow === si && (
                    <tr className="bg-expand"><td colSpan={9}>
                      <div className="spread" style={{ marginBottom: 6 }}>
                        <b style={{ fontSize: 12 }}>Background for scene {si + 1}</b>
                        <span className="row" style={{ gap: 4 }}>
                          <button className="btn tiny" onClick={() => { patchScene(si, { background: null }); setBgRow(-1); }}
                            title="drop the override and inherit the project background">inherit project default</button>
                          <button className="btn tiny primary" onClick={() => { save(false); setBgRow(-1); }}>done</button>
                        </span>
                      </div>
                      <BackgroundPicker projectId={proj.id} dense
                        value={s.meta?.background || null}
                        onChange={(next) => patchScene(si, { background: next })} />
                    </td></tr>
                  )}
                </React.Fragment>
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

/**
 * One row's action + prop selects, memoized. A full board is 15 rows × several
 * controls, and every keystroke in a narration box re-rendered all of them (the
 * "typing lags" complaint). Props here are primitives plus one stable callback, so
 * React.memo actually hits.
 */
const RowPickers = React.memo(function RowPickers({ si, action, prop, onPick }: {
  si: number; action: string; prop: string; onPick: (idx: number, key: string, v: any) => void;
}) {
  return (
    <>
      <select value={action} style={{ width: "100%", padding: "2px 4px", fontSize: 11 }}
        onChange={(e) => onPick(si, "character_action", e.target.value)}>
        {ACTIONS.map((a) => <option key={a} value={a}>🎭 {a}</option>)}
      </select>
      <select value={prop} style={{ width: "100%", padding: "2px 4px", fontSize: 11, marginTop: 3 }}
        onChange={(e) => onPick(si, "prop", e.target.value)}>
        {PROPS.map((pr) => <option key={pr} value={pr}>📦 {pr}</option>)}
      </select>
    </>
  );
});

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

/**
 * The log keeps every line a run produces — 10k on a long render. Rendering all of
 * them is what made the panel stutter, so only a window is mounted, and "follow"
 * keeps it pinned to the newest line. Older lines are one click away, not lost.
 */
function EventLog({ log, rows }: { log: any[]; rows: StageRow[] }) {
  const [expanded, setExpanded] = useState(0);      // how many extra lines to mount
  const [follow, setFollow] = useState(true);
  const errs = rows.filter((r) => r.error);
  const msgs = rows.filter((r) => r.message).slice(-40);
  const WINDOW = 80;
  const shown = follow ? log.slice(-WINDOW - expanded) : log.slice(0, WINDOW + expanded);
  const hidden = log.length - shown.length;
  return (
    <Panel title={`Event log${log.length ? ` · ${log.length} lines` : ""}`} scroll right={
      <span className="row" style={{ gap: 6 }}>
        <button className="btn tiny" onClick={() => setFollow((f) => !f)}
          title="keep the newest line in view">{follow ? "⬇ follow" : "⬆ scrolled back"}</button>
        {hidden > 0 ? (
          <button className="btn tiny" data-testid="log-more"
            onClick={() => setExpanded((e) => e + 200)}>show {Math.min(200, hidden)} more</button>
        ) : null}
      </span>
    }>
      <div className="log" data-testid="event-log">
        {errs.map((r) => (
          <div key={r.id} className="l-err">[{r.stage}#{r.scene_idx}] {r.error}</div>
        ))}
        {msgs.map((r) => (
          <div key={r.id} className={`l-${r.status === "failed" ? "err" : r.status === "done" ? "ok" : ""}`}>
            [{r.stage}#{r.scene_idx}] {r.status}: {r.message}
          </div>
        ))}
        {shown.map((l, i) => (
          <div key={`${follow ? "f" : "b"}-${(log.length - shown.length) + i}`} className={`l-${l.level || ""}`}>
            {(l.text || l.line || JSON.stringify(l)).slice(0, 400)}
          </div>
        ))}
        {hidden > 0 && follow ? <div className="hint">…{hidden} older line(s) hidden by the window</div> : null}
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

// ─────────────────────────────────────── manual control: stages, scenes, pre-run plan
/**
 * The project's own settings, editable where you are working.
 *
 * These fields existed only in the create wizard, so changing a title or the target
 * length meant leaving the workspace (and in manual mode, that is the whole point:
 * every value the render uses should be clickable next to the thing it changes).
 * Saves are debounced into one PATCH and each field ticks when the server accepted
 * it — a form that looks applied but was never sent is the failure mode here.
 */
function IdentityPanel({ proj, onChanged, busy, act }: {
  proj: Project; onChanged: () => void; busy: string;
  act: (v: string, p: string, b?: any, ok?: string) => Promise<any>;
}) {
  const [open, setOpen] = useSticky("studio.identity.open", false);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [savedAt, setSavedAt] = useState(0);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [types, setTypes] = useState<any[]>([]);
  const [chars, setChars] = useState<any[]>([]);
  const [profiles, setProfiles] = useState<any[]>([]);
  const timer = useRef<number | null>(null);
  const live = { ...proj, ...draft };                     // what the board would render with

  useEffect(() => { setDraft({}); setErr(""); }, [proj.id]);
  useEffect(() => {
    if (!open) return;                                      // cheap: only fetched when editing
    api<{ types: any[] }>("/content-types").then((r) => setTypes(r.types || [])).catch(() => setTypes([]));
    api<{ characters: any[] }>("/characters").then((r) => setChars(r.characters || [])).catch(() => setChars([]));
    api<{ rvc_profiles?: any[] }>("/voices")
      .then((r) => setProfiles(r.rvc_profiles || [])).catch(() => setProfiles([]));
  }, [open]);

  const set = (k: string, v: any) => setDraft((d) => ({ ...d, [k]: v }));
  const commit = () => {
    if (!Object.keys(draft).length) return;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      setSaving(true);
      const r = await act("identity", `/projects/${proj.id}`, { ...draft }, "");
      setSaving(false);
      if (r !== undefined) { setDraft({}); setErr(""); setSavedAt(Date.now()); onChanged(); }
      else setErr("the server refused the change — see the toast");
    }, 550);
  };
  useEffect(() => { commit(); }, [draft]);                   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);
  const saved = Date.now() - savedAt < 1800 && savedAt > 0;
  const dirty = Object.keys(draft).length > 0;

  return (
    <Panel title="Project details" className="identity"
      right={<span className="row" style={{ gap: 6 }}>
        {!open ? <span className="hint id-summary">
          {live.content_type || "explainer"} · {live.target_duration}s ·{" "}
          {live.character_id ? "🧑 character" : "no character"} ·{" "}
          {live.voice_profile_id ? "cloned voice" : "studio voice"}
        </span> : null}
        {dirty ? <Badge kind="warn">unsaved</Badge> : saved ? <Badge kind="ok">saved</Badge> : null}
        <button className="btn tiny" data-testid="identity-toggle"
          onClick={() => setOpen((o) => !o)}>{open ? "hide" : "✎ edit"}</button>
      </span>}>
      {open ? (
        <div className="id-grid">
          <Field label="title" saved={saved && "title" in draft}>
            <input className="input" value={String(live.title ?? "")} data-testid="id-title"
              onChange={(e) => set("title", e.target.value)} />
          </Field>
          <Field label="target length (s)" hint="drives how many scenes the director proposes"
            saved={saved && "target_duration" in draft}>
            <input type="number" min={5} max={600} value={Number(live.target_duration ?? 30)}
              data-testid="id-duration" onChange={(e) => set("target_duration", Number(e.target.value) || 30)} />
          </Field>
          <Field label="content type" hint="changes the beat structure of the board"
            saved={saved && "content_type" in draft}>
            <select value={String(live.content_type || "")} data-testid="id-type"
              onChange={(e) => set("content_type", e.target.value)}>
              {(types.length ? types : [{ key: live.content_type, label: live.content_type }]).map((t: any) => (
                <option key={t.key} value={t.key}>{t.emoji ? `${t.emoji} ` : ""}{t.label || t.key}</option>
              ))}
            </select>
          </Field>
          <Field label="status" saved={saved && "status" in draft}>
            <select value={String(live.status || "draft")} data-testid="id-status"
              onChange={(e) => set("status", e.target.value)}>
              {["draft", "ready", "review", "rendering", "done", "failed"].map((x) => <option key={x}>{x}</option>)}
            </select>
          </Field>
          <Field label="topic / angle" hint="what the AI idea and the controller read"
            saved={saved && "topic_hint" in draft}>
            <input className="input" value={String(live.topic_hint ?? "")} data-testid="id-topic"
              onChange={(e) => set("topic_hint", e.target.value)} />
          </Field>
          <Field label="character" hint="the matte + pose source for the talking scenes"
            saved={saved && "character_id" in draft}>
            <select value={String(live.character_id || "")} data-testid="id-character"
              onChange={(e) => set("character_id", e.target.value)}>
              <option value="">none — motion graphics only</option>
              {chars.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="cloned voice (RVC)" hint="the text-to-speech voice is chosen in the Manual Control Panel"
            saved={saved && "voice_profile_id" in draft}>
            <select value={String(live.voice_profile_id || "")} data-testid="id-voice"
              onChange={(e) => set("voice_profile_id", e.target.value)}>
              <option value="">none — engine default</option>
              {profiles.map((v: any) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </Field>
          <Field label="style notes for this project" error={err || undefined}
            hint="sent to the writer as EXTRA DIRECTOR NOTES; the house Khmer guideline always applies"
            saved={saved && "style_notes" in draft}>
            <textarea className="input" rows={3} value={String(live.style_notes ?? "")} data-testid="id-notes"
              onChange={(e) => set("style_notes", e.target.value)} />
          </Field>
          <div className="id-foot">
            {saving ? <span className="hint">saving…</span>
              : dirty ? <span className="hint">saves itself as you stop typing</span>
              : <span className="hint">every field above is what the next run will use</span>}
            <button className="btn tiny" disabled={!dirty || saving || !!busy} onClick={commit}>save now</button>
          </div>
        </div>
      ) : null}
    </Panel>
  );
}

const CORE_STAGES = ["script", "breakdown", "video", "assemble"];

function fmtEta(sec?: number | null): string {
  if (sec === null || sec === undefined) return "measuring…";
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  if (m < 60) return `${m}m ${s.toString().padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${(m % 60).toString().padStart(2, "0")}m`;
}

/**
 * Manual Control Panel — the two selectors (stages, scenes), the pre-run summary
 * the render button used to skip, and the live controls.
 *
 * Everything here changes the render: `skip_stages` / `skip_scenes` go on the run
 * payload, `settings.background` is what every stage paints behind the subject,
 * `settings.tts_voice` is what Stage 3a speaks with.
 */
function RunControlPanel({ proj, scenes, stages, live, busy, onRun, onChanged, act }: {
  proj: Project; scenes: Scene[]; stages: StageSpec[]; live: Live | null; busy: string;
  onRun: (payload: any) => void; onChanged: () => void;
  act: (v: string, p: string, b?: any, ok?: string) => Promise<any>;
}) {
  const toast = useToast();
  const settings = proj.settings || {};
  const [skip, setSkip] = useState<string[]>(Array.isArray(settings.skip_stages) ? settings.skip_stages : []);
  const [runOff, setRunOff] = useState<number[]>(Array.isArray(settings.run_skip_scenes) ? settings.run_skip_scenes : []);
  const [plan, setPlan] = useState<any>(null);
  const [confirm, setConfirm] = useState(false);
  const [coreAsk, setCoreAsk] = useState("");       // core stage waiting on a confirm
  const [voices, setVoices] = useState<any[] | null>(null);
  // open by default: this panel is the reason manual mode exists, and a collapsed
  // "Manual Control Panel" is what made the user think the controls were absent
  const [open, setOpen] = useState(true);
  const boardOff = (scenes || []).filter((s) => s.meta?.disabled).map((s) => s.idx);
  const sceneOff = Array.from(new Set([...boardOff, ...runOff])).sort((a, b) => a - b);
  const key = `${proj.id}|${skip.join(",")}|${sceneOff.join(",")}`;

  // The summary is a real request to the same code the scheduler uses, debounced
  // so a fast run of clicks does not stampede the DB.
  useEffect(() => {
    let stop = false;
    const t = window.setTimeout(() => {
      api<any>(`/projects/${proj.id}/run-plan`, {
        query: { skip_stages: skip.join(","), skip_scenes: sceneOff.join(",") },
      }).then((p) => { if (!stop) setPlan(p); }).catch(() => { if (!stop) setPlan(null); });
    }, 250);
    return () => { stop = true; window.clearTimeout(t); };
  }, [key, proj.id]);                                              // eslint-disable-line react-hooks/exhaustive-deps

  const persist = async (next: Record<string, any>) => {
    try {
      await api(`/projects/${proj.id}`, { method: "PATCH", json: { settings: { ...settings, ...next } } });
      onChanged();
    } catch (e) { toast(errText(e), "err"); }
  };

  const toggleStage = (k: string) => {
    // In MANUAL the core stages are switchable like any other — the user asked for a
    // mode where every control answers to them. What stays non-negotiable is the
    // consequence: switching one off asks first, and the run then reports `partial`
    // with the cut missing, which `_finish` already guarantees.
    if (CORE_STAGES.includes(k) && !skip.includes(k)) { setCoreAsk(k); return; }
    const next = skip.includes(k) ? skip.filter((x) => x !== k) : [...skip, k];
    setSkip(next); persist({ skip_stages: next });
  };
  const confirmCoreOff = () => {
    const k = coreAsk; setCoreAsk("");
    if (!k) return;
    const next = [...skip, k];
    setSkip(next); persist({ skip_stages: next });
    toast(`${k} switched off — the run will end “partial” and produce no final MP4`, "warn");
  };
  const toggleScene = (idx: number) => {
    if (boardOff.includes(idx)) { toast("that scene is deselected on the board — tick it there to render it", "warn"); return; }
    const next = runOff.includes(idx) ? runOff.filter((x) => x !== idx) : [...runOff, idx];
    setRunOff(next); persist({ run_skip_scenes: next });
  };

  const running = live?.status === "running" || live?.status === "queued" || live?.status === "paused";
  const eta = live?.eta || null;
  const done = (live?.stages || []).filter((r) => r.status === "done" || r.status === "skipped").length;
  const total = (live?.stages || []).length || 1;

  if ((proj.settings?.control_mode ?? "auto") !== "manual") {
    return (
      <Panel title="Manual Control Panel">
        <div className="panel-b">
          <div className="hint">
            AUTO Director mode is choosing every stage for this project. Switch the header button to{" "}
            <b>🎛️ MANUAL Override</b> to pick stages, deselect scenes and see the pre-run summary.
          </div>
        </div>
      </Panel>
    );
  }

  return (
    <>
      <Panel title="Manual Control Panel — what runs" right={
        <span className="row" style={{ gap: 6 }}>
          {plan ? <Badge kind={sceneOff.length || skip.length ? "warn" : "blue"}>
            {plan.jobs}/{plan.jobs_total} jobs · {plan.scenes_rendering}/{plan.scenes_total} scenes
          </Badge> : null}
          <button className="btn tiny primary" disabled={!!busy} onClick={() => setConfirm(true)}
            data-testid="open-run-summary">▶ Run this</button>
          <button className="btn tiny" onClick={() => setOpen((o) => !o)}>{open ? "hide" : "show"}</button>
        </span>
      }>
        {open && <div className="panel-b" data-testid="manual-controls">
          <div className="mcp-cols">
            <div>
              <div className="mcp-h">Stages — untick to skip (rendered rows stay, the cut just stops waiting on them)</div>
              <div className="mcp-grid">
                {stages.map((sp) => {
                  const core = CORE_STAGES.includes(sp.key);
                  const off = skip.includes(sp.key);
                  return (
                    <label key={sp.key} className={`mcp-item ${core ? "core" : ""} ${off ? "off" : ""}`}
                      title={core ? `manual mode lets you switch this off, but without ${sp.title} the run `
                                        + `cannot produce a final MP4 — it ends “partial” and says so`
                                  : `${sp.blurb || sp.title}${sp.requires_gpu ? " · GPU" : ""}`}>
                      <input type="checkbox" checked={!off}
                        data-testid={`stage-run-${sp.key}`}
                        onChange={() => toggleStage(sp.key)} />
                      <span>{sp.emoji} {sp.title}</span>
                      {core ? <em className="mcp-lock">{off ? "skipped · no cut" : "needs a confirm"}</em>
                             : off ? <em className="mcp-lock">skipped</em> : null}
                    </label>
                  );
                })}
              </div>
            </div>
            <div>
              <div className="mcp-h">Scenes — untick to leave out of this run (captions and the cut follow)</div>
              <div className="mcp-grid">
                {(scenes || []).map((s) => {
                  const off = sceneOff.includes(s.idx);
                  const fromBoard = boardOff.includes(s.idx);
                  return (
                    <label key={s.idx} className={`mcp-item ${off ? "off" : ""}`}
                      title={fromBoard ? "deselected on the storyboard board — tick it there" : (s.text || "").slice(0, 90)}>
                      <input type="checkbox" checked={!off} data-testid={`scene-run-${s.idx}`}
                        onChange={() => toggleScene(s.idx)} />
                      <span>scene {s.idx + 1}</span>
                      {fromBoard ? <em className="mcp-lock">off on board</em> : null}
                    </label>
                  );
                })}
                {!(scenes || []).length ? <div className="hint">no scenes yet — add them on the board below</div> : null}
              </div>
              <div className="row" style={{ gap: 6, marginTop: 8 }}>
                <span className="hint" style={{ whiteSpace: "nowrap" }}>voice</span>
                <select className="input" style={{ flex: 1 }} data-testid="voice-select"
                  value={settings.tts_voice || ""}
                  onFocus={() => { if (!voices) api<any>("/voices").then((r) => setVoices(r.tts_voices || [])).catch(() => setVoices([])); }}
                  onChange={(e) => { persist({ tts_voice: e.target.value }); }}>
                  <option value="">{voices === null ? "loading voices…" : "config default"}</option>
                  {settings.tts_voice && !voices ? <option value={settings.tts_voice}>{settings.tts_voice}</option> : null}
                  {(voices || []).map((v) => (
                    <option key={v.id} value={v.id} disabled={v.available === false}>
                      {v.label}{v.available === false ? " — not installed" : ""}
                    </option>
                  ))}
                </select>
              </div>
              {voices && voices.length === 0 ? (
                <div className="hint" style={{ fontSize: 10 }}>no TTS voices answered — `pip install edge-tts`,
                  or use the placeholder voice only for pipeline tests</div>
              ) : null}
            </div>
          </div>

          {running ? (
            <div className="mcp-live" data-testid="run-progress">
              <Bar pct={live?.overall?.pct ?? Math.round((done / total) * 100)} />
              <div className="row" style={{ gap: 8, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
                <span className="hint">{done}/{total} stages · {eta?.remaining_jobs ?? "?"} jobs left</span>
                <b style={{ fontSize: 12 }}>
                  {eta?.seconds ? `≈ ${fmtEta(eta.seconds)} remaining` : "measuring speed…"}
                </b>
                {eta?.confidence && eta.confidence !== "none" ? (
                  <span className="hint" title={`${eta.measured_jobs} finished jobs, ${eta.avg_job_seconds}s each on average`}
                    style={{ fontSize: 10 }}>({eta.confidence})</span>
                ) : null}
                {eta?.scene != null ? <span className="hint">on scene {eta.scene + 1}{eta.scene_total ? `/${eta.scene_total}` : ""}</span> : null}
                <span className="row" style={{ gap: 4, marginLeft: "auto" }}>
                  <button className="btn tiny" onClick={() => act("pause", `/runs/${live!.run_id}/pause`)}>⏸ pause</button>
                  <button className="btn tiny" onClick={() => act("resume", `/runs/${live!.run_id}/resume`)}>▶ resume</button>
                  {eta?.scene != null && live?.run_id ? (
                    <button className="btn tiny warn" data-testid="skip-scene-live"
                      title="stop everything this scene has not started and carry on with the rest"
                      onClick={() => act("skip", `/runs/${live!.run_id}/skip_scene`, { scene_idx: eta.scene },
                               `scene ${(eta.scene ?? 0) + 1} will be left out of the cut`)}>
                      ⤳ skip scene {(eta.scene ?? 0) + 1} and continue</button>
                  ) : null}
                  <button className="btn tiny danger" onClick={() => act("cancel", `/runs/${live!.run_id}/cancel`, {}, "cancelled")}>■ stop</button>
                </span>
              </div>
            </div>
          ) : (
            <div className="hint" style={{ marginTop: 8 }}>
              {plan ? <>this run: <b>{plan.jobs}</b> of {plan.jobs_total} jobs ·{" "}
                <b>{plan.scenes_rendering}</b> scene(s) · {plan.resolution} ·{" "}
                {plan.captions ? "captions burned" : "no captions"} ·{" "}
                {plan.backgrounds?.length ? plan.backgrounds.map((b: any) => `${b.label}${b.scenes > 1 ? ` ×${b.scenes}` : ""}`).join(", ") : "studio background"}{" "}
                · ≈ {fmtEta(plan.estimated_seconds)} ({plan.estimate_basis})</>
                : "the pre-run summary could not be read"}
            </div>
          )}
          {plan?.warnings?.length ? (
            <div className="mcp-warn" data-testid="plan-warnings">
              {plan.warnings.map((w: string, i: number) => <div key={i}>⚠ {w}</div>)}
            </div>
          ) : null}
        </div>}
      </Panel>

      {confirm && plan && (
        <Modal title="before you press run — what will happen" onClose={() => setConfirm(false)}>
          <div className="prerun">
            <div className="prerun-row"><span>scenes</span><b>{plan.scenes_rendering} of {plan.scenes_total}</b>
              {plan.scenes_skipped ? <em className="hint"> · skipped: {plan.scenes_skipped.map((i: number) => `#${i + 1}`).join(", ")}</em> : null}</div>
            <div className="prerun-row"><span>jobs</span><b>{plan.jobs} of {plan.jobs_total}</b>
              {plan.stages_skipped?.length ? <em className="hint"> · stages off: {plan.stages_skipped.join(", ")}</em> : null}</div>
            <div className="prerun-row"><span>resolution</span><b>{plan.resolution}</b></div>
            <div className="prerun-row"><span>background</span><b>
              {plan.backgrounds?.length ? plan.backgrounds.map((b: any) => `${b.label} ×${b.scenes}`).join(", ") : "project default (studio)"}
            </b></div>
            <div className="prerun-row"><span>captions</span><b>{plan.captions ? "burned in" : "not burned"}</b></div>
            <div className="prerun-row"><span>engines</span><b className="mono" style={{ fontSize: 11 }}>
              {Object.entries(plan.engines || {}).map(([k, v]) => `${k}:${v || "—"}`).join(" · ")}</b></div>
            <div className="prerun-row"><span>estimated time</span><b>≈ {fmtEta(plan.estimated_seconds)}</b>
              <em className="hint"> {plan.estimate_basis}</em></div>
            {plan.estimated_size_bytes ? (
              <div className="prerun-row"><span>estimated size</span><b>{fmtSize(plan.estimated_size_bytes)}</b></div>
            ) : null}
            {plan.warnings?.length ? (
              <div className="mcp-warn" style={{ marginTop: 8 }}>
                {plan.warnings.map((w: string, i: number) => <div key={i}>⚠ {w}</div>)}
              </div>
            ) : null}
            <div className="spread" style={{ marginTop: 12 }}>
              <button className="btn" onClick={() => setConfirm(false)}>back to editing</button>
              <button className="btn primary" data-testid="confirm-run" disabled={!!busy}
                onClick={() => { setConfirm(false); onRun({ skip_stages: skip, skip_scenes: sceneOff }); }}>
                ▶ Run now ({plan.jobs} jobs)
              </button>
            </div>
          </div>
        </Modal>
      )}

      {coreAsk ? (
        <Modal title={`skip ${coreAsk} for this run?`} onClose={() => setCoreAsk("")}>
          <Notice kind="warn" title={`${coreAsk} is one of the four stages a cut cannot exist without`}>
            Manual mode lets you switch it off — that is what you asked for, and nothing here is
            greyed out to hide it. What will happen: the run still executes every other stage, the
            finished MP4 is <b>not</b> produced, and the run ends <b>partial</b> with the missing
            stage named, never “completed”. You can re-run just that stage afterwards (or use GPU
            catch-up) and assembly will pick up where it stopped.
          </Notice>
          <div className="spread" style={{ marginTop: 12 }}>
            <button className="btn" onClick={() => setCoreAsk("")}>leave it on</button>
            <button className="btn danger" data-testid="confirm-core-off" onClick={confirmCoreOff}>
              skip {coreAsk} anyway
            </button>
          </div>
        </Modal>
      ) : null}
    </>
  );
}

/** Project-wide background. Per-scene overrides live on the storyboard rows. */
function BackgroundPanel({ proj, scenes, onChanged, act, busy }: {
  proj: Project; scenes: Scene[]; onChanged: () => void;
  act: (v: string, p: string, b?: any, ok?: string) => Promise<any>; busy: string;
}) {
  const settings = proj.settings || {};
  const [bg, setBg] = useState<Bg>(settings.background || null);
  const [saved, setSaved] = useState<Bg>(settings.background || null);
  useEffect(() => { setBg(settings.background || null); setSaved(settings.background || null); },
    [JSON.stringify(settings.background || null)]);      // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = JSON.stringify(bg) !== JSON.stringify(saved);
  const overrides = (scenes || []).filter((s) => (s.meta || {}).background);

  const save = async () => {
    const r = await act("background", `/projects/${proj.id}`, { settings: { ...settings, background: bg } },
                        "background saved — it renders on the next clip");
    if (r !== null) { setSaved(bg); onChanged(); }
  };

  return (
    <Panel title="Background & Style" right={
      <span className="row" style={{ gap: 6 }}>
        {dirty ? <Badge kind="warn">unsaved</Badge> : null}
        <button className="btn tiny primary" disabled={!dirty || !!busy} onClick={save}
          data-testid="bg-save">{busy === "background" ? "saving…" : "save background"}</button>
      </span>
    }>
      <div className="panel-b">
        <BackgroundPicker projectId={proj.id} value={bg} onChange={setBg} />
        {overrides.length ? (
          <div className="hint" style={{ marginTop: 6 }}>
            {overrides.length} scene(s) override this with their own background:{" "}
            {overrides.map((s) => `#${s.idx + 1}`).join(", ")} — clear them from the row's 🎨 button
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
