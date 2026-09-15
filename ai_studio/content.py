"""Content types — the creative framing of a project.

Every project used to be implicitly "explain something calmly and positively".
Now the Director picks a content type (or lets Auto mode choose one) and the
whole pipeline — script prompt, scene breakdown, visual tags, deterministic
fallbacks — is shaped accordingly.

This is a *definition* table, not opinions scattered through the stages: the
Controller prompt, the deterministic breakdown, the QA reviewer, the video/SFX
stage and the frontend all read the same ``CONTENT_TYPES`` dict, so adding a
new type later is one entry + (optionally) a deterministic rule, not a hunt
through six modules.

Research basis: these are proven short-form educational/creator formats
(explainer, hypothetical "what if", comparison, decision helper, word-nuance,
myth-vs-fact correction, quick tip).
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContentTypeSpec:
    key: str
    label: str
    one_liner: str                      # what it is (frontend card description)
    instruction: str                    # injected into Controller / Scriptwriter prompts
    scene_rule: str                     # deterministic/LLM structural rule for the breakdown
    default_visual_source: str = "generated_video"   # generated_video | illustration | character_demo
    default_render_mode: str = "broll"               # broll | talking_head
    mood_bias: str = ""                 # preferred mood slug ('' = follow the words)
    target_duration_factor: float = 1.0              # quick_tip → shorter by default
    tags: dict = field(default_factory=dict)         # extra meta fields for scenes/scripts
    emoji: str = "🎬"


CONTENT_TYPES = {
    "explainer": ContentTypeSpec(
        key="explainer",
        label="Explainer",
        one_liner="One concept, explained simply and warmly — today's calm house style.",
        instruction=(
            "CONTENT TYPE: EXPLAINER. Explain ONE concept simply and warmly. One idea per "
            "sentence, concrete images, no jargon. The existing calm/positive house voice "
            "applies unchanged."
        ),
        scene_rule="one idea per scene; each scene introduces exactly one sub-point",
        emoji="🧠",
    ),
    "what_if": ContentTypeSpec(
        key="what_if",
        label="What If",
        one_liner="A hypothetical scenario explored — imaginative, speculative.",
        instruction=(
            "CONTENT TYPE: WHAT IF. Open the script with a hypothetical hook ('What if…'). "
            "Explore ONE plausible scenario with concrete, sensory consequences. Stay "
            "imaginative and speculative, but keep the tone warm and grounded — no fear-mongering. "
            "Visuals may lean more imaginative/speculative than the calm-nature default "
            "(e.g. dreamlike light, unreal palette, gentle surrealism)."
        ),
        scene_rule="scene 1 states the hypothetical; later scenes each explore one consequence",
        mood_bias="night-quiet",
        tags={"fantasy": True},
        emoji="✨",
    ),
    "compare": ContentTypeSpec(
        key="compare",
        label="Compare",
        one_liner="Two things set side by side — A's trait, then B's equivalent.",
        instruction=(
            "CONTENT TYPE: COMPARE. Structure the script in TWO clearly parallel halves: "
            "the first half introduces side A's traits, the second repeats the SAME structure "
            "for side B (A's trait → B's equivalent trait, over and over). Tag every scene "
            "with which side it belongs to (`A` or `B`) and end with one balanced summary "
            "scene. The visual treatment should contrast the two sides (split framing, "
            "alternating colour treatment) so the comparison reads visually, not just verbally."
        ),
        scene_rule=("split scenes into side A then side B (half the scenes each), then one "
                    "balanced summary scene; tag each scene meta.side = 'A' | 'B' | 'summary'"),
        default_visual_source="illustration",
        tags={"paired": True},
        emoji="⚖️",
    ),
    "choose": ContentTypeSpec(
        key="choose",
        label="Choose (decision helper)",
        one_liner="Helps the viewer decide between options — trade-offs plus a clear takeaway.",
        instruction=(
            "CONTENT TYPE: CHOOSE / DECISION HELPER. Present the options with their real "
            "trade-offs (what each costs and gives), then END with a clear takeaway: either "
            "a recommendation, or an honest 'it depends on X' framing. Not neutral description — "
            "the viewer should leave able to decide."
        ),
        scene_rule=("one scene per option (tag meta.side = option id), then a final takeaway "
                    "scene tagged meta.side = 'takeaway'"),
        default_visual_source="illustration",
        tags={"decide": True},
        emoji="🧭",
    ),
    "word_nuance": ContentTypeSpec(
        key="word_nuance",
        label="Word nuance",
        one_liner="Same word, two meanings — or two words for a similar feeling, contrasted.",
        instruction=(
            "CONTENT TYPE: WORD NUANCE. Explicitly contrast the two meanings/words with a "
            "CONCRETE example sentence for EACH, so the distinction is heard, not just stated "
            "abstractly. Label the two halves (meaning-1 / meaning-2) and end with a sentence "
            "that uses both correctly."
        ),
        scene_rule=("scene for meaning 1 (tag meta.side='meaning-1'), scene for meaning 2 "
                    "(meta.side='meaning-2'), optional contrast scene (meta.side='contrast')"),
        default_visual_source="illustration",
        tags={"nuance": True},
        emoji="🔤",
    ),
    "myth_vs_fact": ContentTypeSpec(
        key="myth_vs_fact",
        label="Myth vs fact",
        one_liner="A common misconception, corrected — myth first, fact second.",
        instruction=(
            "CONTENT TYPE: MYTH VS FACT. State the myth plainly FIRST (label it the myth), "
            "then the fact, and briefly address WHY people believe the myth (it sounds "
            "reasonable / it used to be taught / it is repeated). Never mock the believer — "
            "the correction is warm and clarifying."
        ),
        scene_rule=("scene 1 tagged meta.side='myth', scene 2 meta.side='fact' with the "
                    "'why people believe it' inside the fact scene, optional 'why-it-matters' closing"),
        tags={"correct": True},
        emoji="✅",
    ),
    "quick_tip": ContentTypeSpec(
        key="quick_tip",
        label="Quick tip",
        one_liner="One fast, practical, actionable piece of advice — shorter by default.",
        instruction=(
            "CONTENT TYPE: QUICK TIP. ONE fast practical actionable tip. Imperative, "
            "action-oriented (tell the viewer what to DO), not descriptive. Keep it shorter "
            "than the usual run — target duration defaults lower. One tip, one scene, done."
        ),
        scene_rule="1-2 scenes; language imperative; no scene may exceed ~8s",
        target_duration_factor=0.6,
        tags={"action": True},
        emoji="⚡",
    ),
    "meme_relatable": ContentTypeSpec(
        key="meme_relatable",
        label="Meme & Relatable",
        one_liner="Comedic relatable everyday reality — punchy reaction, comedic timing.",
        instruction=(
            "CONTENT TYPE: MEME & RELATABLE. Highlight a common relatable frustration, habit, "
            "or irony. Hook the audience in the first 2 seconds with an exaggerated situation. "
            "Use expressive character reactions (laughing, shocked, facepalm) and deliver "
            "a punchline payoff."
        ),
        scene_rule="scene 1 sets the relatable trap; scene 2-3 escalate; final scene punchline",
        default_visual_source="meme",
        mood_bias="excited",
        tags={"humor": True, "meme": True},
        emoji="😂",
    ),
    "pov": ContentTypeSpec(
        key="pov",
        label="POV (Point of view)",
        one_liner="Puts the viewer inside an immediate, high-stakes or funny scenario.",
        instruction=(
            "CONTENT TYPE: POV. 'POV: You are in situation X'. Immerse the viewer directly. "
            "Use second-person perspective ('អ្នក'). Immediate visual tension or intrigue in "
            "the first 2 seconds."
        ),
        scene_rule="scene 1 POV hook statement; scene 2 internal thought/reaction; scene 3 twist or resolution",
        default_visual_source="character_demo",
        mood_bias="surprised",
        tags={"immersive": True},
        emoji="👀",
    ),
    "storytime": ContentTypeSpec(
        key="storytime",
        label="Storytime",
        one_liner="Compelling personal or historical story with dramatic arc.",
        instruction=(
            "CONTENT TYPE: STORYTIME. Conversational, authentic storytelling. Start with "
            "the turning point or most bizarre detail first, then tell how you got there. "
            "Warm storytelling voice."
        ),
        scene_rule="scene 1 teaser climax hook; scene 2 context/rise; scene 3 resolution & lesson",
        default_visual_source="character_demo",
        mood_bias="thoughtful",
        tags={"narrative": True},
        emoji="📖",
    ),
    "quiz": ContentTypeSpec(
        key="quiz",
        label="Quiz / Trivia",
        one_liner="Interactive question with 3-second thinking pause and reveal.",
        instruction=(
            "CONTENT TYPE: QUIZ. Ask a sharp, intriguing question in scene 1. Challenge the viewer "
            "to guess in scene 2 with a thinking pause. Reveal the answer and the fascinating reason in scene 3."
        ),
        scene_rule="scene 1 question; scene 2 thinking pause; scene 3 answer & punchy explanation",
        default_visual_source="illustration",
        mood_bias="curious",
        tags={"interactive": True},
        emoji="❓",
    ),
    "listicle": ContentTypeSpec(
        key="listicle",
        label="Top 3 / Listicle",
        one_liner="Brisk countdown or checklist — fast paced, high retention.",
        instruction=(
            "CONTENT TYPE: LISTICLE. Top 3 items or rules. Fast, punchy pacing with numbered "
            "visual indicators. No fluff, straight to value."
        ),
        scene_rule="scene 1 hook; scenes 2-4 one item per scene with number; final scene CTA",
        default_visual_source="illustration",
        mood_bias="excited",
        tags={"countdown": True},
        emoji="📋",
    ),
    "reaction_explainer": ContentTypeSpec(
        key="reaction_explainer",
        label="Reaction + Breakdown",
        one_liner="Shocked or surprised reaction hook followed by clear breakdown.",
        instruction=(
            "CONTENT TYPE: REACTION + EXPLAINER. Start with a dramatic reaction to a shocking fact "
            "or event, then pivot into 'Here is what actually happened'. High energy transition."
        ),
        scene_rule="scene 1 dramatic reaction / meme punch-in; scene 2-3 objective breakdown",
        default_visual_source="meme",
        mood_bias="surprised",
        tags={"reaction": True},
        emoji="😲",
    ),
    "mini_story": ContentTypeSpec(
        key="mini_story",
        label="Mini Story",
        one_liner="Complete 3-act narrative compressed into 30–60 seconds.",
        instruction=(
            "CONTENT TYPE: MINI STORY. Classic 3-act story: Character faces a hurdle, tries and struggles, "
            "discovers a breakthrough. Meaningful takeaway."
        ),
        scene_rule="scene 1 character + problem; scene 2 struggle; scene 3 breakthrough & moral",
        default_visual_source="character_demo",
        mood_bias="determined",
        tags={"story": True},
        emoji="🎭",
    ),
    "problem_solution": ContentTypeSpec(
        key="problem_solution",
        label="Problem → Solution",
        one_liner="Identifies a common pain point immediately, delivers the fix.",
        instruction=(
            "CONTENT TYPE: PROBLEM TO SOLUTION. Call out an exact problem in the first 2 seconds. "
            "Validate why it's painful, then present the 1 actionable solution with zero fluff."
        ),
        scene_rule="scene 1 problem pain point; scene 2 failed common attempts; scene 3 the real solution",
        default_visual_source="illustration",
        mood_bias="serious",
        tags={"practical": True},
        emoji="💡",
    ),
    "unexpected_fact": ContentTypeSpec(
        key="unexpected_fact",
        label="Unexpected Fact",
        one_liner="Counter-intuitive curiosity that stops the scroll.",
        instruction=(
            "CONTENT TYPE: UNEXPECTED FACT. State a true fact that sounds completely fake or backwards. "
            "Immediately prove it with evidence. Leave the viewer feeling smarter."
        ),
        scene_rule="scene 1 shocking statement; scene 2 scientific/historical proof; scene 3 mind-blown takeaway",
        default_visual_source="illustration",
        mood_bias="curious",
        tags={"trivia": True},
        emoji="🤯",
    ),
    "challenge": ContentTypeSpec(
        key="challenge",
        label="Viewer Challenge",
        one_liner="Tests the viewer's memory, perception, or decision skills live.",
        instruction=(
            "CONTENT TYPE: CHALLENGE. Challenge the viewer to not blink, find the difference, "
            "or solve a puzzle in 5 seconds. High viewer engagement and comment drive."
        ),
        scene_rule="scene 1 challenge rule; scene 2 active challenge test; scene 3 result check & comment prompt",
        default_visual_source="illustration",
        mood_bias="excited",
        tags={"challenge": True},
        emoji="🏆",
    ),
    "emotional_sad": ContentTypeSpec(
        key="emotional_sad",
        label="Emotional / Sad Story",
        one_liner="Cinematic emotional reflection — where generative video & sad voiceover shine.",
        instruction=(
            "CONTENT TYPE: EMOTIONAL & SAD. Deep, evocative, heartfelt reflection on memory, "
            "loss, kindness, or nostalgia. Deliberate, slower pacing. Cinematic imagery and "
            "somber emotional voice. Memes are strictly prohibited."
        ),
        scene_rule="poetic, emotional scenes with room to breathe; cinematic atmosphere",
        default_visual_source="generated_video",
        default_render_mode="broll",
        mood_bias="sad",
        target_duration_factor=1.2,
        tags={"cinematic": True, "emotional": True},
        emoji="🌧️",
    ),
}

DEFAULT_CONTENT_TYPE = "explainer"
VALID_CONTENT_TYPES = tuple(CONTENT_TYPES)
EXPRESSION_SUGGESTIONS = [
    "neutral", "happy", "sad", "determined", "surprised", "calm", "curious",
    "proud", "thoughtful", "excited", "worried", "grateful",
]

# mood → nearest character expression label (the matching rule, documented for
# the API response and README). Simple string/synonym match, deliberately
# over-engineered-avoided: unknown moods fall back to "neutral".
MOOD_TO_EXPRESSION = {
    "calm-warm": "calm", "water-calm": "calm", "still-lake": "calm",
    "rain-soft": "calm", "flowers-still": "calm",
    "sunrise-warm": "happy", "birds-dawn": "happy", "kind-warm": "happy",
    "night-quiet": "neutral", "forest-mist": "neutral", "home-warm": "calm",
    "study-calm": "thoughtful", "path-walking": "determined",
    "effort-dawn": "determined", "sad": "sad", "sorrow": "sad",
    "surprised": "surprised", "curious": "curious", "thoughtful": "thoughtful",
    "happy": "happy", "determined": "determined", "neutral": "neutral",
}


def spec(key):
    return CONTENT_TYPES.get(key or DEFAULT_CONTENT_TYPE, CONTENT_TYPES[DEFAULT_CONTENT_TYPE])


def instruction_block(key):
    """The content-type instruction injected into agent prompts."""
    return spec(key).instruction


def valid(key):
    return (key or DEFAULT_CONTENT_TYPE) in CONTENT_TYPES


def normalize(key):
    return key if valid(key) else DEFAULT_CONTENT_TYPE


def expression_for_mood(mood_tag, labels=None):
    """Nearest available expression label for a scene's mood.

    Rule: synonym table first (sorrow → sad), then exact label match, then
    'calm' (the house mood), then 'neutral'. `labels` (the character's actual
    uploaded labels) constrains the answer when provided.
    """
    mood = str(mood_tag or "").strip().lower().replace("_", "-")
    labels = [str(l).strip().lower() for l in (labels or []) if str(l).strip()]
    # the mood itself is a candidate only when it already *is* a known
    # expression label/alias — unknown moods must not leak through as labels
    known_aliases = set(MOOD_TO_EXPRESSION) | set(EXPRESSION_SUGGESTIONS) | {"calm"}
    cands = ([MOOD_TO_EXPRESSION.get(mood, "")] if mood in MOOD_TO_EXPRESSION else []) \
        + ([mood] if mood in known_aliases else []) \
        + [MOOD_TO_EXPRESSION.get("calm-warm"), "neutral", "calm"]
    if labels:
        for c in cands:
            if c and c in labels:
                return c
        return labels[0]
    for c in cands:
        if c:
            return c
    return "neutral"


def content_type_payload():
    """API-visible catalog (frontend renders cards from this — not hardcoded)."""
    return [{
        "key": s.key, "label": s.label, "one_liner": s.one_liner, "emoji": s.emoji,
        "default_visual_source": s.default_visual_source,
        "default_render_mode": s.default_render_mode,
        "target_duration_factor": s.target_duration_factor,
    } for s in CONTENT_TYPES.values()]


# ------------------------------------------------------------- Content Director
class ContentDirector:
    """Intelligent content director layer for short-form video optimization.

    Evaluates ideas, hooks, pacing, meme opportunities, character action selection,
    and can reject low-retention or vague concepts.
    """

    @staticmethod
    def recommend_format(topic: str) -> str:
        """Analyze topic intent and select the optimal short-form content type."""
        t = str(topic or "").strip().lower()
        if not t:
            return "explainer"

        if any(w in t for w in ["meme", "funny", "relatable", "joke", "សើច", "កំប្លែង"]):
            return "meme_relatable"
        if any(w in t for w in ["sad", "cry", "tear", "loss", "grief", "យំ", "សោកសៅ", "ទុក្ខ"]):
            return "emotional_sad"
        if any(w in t for w in ["vs", "compare", "difference", "ខុសគ្នា", "ប្រៀបធៀប"]):
            return "compare"
        if any(w in t for w in ["myth", "fact", "true or false", "ការពិត", "ជំនឿ", "ខុស"]):
            return "myth_vs_fact"
        if any(w in t for w in ["choose", "which one", "pick", "ជម្រើស", "រើស"]):
            return "choose"
        if any(w in t for w in ["tip", "hack", "how to", "trick", "តិចនិក", "គន្លឹះ"]):
            return "quick_tip"
        if any(w in t for w in ["what if", "ចុះបើ", "ប្រសិនបើ"]):
            return "what_if"
        if any(w in t for w in ["pov", "perspective", "មើលឃើញ"]):
            return "pov"
        if any(w in t for w in ["story", "happened", "រឿង", "ដំណើររឿង"]):
            return "storytime"
        if any(w in t for w in ["quiz", "guess", "question", "ទាយ", "សំណួរ"]):
            return "quiz"
        if any(w in t for w in ["top", "top 3", "list", "កំពូល"]):
            return "listicle"
        if any(w in t for w in ["shocking", "fact", "secret", "មិនគួរឲ្យជឿ", "អាថ៌កំបាំង"]):
            return "unexpected_fact"
        if any(w in t for w in ["problem", "solve", "fix", "បញ្ហា", "ដំណោះស្រាយ"]):
            return "problem_solution"
        if any(w in t for w in ["meaning", "nuance", "word", "ពាក្យ", "ន័យ"]):
            return "word_nuance"

        return "explainer"

    @staticmethod
    def analyze_topic(topic: str, script: str = None) -> dict:
        """Deep analysis of topic viability for TikTok, FB Reels, and IG Reels."""
        t = str(topic or "").strip()
        word_count = len(t.split())
        critique = []
        approved = True

        # Hook & Length Gate
        if len(t) < 4:
            approved = False
            critique.append("Topic is too brief. Provide a specific scenario or premise.")
        elif word_count == 1 and not script:
            critique.append("Single-word topic lacks an immediate hook. Consider framing as a question or comparison.")

        # Determine best format
        rec_format = ContentDirector.recommend_format(t)
        spec_fmt = spec(rec_format)

        # Emotion & Voice matching
        if rec_format in ("emotional_sad", "storytime"):
            rec_emotion = "sad" if rec_format == "emotional_sad" else "storytelling"
        elif rec_format in ("meme_relatable", "challenge", "listicle"):
            rec_emotion = "excited"
        elif rec_format in ("myth_vs_fact", "unexpected_fact", "quiz"):
            rec_emotion = "surprised"
        elif rec_format == "problem_solution":
            rec_emotion = "serious"
        else:
            rec_emotion = "calm"

        # Character action recommendation
        from . import character_actions as ca
        rec_action, rec_prop = ca.action_for_scene(spec_fmt.mood_bias or rec_emotion, t, content_type=rec_format)

        # Meme recommendation
        from . import meme_engine as me
        use_meme, meme_type, _sfx, meme_reason = me.decide_meme_usage(rec_format, t, rec_emotion, 0, 3)

        # Visual source recommendation
        if rec_format == "emotional_sad":
            rec_visual_source = "generated_video"
        elif use_meme:
            rec_visual_source = "meme"
        elif rec_action:
            rec_visual_source = "character_action"
        else:
            rec_visual_source = "illustration"

        # Viral hook suggestion
        if rec_format == "explainer":
            hook_suggestion = f"តើអ្នកធ្លាប់ឆ្ងល់ទេថា ហេតុអ្វីបានជា {t}?"
        elif rec_format == "myth_vs_fact":
            hook_suggestion = f"មនុស្សជាច្រើនគិតថា {t} តែការពិតមិនដូច្នោះទេ!"
        elif rec_format == "meme_relatable":
            hook_suggestion = f"ពេលដែលអ្នកព្យាយាម {t} ហើយលទ្ធផលគឺ..."
        elif rec_format == "what_if":
            hook_suggestion = f"ចុះបើពិភពលោកគ្មាន {t} តើនឹងមានរឿងអ្វីកើតឡើង?"
        elif rec_format == "unexpected_fact":
            hook_suggestion = f"ការពិតមិនគួរឲ្យជឿមួយអំពី {t} ដែលអ្នកមិនដែលដឹង!"
        else:
            hook_suggestion = f"អាថ៌កំបាំងនៃ {t} ក្នុងរយៈពេល ៣០ វិនាទី!"

        return {
            "approved": approved,
            "topic": t,
            "recommended_content_type": rec_format,
            "content_type_label": spec_fmt.label,
            "recommended_emotion": rec_emotion,
            "recommended_character_action": rec_action,
            "recommended_prop": rec_prop,
            "recommended_visual_source": rec_visual_source,
            "use_meme": use_meme,
            "meme_type": meme_type,
            "meme_reasoning": meme_reason,
            "hook_suggestion": hook_suggestion,
            "retention_score": (88 if rec_format in ("meme_relatable", "unexpected_fact", "myth_vs_fact") else 82),
            "critique": critique,
        }
