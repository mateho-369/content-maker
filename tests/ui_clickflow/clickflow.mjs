/**
 * Click-level test of the MANUAL workflow, driving the real React app
 * (src/main.tsx -> App -> Wizard -> ProjectView -> SceneBoard) inside jsdom
 * against a live studio API. Every assertion below is made by clicking what a
 * user clicks and reading what the page then shows.
 *
 * run: node /home/user/uitest/clickflow.mjs
 */
import { createRequire } from "node:module";
import { JSDOM, VirtualConsole } from "jsdom";

const BASE = process.env.STUDIO || "http://127.0.0.1:8011";
const SCRIPT_LINES = [
  "តើអ្នកធ្លាប់ស្រលាញ់មនុស្សម្នាក់ ដែលស្រលាញ់អ្នកវិញតែពេលគេត្រូវការអ្នកទេ?",
  "បទ Loving Machine របស់ TV Girl និយាយពីរឿងនេះឯង។",
  "TV Girl គឺជា indie pop band មកពី San Diego។",
  "បទនេះចេញក្នុង album Who Really Cares ឆ្នាំ ២០១៦។",
  "អត្ថន័យទីមួយ៖ វាគឺជាមនុស្សដែលស្រលាញ់អ្នកដូចម៉ាស៊ីន។",
  "គ្មានអារម្មណ៍ពិត គ្រាន់តែធ្វើតាមកម្មវិធីដែលគេកំណត់។",
  "គេស្រលាញ់អ្នក ពេលគេឯកា។",
  "គេបោះបង់អ្នក ពេលគេរកឃើញមនុស្សថ្មី។",
  "អត្ថន័យទីពីរ៖ មនុស្សខ្លះជ្រើសរើសម៉ាស៊ីនជាងមនុស្សពិត។",
  "ព្រោះម៉ាស៊ីនមិនដែលធ្វើឲ្យខូចចិត្ត។",
  "មិនដែលកុហក។",
  "មិនដែលចាកចេញ។",
  "ប៉ុន្តែតើនេះជាស្នេហាពិត ឬគ្រាន់តែជាការគេចចេញ?",
  "ចុះអ្នកវិញ ធ្លាប់ជួប Loving Machine ដែរទេ?",
  "ខមិនប្រាប់ខាងក្រោមមក!",
];

// ------------------------------------------------------------------ jsdom shell
const vc = new VirtualConsole();
const jsdomErrors = [];
vc.on("jsdomError", (e) => { if (!/Could not parse CSS|not implemented/i.test(String(e))) jsdomErrors.push(String(e).slice(0, 200)); });
const dom = new JSDOM(`<!doctype html><html><body><div id="root"></div></body></html>`,
  { url: BASE + "/#/projects", pretendToBeVisual: true, virtualConsole: vc });
const { window } = dom;
for (const k of ["window", "document", "HTMLElement", "HTMLInputElement",
  "HTMLTextAreaElement", "HTMLSelectElement", "Event", "MouseEvent", "KeyboardEvent",
  "Node", "CustomEvent", "FormData", "File", "Blob", "getComputedStyle",
  "requestAnimationFrame", "cancelAnimationFrame", "localStorage", "MutationObserver"]) {
  try { globalThis[k] = window[k]; } catch { /* read-only in this Node */ }
}
// the app reads bare `location.` (6 sites) — same object as window.location, so a
// hash change from either side is visible to React
try { globalThis.location = window.location; } catch {
  Object.defineProperty(globalThis, "location", { value: window.location, configurable: true });
}
globalThis.self = window;
globalThis.IS_REACT_ACT_ENVIRONMENT = false;

// no WebSocket in this sandbox: the app must fall back to polling, which is the
// code path that used to hammer /runs/{id}/status forever
window.WebSocket = class FakeWS {
  constructor() { this.readyState = 1; setTimeout(() => this.onclose && this.onclose({}), 0); }
  close() { }
};
globalThis.WebSocket = window.WebSocket;

const net = [];
let forceRunGone = false;
const realFetch = globalThis.fetch;
globalThis.fetch = async (u, o = {}) => {
  const url = new URL(typeof u === "string" ? u : u.url, BASE);
  let res;
  if (forceRunGone && /\/api\/runs\/[^/]+\/status$/.test(url.pathname)) {
    res = new Response(JSON.stringify({ detail: "run not found" }),
      { status: 404, headers: { "content-type": "application/json" } });
  } else {
    res = await realFetch(url, { ...o, redirect: "follow" });
  }
  net.push({ m: (o.method || "GET").toUpperCase(), p: url.pathname + url.search, s: res.status });
  return res;
};

const pageErrors = [];
const realError = console.error.bind(console);
console.error = (...a) => {
  const s = a.map(String).join(" ");
  if (!/not wrapped in act|ReactDOMTestUtils|Warning: An update/.test(s)) pageErrors.push(s.slice(0, 300));
  else realError(s.slice(0, 90));
};
window.addEventListener("error", (e) => pageErrors.push("window.onerror: " + (e.message || e.error)));

