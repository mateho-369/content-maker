import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ProjectRow, StatusPayload } from "./api";
import { errText, useToast } from "./main";
import { Badge, Chip, Drawer, Modal, Skeleton, StatusBadge, TtsVoiceBadge, fmtTime, useHotkeys, useSticky } from "./ui";
import { ProjectView } from "./views/Project";
import { Wizard } from "./views/Wizard";
import { AdminView } from "./views/Admin";
import { HistoryView } from "./views/History";
import { GalleryPanel } from "./views/Gallery";
import { ClipsPanel } from "./views/Clips";

export type Route = { view: string; id?: string };

/** Everything that is not the current project lives in one slide-over instead of a
 *  page per concern. Nine routes used to mean nine full re-renders (and nine places
 *  to lose a project you were working on); a section id is all this needs now. */
const SECTIONS = [
  { key: "gallery", icon: "🎞", label: "Gallery", kbd: "g" },
  { key: "clips", icon: "✂️", label: "Clip a video", kbd: "c" },
  { key: "history", icon: "🕘", label: "History", kbd: "h" },
  { key: "services", icon: "🖥", label: "Services", kbd: "" },
  { key: "team", icon: "🤖", label: "AI Team", kbd: "" },
  { key: "characters", icon: "🧑‍🎤", label: "Characters", kbd: "" },
  { key: "voices", icon: "🎙", label: "Voices", kbd: "" },
  { key: "plugins", icon: "🧩", label: "Plugins / Engines", kbd: "" },
  { key: "settings", icon: "⚙️", label: "Settings", kbd: "," },
  { key: "memory", icon: "🔍", label: "Memory", kbd: "" },
];
const DRAWER_KEYS = new Set(SECTIONS.map((s) => s.key));

