# `tests/ui_clickflow` — the manual workflow, clicked

`pytest` proves the API. This proves the **page**: it boots the real React app
(`ai_studio/frontend/src/main.tsx` → `App` → `Wizard` → `ProjectView` →
`SceneBoard`) in jsdom against a **live studio server**, then clicks what a
manual user clicks and asserts what the DOM shows afterwards.

```bash
./tests/ui_clickflow/run.sh          # 41 checks, ~30s, temp dir only
```

Exit code 0 = every check passed. Nothing is written inside the repo (bundle,
data dir and `node_modules/jsdom` go to a temp dir that is removed on exit).

## What it drives

| # | clicks | asserts |
|---|--------|---------|
| 1–5 | `+ New project` → **MANUAL (Creative Override)** → 5× `Continue →` → paste a 15-line Khmer script → `Create Project & Launch Studio` | wizard works, lands on `#/project/<id>` |
| 6–8 | look at the board | an empty project offers `+ add scene` / `⤓ import script`, and `+ add scene` appends editable rows marked `· unsaved` |
| 9–10 | type narration; blank one row | typing never hits the network; an unfinished row holds the autosave back instead of error-spamming |
| 11–13 | 4 picker changes in one burst | one coalesced `POST /scenes` (200), board leaves “unsaved” |
| 14 | `⧉`, `↓`, `✕` | duplicate / reorder / remove act on the right rows |
| 17–19 | `⤓ import script` → paste 12 lines → `add to board` → `save board` | 15 rows, `storyboard saved · 15 scene(s)` |
| 20–21 | navigate away and back | **every row shows its own stored text + its own action/prop/emotion/visual**, not defaults |
| 22–24 | PATCH `content_type=compare`, set `meta.side`, reload | group heads (⚖ side A / side B / summary) render and each grouped row keeps **its own** narration — this is the scene-index bug |
| 24a–24c | 45 picker/duration edits across 15 rows | one POST; every row stores `character_action` + `emotion_style` + duration; page mirrors DB |
| 24d–24e | caption panel; edit the Mode-A script and save | captions UI renders; a Director may still edit their own locked script |
| 25–29 | `▶ Run Studio`, wait for the finished run | 15 rows survive with `max_scenes=3`; choices survive; the board refreshes **without a page reload**; no 404 flood on run polling |
| 30–32 | open the QA tab, click `🛡️ Run Full QA Audit` | `GET /api/qa/project/<id>` is 200 (was 404 for an unbuilt project) and the gate reports the render state |
| 33 | `🤖 Ask Content Director` with Ollama offline | degrades to the deterministic analysis, no crash |
| 34 | force `/runs/{id}/status` to answer 404 | polling stops (≤2 requests) and the view recovers — was 40 minutes of 404s |
| 35 | click all 9 nav views | no React render error anywhere |

## Why it exists

`git show 377dd9a` / `ac58437` — the manual board was silently destroying what it
showed: `POST /scenes` dropped the picker keys, `meta` was re-filtered on every
run, a hand-made 15-scene board was truncated to `pipeline.max_scenes`, the rows
were indexed by group-relative counter (so grouped boards displayed blanks and
wrote to the wrong scene), the QA tab 404'd for unbuilt projects, and a stale run
id hammered `/runs/{id}/status` forever.

Run the driver against the pre-fix source and 6 headline behaviours reproduce
(blank narration cells, defaults instead of stored picks, meta wiped, 15 → 3
scenes after a run, QA 404). That is the check that these assertions are real.
