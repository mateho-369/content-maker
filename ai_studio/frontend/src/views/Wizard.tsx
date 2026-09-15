import React, { useEffect, useRef, useState } from "react";
import { api, Character, ContentDirectorAnalysis, ContentTypeMeta, Project, StylePreview, VoiceProfile } from "../api";
import { useToast, errText } from "../main";
import { Modal, Badge } from "../ui";

const STEPS = ["Control & Platform", "Content Format", "Character & Actions", "Voice & Emotion", "Pacing & Subs", "Script & Director"];

const PACES = [
  { key: "slow", label: "Slow", desc: "0.9× speech · 1.4s gap" },
  { key: "natural", label: "Natural", desc: "1.0× speech · 1.15s gap (default)" },
  { key: "brisk", label: "Brisk", desc: "1.08× speech · 0.95s gap" },
];

const EMOTIONAL_STYLES = [
  { key: "calm", label: "Calm", desc: "Even, warm, natural pace" },
  { key: "soft", label: "Soft", desc: "Gentle, slower, warm mids" },
  { key: "strong", label: "Strong", desc: "Authoritative, punchy, crisp" },
  { key: "happy", label: "Happy", desc: "Uptempo, brighter presence" },
  { key: "sad", label: "Sad", desc: "Deliberate, somber cadence" },
  { key: "serious", label: "Serious", desc: "Firm, focused, neutral" },
  { key: "excited", label: "Excited", desc: "Fast, energetic, high presence" },
  { key: "surprised", label: "Surprised", desc: "Punchy dynamic inflection" },
  { key: "storytelling", label: "Storytelling", desc: "Narrative cadence, warm low-mids" },
  { key: "emotional", label: "Emotional", desc: "Deeply resonant, expressive" },
];

const TARGET_PLATFORMS = [
  { key: "tiktok", label: "TikTok", aspect: "9:16 (720×1280)", icon: "🎵" },
  { key: "reels", label: "Instagram Reels", aspect: "9:16 (720×1280)", icon: "📸" },
  { key: "fb_reels", label: "Facebook Reels", aspect: "9:16 (720×1280)", icon: "📘" },
  { key: "shorts", label: "YouTube Shorts", aspect: "9:16 (720×1280)", icon: "▶" },
];