function parseHash(): { view: string; id?: string } {
  const h = location.hash.replace(/^#\/?/, "");
  const [view, id] = h.split("/");
  return { view: view || "projects", id };
}

export default function App() {
  const toast = useToast();
  const [route, setRoute] = useState<Route>(() => parseHash());
  const [pid, setPid] = useSticky<string>("studio.project", "");
  const [drawer, setDrawer] = useSticky<string>("studio.drawer", "");
  const [drawerW, setDrawerW] = useSticky<number>("studio.drawer.w", 520);
  const [wizard, setWizard] = useState(false);
  const [palette, setPalette] = useState(false);
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [statusErr, setStatusErr] = useState("");

  /* ── hash is an address, not a router: it opens a project or a drawer section ── */
  const applyHash = useCallback((h: { view: string; id?: string }) => {
    setRoute(h);
    if (h.view === "project" && h.id) { setPid(h.id); setDrawer(""); }
    else if (h.view === "projects") { setPid(""); setDrawer(""); }
    else if (DRAWER_KEYS.has(h.view)) setDrawer(h.view);
  }, [setPid, setDrawer]);

  useEffect(() => {
    applyHash(parseHash());
    const onhash = () => applyHash(parseHash());
    window.addEventListener("hashchange", onhash);
    return () => window.removeEventListener("hashchange", onhash);
  }, [applyHash]);

  const go = useCallback((view: string, id?: string) => {
    const h = "#/" + view + (id ? "/" + id : "");
    if (location.hash === h) { applyHash({ view, id }); return; }   // re-clicking the same row must still act
    location.hash = h;
  }, [applyHash]);

  const openSection = useCallback((k: string) => {
    setDrawer((cur) => (cur === k ? "" : k));
    location.hash = k ? `#/${k}` : (pid ? `#/project/${pid}` : "#/projects");
  }, [setDrawer, pid]);

  const selectProject = useCallback((id: string) => {
    setPid(id);
    location.hash = id ? `#/project/${id}` : "#/projects";
  }, [setPid]);

  const refreshStatus = useCallback(async (silent = true) => {
    try {
      setStatus(await api<StatusPayload>("/status"));
      setStatusErr("");
    } catch (e) {
      const msg = errText(e);
      setStatusErr(msg);
      if (!silent) toast(msg, "err");
    }
  }, [toast]);
  useEffect(() => {
    refreshStatus(true);
    const t = setInterval(() => refreshStatus(true), 15000);
    return () => clearInterval(t);
  }, [refreshStatus]);

  useHotkeys({
    "mod+k": () => setPalette((p) => !p),
    "mod+b": () => openSection(drawer ? "" : "gallery"),
    "mod+g": () => openSection("gallery"),
    "mod+c": () => openSection("clips"),
    "mod+h": () => openSection("history"),
    "mod+,": () => openSection("settings"),
    "mod+shift+n": () => setWizard(true),
    "escape": () => { if (palette) setPalette(false); },
  });

  const rail = useProjectRail(pid);

  return (
    <div className="shell ws">
      <div className="topbar">
        <span className="brand">◈ Khmer AI Content Studio</span>
        {pid ? (
          <select className="projpick" data-testid="project-picker" value={pid}
            onChange={(e) => selectProject(e.target.value)} title="switch project without leaving the workspace">
            {!rail.rows.some((r) => r.id === pid) ? <option value={pid}>{rail.titleOf(pid)}</option> : null}
            {rail.rows.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}
          </select>
        ) : <span className="crumb">no project open</span>}
        <span className="spacer" />
        {status ? (
          <span className="row" style={{ gap: 6 }}>
            <span className={`statusdot ${statusErr ? "bad" : ""}`} />
            <span className="hint">{statusErr ? "API error — " + statusErr.slice(0, 60)
              : `v${status.version} · ${status.machine?.profile || "auto"}`}</span>
          </span>
        ) : null}
        <TtsVoiceBadge status={status} variant="pill" />
        <button className="btn tiny" onClick={() => refreshStatus(false)} title="re-probe the engines">⟳</button>
        <button className="btn tiny" data-testid="open-palette" onClick={() => setPalette(true)}
          title="jump to a project, panel or setting (⌘K)">⌘K</button>
      </div>

      <div className="body">
        <div className="side" data-testid="project-rail">
          <div className="rail-head">
            <button className="btn primary wide" data-testid="new-project" onClick={() => setWizard(true)}>
              + New project
            </button>
            <input className="input" placeholder="filter projects" value={rail.q} data-testid="rail-search"
              onChange={(e) => rail.setQ(e.target.value)} />
            <div className="row" style={{ gap: 4 }}>
              <select value={rail.st} onChange={(e) => rail.setSt(e.target.value)} title="status filter">
                <option value="">any status</option>
                {["draft", "ready", "review", "rendering", "done", "failed"].map((s) => <option key={s}>{s}</option>)}
              </select>
              <select value={rail.md} onChange={(e) => rail.setMd(e.target.value)} title="mode filter">
                <option value="">A + B</option><option value="A">A · Director</option><option value="B">B · Auto</option>
              </select>
              <Chip on={rail.mine} onClick={() => rail.setMine((v: boolean) => !v)}
                title="only projects with a run on this machine">recent</Chip>
            </div>
          </div>

          <div className="rail-list" data-testid="rail-list">
            {rail.loading ? <Skeleton rows={5} /> : rail.rows.length === 0 ? (
              <div className="hint" style={{ padding: 10 }}>
                {rail.err || "no project matches — “+ New project” starts one, and nothing you type is lost between panels any more"}
              </div>
            ) : rail.rows.map((r) => (
              <button key={r.id} className={`projrow ${pid === r.id ? "on" : ""}`} data-testid={`rail-${r.id}`}
                onClick={() => selectProject(r.id)} title={r.script_excerpt || r.title}>
                <span className="projrow-main">
                  <b>{r.title}</b>
                  <span className="hint">
                    {r.mode} · {r.content_type} · {r.scene_count} scenes · {r.run_count} runs · {fmtTime(r.updated_at)}
                  </span>
                </span>
                <StatusBadge status={r.last_run_status || r.status} />
              </button>
            ))}
          </div>

          <div className="rail-nav" data-testid="section-nav">
            {SECTIONS.map((n) => (
              <button key={n.key} className={`nav ${drawer === n.key ? "on" : ""}`} data-testid={`nav-${n.key}`}
                onClick={() => openSection(n.key)}>
                <span>{n.icon}</span>{n.label}
              </button>
            ))}
          </div>
          <div className="mini">one server · one page · API :8000 · Ollama :11434 · RVC :9513 · ComfyUI :8188</div>
        </div>

        <div className="main">
          {statusErr && !pid ? (
            <div style={{ padding: "10px 18px 0" }}>
              <div className="errbar">⚠ Studio API error: {statusErr}</div>
            </div>
          ) : null}
          {pid
            ? <ProjectView projectId={pid} onOpen={go} />
            : <StartPane rows={rail.rows} status={status} onOpen={selectProject} onNew={() => setWizard(true)}
                onSection={openSection} />}
        </div>
      </div>

      <Drawer open={!!drawer} onClose={() => openSection("")} width={drawerW} onWidth={setDrawerW}
        testid="drawer" title={SECTIONS.find((s) => s.key === drawer)?.label || "studio"}>
        {drawer === "gallery" ? <GalleryPanel onOpen={(v, id) => { openSection(""); if (id) selectProject(id); }} /> : null}
        {drawer === "clips" ? <ClipsPanel /> : null}
        {drawer === "history" ? <HistoryView status={status} onOpen={(v: string, id?: string) => { openSection(""); go(v, id); }} /> : null}
        {["services", "team", "plugins", "characters", "voices", "settings", "memory"].includes(drawer) ? (
          <AdminView tab={drawer} status={status} onNavigate={(v: string, id?: string) => { openSection(v); go(v, id); }} />
        ) : null}
      </Drawer>

      {wizard ? (
        <div className="wizwrap" data-testid="wizard-overlay">
          <Wizard onClose={() => setWizard(false)}
            onCreated={(id: string) => { setWizard(false); selectProject(id); toast("project created — it is open in the workspace", "ok"); }} />
        </div>
      ) : null}

      {palette ? (
        <CommandPalette rows={rail.rows} sections={SECTIONS} pid={pid}
          onClose={() => setPalette(false)} onProject={selectProject} onSection={openSection}
          onNew={() => { setPalette(false); setWizard(true); }} />
      ) : null}
    </div>
  );
}

/** The rail's data: one debounced search against the API, kept at the shell level so
 *  switching projects never re-fetches the whole list. */
function useProjectRail(pid: string) {
  const [rows, setRows] = useState<ProjectRow[]>([]);
  const [all, setAll] = useState<ProjectRow[]>([]);
  const [q, setQ] = useState("");
  const [st, setSt] = useState("");
  const [md, setMd] = useState("");
  const [mine, setMine] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    let stop = false;
    const t = window.setTimeout(async () => {
      try {
        const r = await api<{ projects: ProjectRow[] }>("/projects", { query: { search: q, status: st, mode: md } });
        if (stop) return;
        setRows(r.projects || []); setAll((prev) => (prev.length && !q && !st && !md ? prev : r.projects || prev));
        setErr("");
      } catch (e) { if (!stop) setErr(errText(e)); }
      if (!stop) setLoading(false);
    }, q ? 260 : 0);
    return () => { stop = true; window.clearTimeout(t); };
  }, [q, st, md]);

  // A project created this session must appear even if the list fetch has not
  // caught up — but only while nothing is filtered: rescuing the open project past a
  // search box would make the filter look broken (it would always show ≥1 row).
  useEffect(() => {
    if (!pid || (q || st || md)) return;
    if (rows.some((r) => r.id === pid)) return;
    api<{ project: any }>(`/projects/${pid}`)
      .then((r) => setRows((x) => (x.some((y) => y.id === r.project.id) ? x : [r.project, ...x].slice(0, 400))))
      .catch(() => { /* the shell already shows the project error */ });
  }, [pid, q, st, md, rows]);

  const shown = useMemo(() => (mine ? rows.filter((r) => (r.run_count || 0) > 0) : rows), [rows, mine]);
  const titleOf = useCallback((id: string) => all.find((r) => r.id === id)?.title || id, [all]);
  return { rows: shown, all, q, setQ, st, setSt, md, setMd, mine, setMine, loading, err, titleOf };
}