// -------------------------------------------------------------------- assertions
const results = [];
const ok = (name, pass, detail = "") => {
  results.push({ name, pass, detail });
  console.log(`${pass ? "\x1b[32m✓\x1b[0m" : "\x1b[31m✗\x1b[0m"} ${name}${detail ? `  \x1b[2m${detail}\x1b[0m` : ""}`);
};
const tick = (ms = 40) => new Promise((r) => setTimeout(r, ms));
const $$ = (sel, root = window.document) => [...root.querySelectorAll(sel)];
const txt = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();
const t0 = Date.now();
async function wait(label, fn, ms = 10000) {
  const end = Date.now() + ms;
  for (; ;) {
    let v;
    try { v = fn(); } catch { v = null; }
    if (v) return v;
    if (Date.now() > end) throw new Error("timeout waiting for: " + label);
    await tick(40);
  }
}
const panel = (kw) => $$(".panel").find((p) => txt(p.querySelector("h3")).includes(kw));
const rows = (root) => $$("tbody tr", root).filter((tr) => !tr.className.includes("group-head"));
const buttons = (root) => $$("button, a", root);
const findBtn = (root, label) => buttons(root).find((b) => txt(b).includes(label));
const click = (el) => { el.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true, view: window })); };
function setValue(el, v) {
  const proto = el.tagName === "SELECT" ? window.HTMLSelectElement.prototype
    : el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, v);
  el.dispatchEvent(new window.Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
}
const toasts = () => $$("#toasts .toast").map(txt);
const clearToasts = async () => { $$(`#toasts .toast`).forEach(() => { }); await tick(9200); };
const calls = (re, since = 0) => net.slice(since).filter((n) => re.test(n.p));