export function Wizard({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<"A" | "B">("A");
  const [controlMode, setControlMode] = useState<"auto" | "manual">("auto");
  const [platform, setPlatform] = useState("tiktok");
  const [ct, setCt] = useState("explainer");
  const [cts, setCts] = useState<ContentTypeMeta[]>([]);
  const [chars, setChars] = useState<Character[]>([]);
  const [characterId, setCharacterId] = useState("");
  const [visualSource, setVisualSource] = useState("character_action");
  const [emotionStyle, setEmotionStyle] = useState("calm");
  const [pace, setPace] = useState("natural");
  const [lineGap, setLineGap] = useState(1.15);
  const [burn, setBurn] = useState(true);
  const [subStyle, setSubStyle] = useState("clean");
  const [titleStyle, setTitleStyle] = useState("");
  const [previews, setPreviews] = useState<{ sub: StylePreview[]; title: StylePreview[] }>({ sub: [], title: [] });
  const [script, setScript] = useState("");
  const [topic, setTopic] = useState("");
  const [duration, setDuration] = useState(30);
  const [styleNotes, setStyleNotes] = useState("");
  const [voices, setVoices] = useState<VoiceProfile[]>([]);
  const [voiceId, setVoiceId] = useState("");
  const [busy, setBusy] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<ContentDirectorAnalysis | null>(null);

  const scriptRef = useRef<HTMLTextAreaElement | null>(null);
  const toast = useToast();

  const markSilent = () => {
    const ta = scriptRef.current;
    if (!ta) return;
    const a = ta.selectionStart, b = ta.selectionEnd;
    if (b <= a) { toast("select some text first, then mark it as not spoken", "warn"); return; }
    const sel = script.slice(a, b);
    if (sel.includes("[[")) { toast("selection already contains silent markup — pick plain text", "warn"); return; }
    const next = script.slice(0, a) + "[[silent: " + sel.trim() + "]]" + script.slice(b);
    setScript(next);
    toast("marked as not spoken — shown in captions, never read aloud", "ok");
    requestAnimationFrame(() => { ta.focus(); ta.setSelectionRange(a, a + next.length); });
  };

  useEffect(() => {
    api<{ types: ContentTypeMeta[] }>("/content-types").then((r) => setCts(r.types || [])).catch(() => {});
    api<{ characters: Character[] }>("/characters").then((r) => setChars(r.characters || [])).catch(() => {});
    api<{ voices: VoiceProfile[] }>("/voices").then((r) => setVoices(r.voices || [])).catch(() => {});
    api<{ subtitle_styles: StylePreview[]; title_styles: StylePreview[] }>("/style-previews")
      .then((r) => setPreviews({ sub: r.subtitle_styles || [], title: r.title_styles || [] }))
      .catch((e) => toast("style previews unavailable: " + errText(e), "warn"));
  }, []);

  const runContentDirector = async () => {
    const targetText = (topic || script || "").trim();
    if (!targetText) {
      toast("enter a topic or script snippet first to analyze", "warn");
      return;
    }
    setAnalyzing(true);
    try {
      const res = await api<ContentDirectorAnalysis>("/content-director/analyze", {
        method: "POST",
        json: { topic: targetText, script: script },
      });
      setAnalysis(res);
      if (res.recommended_content_type) setCt(res.recommended_content_type);
      if (res.recommended_emotion) setEmotionStyle(res.recommended_emotion);
      if (res.recommended_visual_source) setVisualSource(res.recommended_visual_source);
      toast("Content Director analyzed your idea!", "ok");
    } catch (e) {
      toast(errText(e), "err");
    } finally {
      setAnalyzing(false);
    }
  };

  const create = async () => {
    setBusy(true);
    try {
      const payload: any = {
        mode,
        content_type: ct,
        character_id: characterId,
        language: "km",
        target_duration: Number(duration) || 30,
        style_notes: styleNotes,
        voice_profile_id: voiceId,
        settings: {
          control_mode: controlMode,
          target_platform: platform,
          emotion_style: emotionStyle,
          visual_source: visualSource,
          tts: { pace, line_gap_sec: Number(lineGap) || 1.15, emotion_style: emotionStyle },
          assembly: { burn_captions: burn, subtitle_style: subStyle, title_style: titleStyle },
        },
      };
      if (mode === "A") {
        if (!script.trim()) throw new Error("Mode A needs the finished script pasted in.");
        payload.script = script;
      } else {
        payload.topic_hint = topic;
      }
      const r = await api<{ project: Project }>("/projects", { method: "POST", json: payload });
      toast(`project "${r.project.title}" created`, "ok");
      onCreated(r.project.id);
    } catch (e) {
      toast(errText(e), "err");
      setBusy(false);
    }
  };

  const next = () => { if (step < STEPS.length - 1) setStep(step + 1); else create(); };
  const back = () => setStep(Math.max(0, step - 1));
  const canNext = (() => {
    if (step === 0) return true;
    if (step === 1) return !!ct;
    if (step === 5) return mode === "A" ? script.trim().length >= 10 : topic.trim().length > 0;
    return true;
  })();

  return (
    <Modal title="New Project · Promax Creative Studio" onClose={onClose}>
      <div className="tabs">
        {STEPS.map((s, i) => (
          <button key={s} className={i === step ? "on" : ""} onClick={() => i < step || setStep(i)}>
            {`${i + 1}. ${s}`}
          </button>
        ))}
      </div>
      <div style={{ minHeight: 320 }}>
        {/* Step 0: Control Mode & Target Platform */}
        {step === 0 && (
          <div>
            <div style={{ marginBottom: 12 }}>
              <b>Creative Control Mode</b>
              <div className="cards" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 6 }}>
                <div className={`ct-card ${controlMode === "auto" ? "on" : ""}`} onClick={() => setControlMode("auto")}>
                  <b>🤖 AUTO (Content Director)</b>
                  <div className="hint" style={{ marginTop: 4 }}>
                    AI Content Director automatically selects viral hooks, character actions, emotions, pacing, and meme moments.
                  </div>
                </div>
                <div className={`ct-card ${controlMode === "manual" ? "on" : ""}`} onClick={() => setControlMode("manual")}>
                  <b>🎛️ MANUAL (Creative Override)</b>
                  <div className="hint" style={{ marginTop: 4 }}>
                    Full director control over every scene, character action, prop, voice emotion, and visual cut.
                  </div>
                </div>
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <b>Script Input Flow</b>
              <div className="cards" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 6 }}>
                <div className={`ct-card ${mode === "A" ? "on" : ""}`} onClick={() => setMode("A")}>
                  <b>Director Script Mode</b>
                  <div className="hint" style={{ marginTop: 4 }}>
                    Paste your ready Khmer script. Sentences are segmented into scenes without rewriting.
                  </div>
                </div>
                <div className={`ct-card ${mode === "B" ? "on" : ""}`} onClick={() => setMode("B")}>
                  <b>AI Story Ideation</b>
                  <div className="hint" style={{ marginTop: 4 }}>
                    Input a brief topic. The Content Director drafts the script for your approval before production.
                  </div>
                </div>
              </div>
            </div>

            <div>
              <b>Target Social Platform</b>
              <div className="cards" style={{ gridTemplateColumns: "repeat(4, 1fr)", marginTop: 6 }}>
                {TARGET_PLATFORMS.map((p) => (
                  <div key={p.key} className={`ct-card ${platform === p.key ? "on" : ""}`} onClick={() => setPlatform(p.key)}>
                    <span style={{ fontSize: 18 }}>{p.icon}</span> <b>{p.label}</b>
                    <div className="hint" style={{ marginTop: 4 }}>{p.aspect}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Step 1: Content Format */}
        {step === 1 && (
          <>
            <p className="hint" style={{ marginBottom: 10 }}>
              Select a specialized short-form format. The format directs scene pacing, visual cues, and subtitle behavior.
            </p>
            <div className="cards" style={{ maxHeight: 380, overflowY: "auto" }}>
              {cts.map((c) => (
                <div key={c.key} className={`ct-card ${ct === c.key ? "on" : ""}`} onClick={() => setCt(c.key)}>
                  <span className="ct-emoji">{c.emoji}</span> <b>{c.label}</b>
                  <div className="hint" style={{ marginTop: 4 }}>{c.one_liner}</div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Step 2: Character & Actions */}
        {step === 2 && (
          <div>
            <b>Primary Reusable Character</b>
            <p className="hint" style={{ marginBottom: 8, marginTop: 4 }}>
              Deterministic visual consistency across all scenes. Pick an NPC to drive actions, reactions, and talking shots.
            </p>
            <select value={characterId} onChange={(e) => setCharacterId(e.target.value)} style={{ marginBottom: 16 }}>
              <option value="">— no character (motion graphics & illustrations) —</option>
              {chars.map((c) => (
                <option key={c.id} value={c.id}>{c.name} ({c.images.length} expressions)</option>
              ))}
            </select>

            <b>Default Visual Production Path</b>
            <p className="hint" style={{ marginBottom: 8, marginTop: 4 }}>
              Non-AI video is the dependable default. AI-generated video is an optional mode for cinematic scenes.
            </p>
            <div className="cards" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 6 }}>
              <div className={`ct-card ${visualSource === "character_action" ? "on" : ""}`} onClick={() => setVisualSource("character_action")}>
                <b>🎭 Character Actions (Default)</b>
                <div className="hint" style={{ marginTop: 4 }}>
                  Consistent reusable character with 21 context-aware actions, props, and audio sync.
                </div>
              </div>
              <div className={`ct-card ${visualSource === "illustration" ? "on" : ""}`} onClick={() => setVisualSource("illustration")}>
                <b>🖼 Ken Burns Illustration</b>
                <div className="hint" style={{ marginTop: 4 }}>
                  Static or generated high-res art with subtle motion, pan, and zoom.
                </div>
              </div>
              <div className={`ct-card ${visualSource === "meme" ? "on" : ""}`} onClick={() => setVisualSource("meme")}>
                <b>⚡ Meme & Reaction</b>
                <div className="hint" style={{ marginTop: 4 }}>
                  Comedic timing, visual punch-ins, freeze frames, and SFX hits.
                </div>
              </div>
              <div className={`ct-card ${visualSource === "generated_video" ? "on" : ""}`} onClick={() => setVisualSource("generated_video")}>
                <b>🎞 AI Video (Optional / Cinematic)</b>
                <div className="hint" style={{ marginTop: 4 }}>
                  Generative diffusion video for dramatic or emotional story scenes.
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Voice & Emotion */}
        {step === 3 && (
          <div>
            <b>Emotional Voice Profile</b>
            <p className="hint" style={{ marginBottom: 8, marginTop: 4 }}>
              Acoustic pitch, tempo, volume, and EQ shaping applied across synthesized Khmer speech.
            </p>
            <div className="cards" style={{ gridTemplateColumns: "repeat(5, 1fr)", marginBottom: 16 }}>
              {EMOTIONAL_STYLES.map((e) => (
                <div key={e.key} className={`ct-card ${emotionStyle === e.key ? "on" : ""}`} onClick={() => setEmotionStyle(e.key)}>
                  <b>{e.label}</b>
                  <div className="hint" style={{ marginTop: 2, fontSize: 11 }}>{e.desc}</div>
                </div>
              ))}
            </div>

            <b>TTS Voice Model / Profile</b>
            <select value={voiceId} onChange={(e) => setVoiceId(e.target.value)} style={{ marginTop: 6 }}>
              <option value="">House Khmer Voice (Local Sherpa MMS-TTS)</option>
              {voices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </div>
        )}

        {/* Step 4: Pacing & Subtitles */}
        {step === 4 && (
          <div>
            <b>Speech Pacing & Gaps</b>
            <p className="hint" style={{ marginBottom: 8 }}>
              Pace controls TTS speed and deterministic silence between lines (clamped 0.3–3.0s).
            </p>
            <div className="cards" style={{ gridTemplateColumns: "1fr 1fr 1fr", marginBottom: 12 }}>
              {PACES.map((p) => (
                <div key={p.key} className={`ct-card ${pace === p.key ? "on" : ""}`} onClick={() => {
                  setPace(p.key);
                  if (p.key === "slow") setLineGap(1.4);
                  if (p.key === "natural") setLineGap(1.15);
                  if (p.key === "brisk") setLineGap(0.95);
                }}>
                  <b>{p.label}</b><div className="hint">{p.desc}</div>
                </div>
              ))}
            </div>

            <div className="spread" style={{ marginBottom: 10, marginTop: 14 }}>
              <b>Burn HarfBuzz-shaped Khmer captions into final MP4?</b>
              <input type="checkbox" checked={burn} onChange={(e) => setBurn(e.target.checked)} style={{ width: "auto" }} />
            </div>
            <p className="hint" style={{ marginBottom: 8 }}>Select subtitle styling preset:</p>
            <div className="gallery">
              {previews.sub.map((s) => (
                <div key={s.key} className={`g-item ${subStyle === s.key ? "on" : ""}`} onClick={() => { setSubStyle(s.key); setBurn(true); }}>
                  {s.url ? <video src={s.url} muted loop autoPlay playsInline /> : <div className="hint" style={{ padding: 20 }}>preview</div>}
                  <div className="g-cap"><b>{s.label}</b></div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Step 5: Script & Content Director */}
        {step === 5 && (
          <div>
            {mode === "A" ? (
              <label className="fld">
                <span>Finished Khmer script (one sentence per line — line = scene)</span>
                <div className="row" style={{ gap: 6, marginBottom: 4 }}>
                  <button type="button" className="btn tiny" onClick={markSilent}
                    title="wrap the selected text in [[silent: …]] — it is shown in captions but never spoken">
                    ✕ mark selection as not spoken
                  </button>
                  <button type="button" className="btn tiny primary" onClick={runContentDirector} disabled={analyzing}>
                    {analyzing ? "Analyzing…" : "🤖 Ask Content Director"}
                  </button>
                </div>
                <textarea ref={scriptRef} lang="km" spellCheck={false} rows={6} value={script} onChange={(e) => setScript(e.target.value)}
                  placeholder={"ជីវិតមនុស្ស មិនមែនជាការប្រណាំងទេ។\nវាគឺជាដំណើរ ដែលយើងត្រូវរៀនដើរម្ដងមួយជំហាន។"} />
                <SilentPreview text={script} />
              </label>
            ) : (
              <label className="fld">
                <span>Topic premise (Khmer or English)</span>
                <div className="row" style={{ gap: 6 }}>
                  <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="ការពិតមិនគួរឲ្យជឿអំពីខួរក្បាលមនុស្ស" />
                  <button type="button" className="btn primary" onClick={runContentDirector} disabled={analyzing}>
                    {analyzing ? "Analyzing…" : "🤖 Ask Content Director"}
                  </button>
                </div>
              </label>
            )}

            {/* Content Director Insights Card */}
            {analysis && (
              <div style={{ background: "#1c2128", border: "1px solid #30363d", borderRadius: 6, padding: 12, marginTop: 10 }}>
                <div className="spread">
                  <b>🤖 Content Director Intelligence</b>
                  <Badge kind={analysis.approved ? "ok" : "warn"}>
                    {analysis.approved ? `Hook Score: ${analysis.retention_score}/100` : "Needs Polish"}
                  </Badge>
                </div>
                <div style={{ fontSize: 12, marginTop: 6, color: "var(--tx2)" }}>
                  <div><b>Recommended Format:</b> {analysis.content_type_label} ({analysis.recommended_content_type})</div>
                  <div><b>Suggested 1-3s Hook:</b> <span lang="km" style={{ color: "var(--tx)" }}>{analysis.hook_suggestion}</span></div>
                  <div><b>Action & Prop:</b> {analysis.recommended_character_action} + {analysis.recommended_prop}</div>
                  <div><b>Voice Emotion:</b> {analysis.recommended_emotion}</div>
                  {analysis.use_meme && <div><b>Meme Moment:</b> Yes ({analysis.meme_type}) — {analysis.meme_reasoning}</div>}
                  {analysis.critique.length > 0 && (
                    <div style={{ color: "var(--yellow)", marginTop: 4 }}>
                      ⚠️ {analysis.critique.join(" ")}
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="row" style={{ marginTop: 10 }}>
              <label className="fld grow">
                <span>Target duration (seconds)</span>
                <input type="number" min={10} max={180} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
              </label>
              <label className="fld grow">
                <span>Style notes</span>
                <input value={styleNotes} onChange={(e) => setStyleNotes(e.target.value)} placeholder="clean, punchy, high retention" />
              </label>
            </div>
          </div>
        )}
      </div>

      <div className="spread" style={{ marginTop: 14 }}>
        <div className="hint">Step {step + 1}/{STEPS.length}</div>
        <div className="row">
          {step > 0 && <button className="btn" onClick={back}>← back</button>}
          <button className="btn primary" disabled={!canNext || busy} onClick={next}>
            {busy ? <span className="spin" /> : step === STEPS.length - 1 ? "Create Project & Launch Studio" : "Continue →"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function SilentPreview({ text }: { text: string }) {
  const parts = text.split(/(\[\[silent:[^\]]*\]\])/g);
  return (
    <div className="silent-preview" aria-label="script preview: struck-through text is not spoken">
      <span className="hint">preview — </span>
      {parts.map((p, i) => {
        const m = /^\[\[silent:\s*([^\]]*)\]\]$/.exec(p);
        return m
          ? <span key={i} className="silent-mark" title="not spoken — displayed only">{m[1]}</span>
          : <span key={i}>{p}</span>;
      })}
    </div>
  );
}