/** The first screen: an empty workspace is where a manual user decides what to do,
 *  so it names what is running and what to press. */
function StartPane({ rows, status, onOpen, onNew, onSection }: {
  rows: ProjectRow[]; status: StatusPayload | null; onOpen: (id: string) => void;
  onNew: () => void; onSection: (k: string) => void;
}) {
  const caps = status?.capabilities || {};
  const list = rows.slice(0, 6);
  return (
    <div className="pad start-pane">
      <div className="start-hero">
        <h2>Nothing open</h2>
        <p className="hint">
          One page for the whole pipeline: create a project (⌘⇧N), then edit the board, the manual
          switches, captions and the QA gate without a page swap. Pick a project on the left, or start
          from the most recent one below.
        </p>
        <div className="row" style={{ gap: 6, marginTop: 10 }}>
          <button className="btn primary" data-testid="start-new" onClick={onNew}>+ New project</button>
          {list.length ? (
            <button className="btn" data-testid="start-resume" onClick={() => onOpen(list[0].id)}>
              resume “{list[0].title.slice(0, 26)}”
            </button>
          ) : null}
          <button className="btn" onClick={() => onSection("gallery")}>🎞 gallery</button>
          <button className="btn" onClick={() => onSection("clips")}>✂️ clip a video</button>
          <button className="btn" onClick={() => onSection("settings")}>⚙️ settings</button>
        </div>
      </div>
      <div className="row" style={{ gap: 6, flexWrap: "wrap", margin: "14px 0" }}>
        {Object.entries(caps).map(([k, v]: [string, any]) => (
          <Badge key={k} kind={v?.available || v?.ok || v === true ? "ok" : "warn"}
            title={typeof v === "object" ? JSON.stringify(v).slice(0, 200) : String(v)}>
            {k}: {typeof v === "object" ? (v?.label || v?.engine || (v?.available || v?.ok ? "ready" : "off")) : String(v)}
          </Badge>
        ))}
        {!Object.keys(caps).length ? <span className="hint">engine status arrives with /api/status</span> : null}
      </div>
      {list.length ? (
        <div className="start-recent" data-testid="start-recent">
          <h3>recent projects</h3>
          {list.map((r) => (
            <button key={r.id} className="projrow" onClick={() => onOpen(r.id)} data-testid={`start-${r.id}`}>
              <span className="projrow-main"><b>{r.title}</b>
                <span className="hint">{r.content_type} · {r.scene_count} scenes · updated {fmtTime(r.updated_at)}</span></span>
              <StatusBadge status={r.last_run_status || r.status} />
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** ⌘K: type to jump. A workspace with everything docked needs one fast way to point
 *  at a thing, or you end up clicking through rails to find a project. */
function CommandPalette({ rows, sections, pid, onClose, onProject, onSection, onNew }: {
  rows: ProjectRow[]; sections: { key: string; icon: string; label: string }[]; pid: string;
  onClose: () => void; onProject: (id: string) => void; onSection: (k: string) => void; onNew: () => void;
}) {
  const [q, setQ] = useState("");
  const box = useRef<HTMLInputElement | null>(null);
  useEffect(() => { box.current?.focus(); }, []);
  const hay = q.trim().toLowerCase();
  const items = useMemo(() => {
    const proj = rows.filter((r) => !hay || r.title.toLowerCase().includes(hay)).slice(0, 8)
      .map((r) => ({ kind: "project" as const, key: `p${r.id}`, label: r.title, hint: `${r.scene_count} scenes`, run: () => onProject(r.id) }));
    const sec = sections.filter((s) => !hay || s.label.toLowerCase().includes(hay))
      .map((s) => ({ kind: "section" as const, key: `s${s.key}`, label: `${s.icon} ${s.label}`, hint: "panel", run: () => onSection(s.key) }));
    const acts = [
      { kind: "action" as const, key: "a-new", label: "+ New project", hint: "wizard", run: () => onNew() },
      ...(pid ? [{ kind: "action" as const, key: "a-close", label: "close the open project", hint: "back to start", run: () => { location.hash = "#/projects"; onClose(); } }] : []),
    ].filter((a) => !hay || a.label.toLowerCase().includes(hay));
    return [...proj, ...sec, ...acts];
  }, [hay, rows, sections, pid, onProject, onSection, onNew, onClose]);
  const [sel, setSel] = useState(0);
  useEffect(() => { setSel(0); }, [q]);

  return (
    <Modal title="jump to anything" onClose={onClose}>
      <input ref={box} className="input" data-testid="palette-input" placeholder="project, panel or action…"
        value={q} onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setSel((x) => Math.min(items.length - 1, x + 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setSel((x) => Math.max(0, x - 1)); }
          if (e.key === "Enter") { e.preventDefault(); const it = items[sel]; if (it) { it.run(); onClose(); } }
        }} />
      <div className="palette-list" data-testid="palette-list">
        {items.length === 0 ? <div className="hint" style={{ padding: 10 }}>nothing matches “{q}”</div> : null}
        {items.map((it, i) => (
          <button key={it.key} className={`palette-item ${i === sel ? "on" : ""}`}
            onMouseEnter={() => setSel(i)}
            onClick={() => { it.run(); onClose(); }}>
            <span>{it.label}</span><em className="hint">{it.hint}</em>
          </button>
        ))}
      </div>
    </Modal>
  );
}

export { SECTIONS };