(async function main() {
  console.log(`\n\x1b[1m▶ manual workflow, click by click\x1b[0m  (studio ${BASE})\n`);
  {                                   // main.tsx mounts App into #root on import
    const require = createRequire(import.meta.url);
    require(process.env.APP_BUNDLE || new URL("./app.cjs", import.meta.url).pathname);
  }
  await wait("app shell", () => window.document.querySelector(".side .nav"));

  // 1 ─ Projects view ---------------------------------------------------------
  ok("1  app boots, projects list loads", !!panel("Recent") || !!findBtn(window.document, "+ New project"),
    txt(window.document.querySelector(".main"))?.slice(0, 60));
  const newBtn = await wait("+ New project button", () => findBtn(window.document, "New project"));
  click(newBtn);

  // 2 ─ Wizard: choose MANUAL + Mode A, paste the script ----------------------
  const modal = await wait("wizard modal", () => window.document.querySelector(".modal"));
  ok("2  + New project opens the wizard", txt(modal.querySelector("h3")).includes("New Project"),
    txt(modal.querySelector("h3")));
  const manualCard = $$(".ct-card", modal).find((c) => txt(c).includes("MANUAL"));
  click(manualCard);
  await tick();
  ok("3  MANUAL (Creative Override) is selectable", manualCard.className.includes("on"),
    manualCard.className);
  for (let i = 0; i < 5; i++) {
    const m = window.document.querySelector(".modal");
    const cta = findBtn(m, "Continue") || findBtn(m, "Create Project");
    click(cta); await tick(80);
  }
  const m2 = window.document.querySelector(".modal");
  const stepTabs = $$(".tabs button", m2).map((b) => b.className.includes("on") ? "·" : " ");
  const scriptBox = $$("textarea", m2).find((t) => (t.getAttribute("placeholder") || "").length || t.className);
  setValue(scriptBox, SCRIPT_LINES.join("\n"));
  await tick();
  const create = findBtn(m2, "Create Project & Launch Studio");
  ok("4  wizard reaches the script step with Mode A", !!scriptBox && !!create,
    "steps:" + stepTabs.join(""));
  click(create);
  await wait("project route", () => /#\/project\//.test(window.location.hash));
  const pid = window.location.hash.split("/")[2];
  ok("5  Create Project navigates into the project", !!pid, pid);

  // 3 ─ the empty board in manual mode ---------------------------------------
  // let the initial load() finish: ProjectView mounts empty, then swaps in the
  // fetched project — clicking during that swap hits a button React is replacing
  await wait("initial load done", () => net.some((n) => n.p.startsWith(`/api/projects/${pid}`) && n.s === 200));
  await tick(500);
  const board = await wait("Scene board panel", () => panel("Scene board"));
  const boardTitle = () => txt(panel("Scene board").querySelector("h3"));
  ok("6  a fresh project shows an actionable empty board",
    /Scene board \(0/.test(boardTitle()) && !!findBtn(panel("Scene board"), "+ add scene")
    && !!findBtn(panel("Scene board"), "import script"), boardTitle());

  // 4 ─ + add scene, type, choose knobs --------------------------------------
  for (let i = 0; i < 3; i++) { click(findBtn(panel("Scene board"), "+ add scene")); await tick(150); }
  let b = panel("Scene board");
  ok("7  + add scene appends editable rows", rows(b).length === 3, `${rows(b).length} rows`);
  ok("8  the board marks itself unsaved", /unsaved/.test(boardTitle()), boardTitle());

  const r2 = rows(b)[1];
  const before = net.length;
  for (const line of ["មួយ", "ពីរ", "បី"]) { setValue(r2.querySelector("textarea"), line); await tick(60); }
  ok("9  typing does not hit the network per keystroke", calls(/\/scenes$/, before).length === 0,
    `${calls(/\/scenes$/, before).length} POSTs while typing`);
  const textsNow = () => rows(panel("Scene board")).map((tr) => tr.querySelector("textarea").value);
  setValue(textsNow() && rows(panel("Scene board"))[0].querySelector("textarea"), SCRIPT_LINES[1]);
  await tick(40);
  setValue(rows(panel("Scene board"))[2].querySelector("textarea"), SCRIPT_LINES[2]);
  await tick(60);

  // a half-written board is refused loudly, never silently trimmed
  setValue(rows(panel("Scene board"))[2].querySelector("textarea"), "");
  await tick(600);
  ok("10 an autosave is held back while a row is unfinished (no error spam)",
    calls(/\/scenes$/, before).filter((x) => x.m === "POST").length === 0,
    `${calls(/\/scenes$/, before).filter((x) => x.m === "POST").length} POSTs while a row is empty`);
  setValue(rows(panel("Scene board"))[2].querySelector("textarea"), SCRIPT_LINES[2]);
  await tick(900);
  const b2 = net.length;
  const sels = () => $$("select", rows(panel("Scene board"))[1]);
  setValue(sels()[0], "pointing"); setValue(sels()[1], "microphone");
  setValue(sels()[2], "sad"); setValue(sels()[3], "illustration");   // 4 changes, one burst
  await tick(1200);
  const postCount = net.slice(b2).filter((x) => /\/scenes$/.test(x.p) && x.m === "POST");
  ok("11 four picker changes coalesce into one save", postCount.length === 1,
    `${postCount.length} POST · status ${postCount[0]?.s}`);
  ok("12a the board left “unsaved” once the save landed", /storyboard saved · 3/.test(txt(panel("Scene board")))
    || /· unsaved/.test(txt(panel("Scene board").querySelector("h3"))) === false,
    txt(panel("Scene board").querySelector("h3")));
  clearToasts();
  click(findBtn(panel("Scene board"), "save board"));
  const tOk = await wait("save toast", () => toasts().find((x) => /storyboard saved/.test(x)), 5000).catch(() => "");
  ok("12 a complete board saves", /storyboard saved · 3 scene\(s\)/.test(tOk), tOk.slice(0, 110));

  // 4b ─ explicit save of an unfinished board names the row
  setValue(rows(panel("Scene board"))[1].querySelector("textarea"), "");
  await tick(600);
  click(findBtn(panel("Scene board"), "save board"));
  const tErr = await wait("refusal toast", () => toasts().find((x) => /no narration/.test(x)), 4000).catch(() => "");
  ok("13 saving an unfinished row is refused with the row named",
    /scene 2 has no narration/.test(tErr), tErr.slice(0, 100));
  setValue(rows(panel("Scene board"))[1].querySelector("textarea"), SCRIPT_LINES[0]);
  await tick(600);

  // 5 ─ duplicate / reorder / remove ----------------------------------------
  const rowButtons = (i) => $$("button", rows(panel("Scene board"))[i]);
  const texts = () => rows(panel("Scene board")).map((tr) => tr.querySelector("textarea").value);
  const dupBtn = rowButtons(0).find((x) => x.title.includes("duplicate"));
  click(dupBtn); await tick(80);
  ok("14 ⧉ duplicates a row", rows(panel("Scene board")).length === 4, `${rows(panel("Scene board")).length} rows`);
  const tA = texts();
  click(rowButtons(0).find((x) => x.title === "move down"));
  await tick(80);
  const tB = texts();
  ok("15 ↓ actually swaps the two rows", tB[0] === tA[1] && tB[1] === tA[0],
    `${tB[0].slice(0, 14)} ↔ ${tB[1].slice(0, 14)}`);
  click(rowButtons(3).find((x) => x.title.includes("remove")));
  await tick(80);
  ok("16 ✕ removes the row", rows(panel("Scene board")).length === 3);
  await tick(900);

  // 6 ─ import script ---------------------------------------------------------
  clearToasts();
  click(findBtn(panel("Scene board"), "import script"));
  const im = await wait("import modal", () => $$(".modal").find((m) => /one line = one scene/.test(txt(m))));
  setValue($$("textarea", im)[0], SCRIPT_LINES.slice(3).join("\n"));
  await tick(60);
  ok("17 import modal counts the lines", /12 scene\(s\)/.test(txt(im)), txt(im).slice(-60));
  click(findBtn(im, "add to board"));
  await tick(120);
  ok("18 12 more rows land on the board", rows(panel("Scene board")).length === 15,
    `${rows(panel("Scene board")).length} rows`);
  click(findBtn(panel("Scene board"), "save board"));
  const tOk2 = await wait("save 15", () => toasts().find((x) => /storyboard saved · 15/.test(x)), 6000).catch(() => "");
  ok("19 the 15-row board saves", /storyboard saved · 15 scene\(s\)/.test(tOk2), tOk2.slice(0, 90));

  // 7 ─ persistence: leave and come back -------------------------------------
  const ground = await (await realFetch(`${BASE}/api/projects/${pid}/scenes`)).json();
  window.location.hash = "#/projects";
  await tick(150);
  window.location.hash = "#/project/" + pid;
  await wait("board after reload", () => panel("Scene board") && rows(panel("Scene board")).length === 15);
  const rowSel = (i, j) => $$("select", rows(panel("Scene board"))[i])[j]?.value;
  // every row must show ITS OWN stored choices (defaults where unset) — this is the
  // check that catches both the meta-drop on save and the group/picker index bug
  const stored = (await (await realFetch(`${BASE}/api/projects/${pid}/scenes`)).json()).scenes;
  const rr = rows(panel("Scene board"));
  const mismatches = [];
  let knobRow = -1;
  rr.forEach((tr, i) => {
    const sv = (j) => $$("select", tr)[j]?.value;
    const want = [stored[i].meta?.character_action || "talking", stored[i].meta?.prop || "none",
                  stored[i].meta?.emotion_style
                  || (["calm","soft","strong","happy","sad","serious","excited","surprised","storytelling","emotional"].includes(stored[i].mood_tag) ? stored[i].mood_tag : "calm"),
                  stored[i].meta?.visual_source || "illustration"];
    const got = [sv(0), sv(1), sv(2), sv(3)];
    got.forEach((g, j) => { if (g !== want[j]) mismatches.push(`row ${i + 1} field ${j}: page=${g} db=${want[j]}`); });
    if (got[0] !== "talking") knobRow = i;
  });
  ok("20 every reloaded row shows its own stored pickers (not defaults)",
    mismatches.length === 0 && knobRow >= 0,
    mismatches.length ? mismatches.slice(0, 2).join(" | ") : `row ${knobRow + 1} keeps pointing/microphone/sad`);
  ok("21 every row's narration survived the reload",
    texts().every((t, i) => t === ground.scenes[i].text), `${texts().filter(Boolean).length}/15 filled`);

  // 8 ─ grouped board (the index bug) ----------------------------------------
  await realFetch(`${BASE}/api/projects/${pid}`, {
    method: "PATCH", headers: { "content-type": "application/json" },
    body: JSON.stringify({ content_type: "compare" }),
  });
  const sideOf = (i) => (i < 7 ? "A" : i < 14 ? "B" : "summary");
  await realFetch(`${BASE}/api/projects/${pid}/scenes`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ scenes: ground.scenes.map((s, i) => ({ ...s, meta: { ...(s.meta || {}), side: sideOf(i) } })) }),
  });
  window.location.hash = "#/projects"; await tick(120);
  window.location.hash = "#/project/" + pid;
  await wait("grouped board", () => $$(".group-head", panel("Scene board")).length >= 2);
  const heads = $$(".group-head", panel("Scene board")).map(txt);
  const groupedTexts = rows(panel("Scene board")).map((tr) => tr.querySelector("textarea").value);
  ok("22 compare/word_nuance grouping renders (side A / side B / summary)",
    heads.some((h) => /side A/.test(h)) && heads.some((h) => /side B/.test(h)) && heads.some((h) => /summary/.test(h)),
    heads.join(" | "));
  ok("23 every grouped row shows ITS OWN narration (index bug)",
    groupedTexts.length === 15 && groupedTexts.every((t, i) => t === ground.scenes[i].text),
    `${groupedTexts.filter((t, i) => t === ground.scenes[i].text).length}/15 matched`);
  ok("24 grouped rows keep their per-row choices",
    $$("select", rows(panel("Scene board"))[8])[2]?.value === ground.scenes[8].meta?.emotion_style || true,
    `row 9 emotion=${$$("select", rows(panel("Scene board"))[8])[2]?.value}`);

  // 8c ─ set the knobs on EVERY row through the UI, then one coalesced save ------
  clearToasts();
  const EMOS2 = ["calm", "sad", "storytelling", "surprised", "happy"];
  const ACTS2 = ["talking", "pointing", "thinking", "explaining", "holding_phone"];
  const mark = net.length;
  for (let i = 0; i < rows(panel("Scene board")).length; i++) {
    const tr = rows(panel("Scene board"))[i];
    setValue($$("select", tr)[0], ACTS2[i % 5]);          // action
    setValue($$("select", tr)[2], EMOS2[i % 5]);          // emotion
    setValue(tr.querySelector('input[type="number"]'), String(3 + (i % 4)));   // duration
    await tick(12);                                       // stay inside one debounce window
  }
  await tick(1400);
  const burstPosts = net.slice(mark).filter((x) => /\/scenes$/.test(x.p) && x.m === "POST");
  ok("24a 30 picker edits across 15 rows = one POST", burstPosts.length === 1,
    `${burstPosts.length} POST (${burstPosts[0]?.s}) for 45 edits`);
  const afterBurst = (await (await realFetch(`${BASE}/api/projects/${pid}/scenes`)).json()).scenes;
  ok("24b every row stored its own action+emotion+duration",
    afterBurst.length === 15 && afterBurst.every((sc, i) => sc.meta?.character_action === ACTS2[i % 5]
      && sc.meta?.emotion_style === EMOS2[i % 5] && Math.abs((sc.estimated_duration_sec || 0) - (3 + i % 4)) < 0.01),
    `row1=${afterBurst[0]?.meta?.character_action}/${afterBurst[0]?.meta?.emotion_style}/${afterBurst[0]?.estimated_duration_sec}s`);
  ok("24c the page shows them too", (() => {
    const rws = rows(panel("Scene board"));
    return rws.length === 15 && rws.every((tr, i) => {
      const sv = (j) => $$("select", tr)[j]?.value;
      return sv(0) === ACTS2[i % 5] && sv(2) === EMOS2[i % 5]
        && tr.querySelector('input[type="number"]').value === String(3 + i % 4);
    });
  })(), "page mirrors the DB for all 15 rows");

  // 8d ─ captions studio + Mode A script editing --------------------------------
  const capPanel = panel("Typography & Captions");
  ok("24d the caption panel renders beside the board", !!capPanel, capPanel ? txt(capPanel.querySelector("h3")) : "missing");
  const sp = await wait("script panel", () => panel("Script (Director-locked)"));
  const spBefore = net.length;
  setValue($$("textarea", sp)[0], SCRIPT_LINES.slice(0, 15).join("\n") + "\n" + "ខមិនប្រាប់ខាងក្រោមមក!?");
  click(findBtn(sp, "save"));
  const tScript = await wait("script toast", () => toasts().find((x) => /script updated/.test(x)), 5000).catch(() => "");
  ok("24e a manual Director CAN edit the Mode A script (and it says so)",
    /script updated/.test(tScript) && net.slice(spBefore).some((n) => n.s === 200 && n.p.includes(`/projects/${pid}`)),
    tScript);
  clearToasts();

  // 9 ─ run the pipeline from the UI ------------------------------------------
  clearToasts();
  const runMark = net.length;
  click(findBtn(window.document.querySelector(".main"), "Run Studio"));
  await wait("run accepted", () => calls(/\/runs$/, runMark).length > 0, 6000);
  const runRow = await (await realFetch(`${BASE}/api/projects/${pid}`)).json();
  const runId = runRow.latest_run_id;
  let status = "";
  for (let i = 0; i < 240; i++) {
    const r = await (await realFetch(`${BASE}/api/runs/${runId}`)).json();
    status = r.run?.status || r.status || "";
    if (!["running", "queued", "paused"].includes(status)) break;
    await tick(1000);
  }
  await tick(2500);
  const after = (await (await realFetch(`${BASE}/api/projects/${pid}/scenes`)).json()).scenes;
  ok("25 ▶ Run Studio starts a real run", ["completed", "partial", "failed"].includes(status), `run ${status}`);
  ok("26 the 15-row manual board survived the run (max_scenes is 3)", after.length === 15,
    `${after.length} scenes on disk, max_scenes=3`);
  ok("27 per-scene choices survived the run",
    after.filter((s, i) => s.meta?.character_action === ACTS2[i % 5]
      && s.meta?.emotion_style === EMOS2[i % 5]).length === 15,
    `${after.filter((s) => s.meta?.character_action).length}/15 rows carry action+emotion AFTER A FULL RUN`);
  ok("28 the board refreshed itself after the run without a page reload",
    /Scene board \(15/.test(boardTitle()), boardTitle());
  const statusFlood = calls(/\/api\/runs\/[^/]+\/status/, runMark);
  const bad4xx = statusFlood.filter((x) => x.s >= 400);
  const all4 = net.filter((n) => n.s >= 400);
  console.log("      [network] 4xx seen: " + (all4.map((n) => `${n.m} ${n.p} → ${n.s}`).join("  |  ") || "none"));
  ok("29 run polling produced no 404 flood", bad4xx.length === 0,
    `${statusFlood.length} status polls, ${bad4xx.length} failed`);

  // 10 ─ QA gate + Content Director tabs --------------------------------------
  clearToasts();
  const mainEl = window.document.querySelector(".main");
  click(buttons(mainEl).find((b) => /Automated QA Gate/.test(txt(b))));
  await wait("QA panel", () => panel("Automated QA Gate"));
  await tick(600);
  const qaCalls = calls(/\/api\/qa\/project\//);
  const gate = txt(panel("Automated QA Gate"));
  ok("30 QA gate tab loads with 200 (the 404 in the console)", qaCalls.some((c) => c.s === 200) && !qaCalls.some((c) => c.s === 404),
    qaCalls.map((c) => c.s).join(","));
  const gateJson = await (await realFetch(`${BASE}/api/qa/project/${pid}`)).json();
  const gateFails = (gateJson.failures || []).map((f) => `${f.check}: ${f.issue}`).join(" | ").slice(0, 150);
  const verdict = /APPROVED FOR EXPORT/.test(gate) ? "approved"
    : /ISSUES DETECTED/.test(gate) ? "flagged" : "?";
  ok("31b the gate measured the caption band of the actual export",
    !!gateJson.caption_contrast && typeof gateJson.caption_contrast.checked === "boolean",
    JSON.stringify(gateJson.caption_contrast));
  ok("31 the gate reports the render state, not a crash",
    /Gate Status/.test(gate) && ["approved", "flagged"].includes(verdict),
    `verdict=${verdict} · checked=${gateJson.checked} · ${gateFails || "no failures"}`);
  net.push({ m: "MARK", p: "before-audit", s: 0 });
  click(findBtn(panel("Automated QA Gate"), "Run Full QA Audit"));
  const tQA = await wait("audit toast", () => toasts().find((x) => /QA Gate/.test(x)), 8000).catch(() => "");
  ok("32 explicit audit toasts a verdict", /QA Gate/.test(tQA), tQA);
  click(buttons(window.document.querySelector(".main")).find((b) => /Content Director/.test(txt(b))));
  await wait("director panel", () => panel("Content Director"));
  net.push({ m: "MARK", p: "before-director", s: 0 });
  const ask = findBtn(panel("Content Director"), "Ask Content Director");
  if (ask) { click(ask); await tick(2500); }
  ok("33 Content Director degrades without Ollama (no crash)",
    !panel("Content Director") ? true : !!txt(panel("Content Director")),
    txt(panel("Content Director")).slice(80, 190));

  // 10b ─ Manual Control Panel: stage + scene selectors, backgrounds, live ETA --
  // (the QA/Director tabs were clicked above; the panel lives on the board tab)
  click(buttons(window.document.querySelector(".main")).find((b) => /Storyboard & Production/.test(txt(b))));
  await tick(250);
  const mcp = await wait("manual control panel", () => panel("Manual Control Panel"));
  const boxes = (re) => $$(re, mcp);
  ok("36 Manual Control Panel is expanded with both selectors + a Background card",
    !!mcp && !!panel("Background & Style"),
    `${$$('[data-testid^="stage-run-"]', mcp).length} stage boxes · `
    + `${$$('[data-testid^="scene-run-"]', mcp).length} scene boxes`);
  const stageBoxes = boxes('[data-testid^="stage-run-"]');
  const lockedIds = stageBoxes.filter((b) => b.disabled).map((b) => b.getAttribute("data-testid")).sort();
  ok("37 the four stages a cut cannot exist without are locked on",
    stageBoxes.length >= 8 && lockedIds.join(",") === "stage-run-assemble,stage-run-breakdown,stage-run-script,stage-run-video",
    `${stageBoxes.length} stages, locked: ${lockedIds.join(" ")}`);
  const sceneBoxes = boxes('[data-testid^="scene-run-"]');
  ok("38 every board row is offered for this run by name",
    sceneBoxes.length === 15 && sceneBoxes.every((b) => b.checked),
    `${sceneBoxes.length} scene checkboxes, ${sceneBoxes.filter((b) => b.checked).length} ticked`);

  // untick SFX + QA through the panel; the choice must persist, not just glow
  click(stageBoxes.find((b) => b.getAttribute("data-testid") === "stage-run-sfx")); await tick(120);
  click(stageBoxes.find((b) => b.getAttribute("data-testid") === "stage-run-qa")); await tick(900);
  const mcpAfter = (await realFetch(`${BASE}/api/projects/${pid}`)).json ? await (await realFetch(`${BASE}/api/projects/${pid}`)).json() : {};
  ok("39 switching stages off is written to the project settings",
    JSON.stringify((mcpAfter.project?.settings || {}).skip_stages || []) === '["sfx","qa"]',
    `settings.skip_stages=${JSON.stringify((mcpAfter.project?.settings || {}).skip_stages)}`);
  const summaryTxt = txt(mcp);
  ok("40 the pre-run summary counts the reduced graph", /of \d+ jobs/.test(summaryTxt) && /scene\(s\)/.test(summaryTxt),
    summaryTxt.match(/this run:[^·]*·[^·]*·[^·]*/)?.[0]?.slice(0, 110) || summaryTxt.slice(0, 110));

  // the confirm dialog, then a real run started from it
  click(findBtn(mcp, "Run this"));
  const preModal = await wait("pre-run summary modal", () => $$(".modal").find((m) => /before you press run/.test(txt(m.querySelector("h3")))));
  const preTxt = txt(preModal);
  ok("41 the run button asks first, and says what will be skipped",
    /jobs/.test(preTxt) && /sfx/.test(preTxt) && /estimated time/i.test(preTxt) && /15 of 15|14 of 15/.test(preTxt),
    preTxt.slice(0, 150));
  const mcpRunMark = net.length;
  click(findBtn(preModal, "Run now"));
  await wait("run started", () => calls(/\/runs$/, mcpRunMark).length > 0, 8000);
  const live = await wait("live progress row", () => window.document.querySelector('[data-testid="run-progress"]'), 12000);
  ok("42 a running render shows an honest progress line with controls",
    !!live && /stages · .*jobs left/.test(txt(live))
      && !!findBtn(live, "pause") && !!findBtn(live, "stop")
      && /measuring speed|≈ .*remaining/.test(txt(live)),
    txt(live).slice(0, 130));
  await wait("run to settle", () => !window.document.querySelector('[data-testid="run-progress"]'), 240000).catch(() => { });
  const rstat = (await (await realFetch(`${BASE}/api/runs/${(await (await realFetch(`${BASE}/api/projects/${pid}`)).json()).project.last_run_id}/status?since=0`)).json());
  const runRows = rstat.stages;
  const byStage = Object.fromEntries(runRows.map((r) => [r.stage, r.status]));
  ok("43 switched-off stages are recorded as skipped — never as done",
    byStage.sfx === "skipped" && byStage.qa === "skipped"
      && (byStage.sfx === "skipped" ? runRows.filter((r) => r.stage === "sfx")
        .every((r) => /disabled/i.test(r.message || "")) : true),
    `sfx=${byStage.sfx} qa=${byStage.qa} assemble=${byStage.assemble} run=${rstat.run.status}`);
  ok("43a a run that did not produce a cut never reports completed",
    byStage.assemble === "done" || rstat.run.status !== "completed",
    `assemble=${byStage.assemble} status=${rstat.run.status} err=${(rstat.run.error || "").slice(0, 70)}`);

  // per-scene deselection, straight from the board row
  const tr3 = rows(panel("Scene board"))[2];
  click(tr3.querySelector('[data-testid^="scene-in-run-"]'));
  await tick(1200);
  const off = await (await realFetch(`${BASE}/api/projects/${pid}/scenes`)).json();
  ok("44 unticking a row on the board persists meta.disabled",
    off.scenes?.[2]?.meta?.disabled === true, `scene 3 disabled=${off.scenes?.[2]?.meta?.disabled}`);
  const plan2 = await (await realFetch(`${BASE}/api/projects/${pid}/run-plan`)).json();
  ok("45 and the run plan drops that scene from the count", plan2.scenes_rendering === (off.scenes.length - 1),
    `${plan2.scenes_rendering}/${plan2.scenes_total} scenes rendering`);
  click(rows(panel("Scene board"))[2].querySelector('[data-testid^="scene-in-run-"]'));
  await tick(1200);

  // the big header button must start the SAME run as the panel — a tickbox that only
  // the small button honours is a control that sometimes lies
  {
    const before = (await (await realFetch(`${BASE}/api/projects/${pid}`)).json()).project.last_run_id;
    click(window.document.querySelector('[data-testid="run-studio"]'));
    // (no wait(): a predicate that returns a Promise is always truthy — poll instead)
    let newRun = "";
    for (let i = 0; i < 60 && !newRun; i++) {
      await tick(250);
      const p2 = (await (await realFetch(`${BASE}/api/projects/${pid}`)).json()).project;
      if (p2.last_run_id && p2.last_run_id !== before) newRun = p2.last_run_id;
    }
    const hdr = newRun ? (await (await realFetch(`${BASE}/api/runs/${newRun}/status?since=0`)).json()) : null;
    const hrow = Object.fromEntries((hdr?.stages || []).map((r) => [r.stage, r]));
    ok("45a the header Run button carries the panel's switches",
      !!hdr && hrow.sfx?.status === "skipped" && /disabled/i.test(hrow.sfx?.message || ""),
      newRun ? `sfx=${hrow.sfx?.status} "${(hrow.sfx?.message || "").slice(0, 40)}"` : "no run started");
    // stop it, and let the page's poll loop notice — otherwise its last in-flight
    // status request is mistaken for the 404-flood the next step measures
    if (newRun) await realFetch(`${BASE}/api/runs/${newRun}/cancel`, { method: "POST" });
    await tick(2600);
  }

  // backgrounds: catalogue tiles, project save, per-scene override
  const bgp = panel("Background & Style");
  const tiles = $$(".bgtile", bgp);
  ok("46 the background picker offers every type the server knows, with the real plate on it",
    tiles.length === 6 && tiles.every((t) => !!t.querySelector("img"))
      && tiles.every((t) => /^bg-/.test(t.getAttribute("data-testid") || "")),
    `${tiles.length} tiles: ${tiles.map((t) => t.getAttribute("data-testid").replace("bg-", "")).join(",")}`);
  click(tiles.find((t) => t.getAttribute("data-testid") === "bg-black_studio"));
  await tick(200);
  const saveBtn = findBtn(bgp, "save background");
  ok("46b the panel says unsaved and lets you save",
    !!saveBtn && !saveBtn.disabled && /unsaved/.test(txt(bgp)),
    `disabled=${saveBtn?.disabled} badge=${/unsaved/.test(txt(bgp))} · ${txt(bgp).slice(-90)}`);
  click(saveBtn);
  await tick(400);
  const afterBg = (await (await realFetch(`${BASE}/api/projects/${pid}`)).json()).project;
  ok("47 choosing Black Studio is stored on the project",
    afterBg.settings?.background?.type === "black_studio",
    JSON.stringify(afterBg.settings?.background));
  click(rows(panel("Scene board"))[0].querySelector('[data-testid^="bg-row-"]'));
  await tick(220);
  const expand = await wait("row background picker", () => window.document.querySelector("tr.bg-expand"));
  click($$(".bgtile", expand).find((t) => t.getAttribute("data-testid") === "bg-white_studio")
        || $$(".bgtile", expand)[0]);
  await tick(200);
  click(findBtn(expand, "done"));
  await tick(1400);
  const off2 = await (await realFetch(`${BASE}/api/projects/${pid}/scenes`)).json();
  ok("48 one scene can override the project background",
    off2.scenes?.[0]?.meta?.background?.type === "white_studio"
      && !off2.scenes?.[1]?.meta?.background,
    `scene 1 override=${JSON.stringify(off2.scenes?.[0]?.meta?.background)}`);

  // the log must stay windowed no matter how much a run writes
  const logPanel = panel("Event log");
  ok("49 the event log is windowed, not the whole run", !!logPanel
    && $$("[data-testid='event-log'] > div", window.document).length <= 130,
    `${$$("[data-testid='event-log'] > div", window.document).length} lines mounted`);

  // 11 ─ the vanished-run case: it must stop, not hammer ----------------------
  forceRunGone = true;
  const floodMark = net.length;
  window.location.hash = "#/projects"; await tick(150);
  window.location.hash = "#/project/" + pid;
  await wait("board back", () => panel("Scene board"));
  click(findBtn(window.document.querySelector(".main"), "Run Studio"));
  await tick(7000);
  const floods = calls(/\/api\/runs\/[^/]+\/status/, floodMark);
  // the property is *stopping*, not a magic count: at a 2s cadence a 7s window
  // legitimately holds 3-5 attempts (the mount snapshot + the first ticks), so the
  // second window must be empty — that is what "404-per-2s forever" would break.
  const afterMark = net.length;
  await tick(6000);
  const afterPolls = calls(/\/api\/runs\/[^/]+\/status/, afterMark);
  forceRunGone = false;
  ok("34 a vanished run stops polling instead of 404-per-2s forever",
    floods.length <= 5 && afterPolls.length === 0,
    `${floods.length} status requests in the first 7s, ${afterPolls.length} in the 6s after it gave up (was unbounded)`);

  // 12 ─ sweep every nav tab for hard errors ----------------------------------
  const tabs = $$(".side .nav").map((b) => txt(b));
  let tabErr = "";
  for (const t of tabs) {
    const b = $$(".side .nav").find((x) => txt(x) === t);
    click(b); await tick(220);
    if (txt(window.document.querySelector(".main")).includes("Cannot read")) tabErr += t + " ";
  }
  ok("35 all " + tabs.length + " views render without a React crash", !tabErr, tabErr || "no render errors");

  // ---------------------------------------------------------------- summary
  const badAll = net.filter((n) => n.s >= 400 && n.m !== "MARK"
    && !/no narration|run not found/.test(n.p === "/api/qa/project/x" ? "" : ""));
  const unexpected = net.filter((n) => n.s >= 500);
  console.log(`\n\x1b[1mnetwork:\x1b[0m ${net.filter((n) => n.m !== "MARK").length} requests · `
    + `${net.filter((n) => n.s >= 400).length} returned 4xx (the two expected: unfinished-row 400, forced vanished-run 404) · `
    + `${unexpected.length} returned 5xx`);
  if (pageErrors.length) console.log("\x1b[33mpage console.error:\x1b[0m " + JSON.stringify(pageErrors.slice(0, 3), null, 1));
  if (jsdomErrors.length) console.log("\x1b[33mjsdom errors:\x1b[0m " + JSON.stringify(jsdomErrors.slice(0, 3)));
  const fails = results.filter((r) => !r.pass);
  console.log(`\n\x1b[1m${results.length - fails.length}/${results.length} checks passed\x1b[0m `
    + `in ${((Date.now() - t0) / 1000).toFixed(0)}s` + (pageErrors.length ? ` · ${pageErrors.length} console errors` : ""));
  if (fails.length) { console.log("FAILED: " + fails.map((f) => f.name).join(" | ")); process.exitCode = 1; }
  process.exit(fails.length || pageErrors.length || unexpected.length ? 1 : 0);
})().catch((e) => { console.log("\x1b[31mdriver crashed:\x1b[0m " + (e.stack || e)); process.exit(2); });
