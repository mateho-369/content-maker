"""Background plates — the sixth column of the Manual board.

One vocabulary for three audiences: the UI picker, the save endpoint's validator,
and the renderers. A background is *not* a decoration flag that the pipeline
ignores — ``resolve()`` turns the stored spec into pixels and every visual source
in Stage 4 paints its subject on top of it:

  previz / generated_video  → the whole environment plate (sky, hills and water
                             are replaced; particles, mist and the light source
                             are kept and re-tinted)
  character_action / _demo  → the studio or plate behind the mascot, with a floor
                             shadow when the plate is a studio sweep
  meme                      → the colour/rays plate under the headline
  illustration still        → the fill behind the matted still (and the letterbox
                             if the still does not cover the frame)
  ComfyUI video             → a prompt clause, not a composite: an AI clip cannot
                             be re-lit after the fact, so the request states the
                             backdrop and the notes say so

Storage: the project setting ``settings["background"]`` is the global choice and
``scene.meta["background"]`` is the per-scene override (empty/absent = follow the
global one). Both are flat values validated by :func:`validate`, and — like every
other scene meta key — they survive a run untouched.

Shapes accepted anywhere a background is read or written::

    "white_studio"                                  # shorthand string
    {"type": "gradient", "a": "#0b1d3a", "b": "#38bdf8"}
    {"type": "image", "path": "backgrounds/plate.png"}   # under the data root
    {"type": "ai_prompt", "prompt": "golden hour rice paddy"}
    {"type": "template", "template": "city"}
"""
import hashlib
import math
import os
import re

import numpy as np

# --------------------------------------------------------------------------- specs
KINDS = ("white_studio", "black_studio", "gradient", "image", "ai_prompt", "template")

TEMPLATES = {
    "studio":   {"label": "Studio sweep", "emoji": "⬜", "one_liner": "Soft cyc, neutral key light"},
    "nature":   {"label": "Nature", "emoji": "🌿", "one_liner": "Misted hills, warm horizon"},
    "city":     {"label": "City", "emoji": "🌃", "one_liner": "Skyline silhouette, sodium haze"},
    "abstract": {"label": "Abstract", "emoji": "🌀", "one_liner": "Slow mesh gradient, no scenery"},
    "paper":    {"label": "Paper", "emoji": "📄", "one_liner": "Warm paper with a faint fibre grain"},
    "neon":     {"label": "Neon", "emoji": "💠", "one_liner": "Dark floor, cyan/magenta rim glow"},
}

# key → what the UI needs to draw a row of the picker. ``fields`` are the extra
# inputs the type reveals (colour pickers, prompt box, upload, template grid).
BACKGROUNDS = {
    "white_studio": {"key": "white_studio", "label": "White Studio", "emoji": "⬜",
                     "one_liner": "Clean, professional — the default for explainers",
                     "fields": [], "default": {"type": "white_studio"}},
    "black_studio": {"key": "black_studio", "label": "Black Studio", "emoji": "⬛",
                     "one_liner": "Cinematic, high contrast, best with light captions",
                     "fields": [], "default": {"type": "black_studio"}},
    "gradient": {"key": "gradient", "label": "Gradient", "emoji": "🎨",
                 "one_liner": "Two colours, A → B, diagonal",
                 "fields": [{"name": "a", "label": "Colour A", "kind": "color", "default": "#0b1d3a"},
                            {"name": "b", "label": "Colour B", "kind": "color", "default": "#38bdf8"}],
                 "default": {"type": "gradient", "a": "#0b1d3a", "b": "#38bdf8"}},
    "image": {"key": "image", "label": "Custom Image", "emoji": "🖼️",
              "one_liner": "Your own plate — uploaded, cover-cropped per frame",
              "fields": [{"name": "path", "label": "Image", "kind": "upload",
                          "accept": ".png,.jpg,.jpeg,.webp"}],
              "default": {"type": "image", "path": ""}},
    "ai_prompt": {"key": "ai_prompt", "label": "AI Generate", "emoji": "🤖",
                  "one_liner": "One plate per prompt, made by the image engine and reused",
                  "fields": [{"name": "prompt", "label": "Prompt", "kind": "text", "default": ""},
                             {"name": "seed", "label": "Seed", "kind": "number", "default": 0}],
                  "default": {"type": "ai_prompt", "prompt": ""}},
    "template": {"key": "template", "label": "Templates", "emoji": "📦",
                 "one_liner": "Six looks rendered locally — no model needed",
                 "fields": [{"name": "template", "label": "Template", "kind": "choice",
                             "options": [{"key": k, "label": v["label"], "emoji": v["emoji"],
                                          "one_liner": v["one_liner"]} for k, v in TEMPLATES.items()],
                             "default": "studio"}],
                 "default": {"type": "template", "template": "studio"}},
}
DEFAULT_BACKGROUND = {"type": "white_studio"}

# --------------------------------------------------------------------------- colours
_HEX = re.compile(r"^#?([0-9a-f]{3}|[0-9a-f]{6})$", re.I)

# plate colours: (top, bottom) in 0-255 RGB, plus how much the light drifts
_STUDIO = {"white": ((247, 247, 245), (219, 220, 221)), "black": ((20, 21, 25), (6, 6, 9))}
_GRADIENT_DEFAULTS = ((11, 29, 58), (56, 189, 248))
_NATURE = {"sky": ((168, 196, 214), (226, 214, 186)),
           "hills": ((92, 118, 96), (52, 74, 62), (28, 44, 40)), "light": (255, 236, 200)}
_CITY = {"sky": ((24, 28, 46), (72, 58, 66)), "towers": ((16, 18, 30), (10, 11, 20)),
         "light": (255, 176, 112)}
_ABSTRACT = ((28, 32, 66), (112, 76, 158), (36, 146, 176))
_PAPER = {"base": ((246, 240, 228), (226, 216, 198)), "grain": 0.02}
_NEON = {"base": ((12, 14, 22), (4, 4, 8)), "a": (56, 220, 255), "b": (255, 84, 200)}

# how many keyframes one plate is baked at before it loops; 1 = a static plate
# that only drifts (cheap), 4 = enough steps to fake twinkle/parallax
PHASES = {"studio": 1, "flat": 1, "gradient": 1, "plate": 1, "missing": 1,
          "template": 1, "ai": 1}
PHASES_BY_TEMPLATE = {"city": 4, "neon": 4, "abstract": 4, "nature": 4, "paper": 1, "studio": 1}
CYCLE_SEC = 8.0          # the plate animation loop
PAD = 0.045              # overscan so the per-frame drift never shows an edge


def _hex(v, fallback):
    """`#rgb`/`rrggbb` → (r,g,b) float 0-255, or ``fallback`` when unparseable."""
    s = str(v or "").strip()
    m = _HEX.match(s)
    if not m:
        return tuple(float(c) for c in fallback)
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(float(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def normalize(raw):
    """Any stored/typed value → a clean dict, or ``{}`` for "no choice made".

    Accepts the shorthand string (``"black_studio"``), a dict, and the picker's
    ``{"type": "template", "template": "city"}`` form. Unknown types are dropped
    rather than guessed, because a wrong plate in the render is worse than the
    project default.
    """
    if not raw:
        return {}
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        if s in BACKGROUNDS:
            return {"type": s}
        if ":" in s:                              # "template:city" from a CLI/older row
            k, _, v = s.partition(":")
            if k == "template" and v in TEMPLATES:
                return {"type": "template", "template": v}
        return {"type": s}                          # stays invalid → validate() reports it
    if not isinstance(raw, dict):
        return {}
    out = {k: v for k, v in raw.items() if v not in (None, "", [])}
    t = str(out.get("type") or out.get("kind") or "").strip().lower().replace("-", "_")
    if not t:
        # the picker sends {"a": "#..", "b": "#.."} without a type when the user
        # only touched the colour inputs — two colours *are* a gradient
        if out.get("a") or out.get("b"):
            t = "gradient"
        elif out.get("path"):
            t = "image"
        elif out.get("prompt"):
            t = "ai_prompt"
        elif out.get("template"):
            t = "template"
    if not t:
        return {}
    out["type"] = t
    return out


def validate(raw):
    """(ok, background_dict_or_error_string). The API's gate for 400 responses."""
    b = normalize(raw)
    if not b:
        return True, {}
    t = b["type"]
    if t not in KINDS:
        return False, (f"background type '{t}' does not exist — pick one of "
                       f"{', '.join(KINDS)}, or clear the cell to follow the project's background")
    if t == "template":
        name = str(b.get("template") or "studio")
        if name not in TEMPLATES:
            return False, (f"unknown background template '{name}' — available: "
                           f"{', '.join(TEMPLATES)}")
        b["template"] = name
    if t == "gradient":
        b["a"] = _to_hex(_hex(b.get("a"), _GRADIENT_DEFAULTS[0]))
        b["b"] = _to_hex(_hex(b.get("b"), _GRADIENT_DEFAULTS[1]))
    if t == "image" and not str(b.get("path") or "").strip():
        return False, ("background type 'image' needs an image — upload one in the "
                       "Background selector (🖼️ Custom Image → Upload)")
    if t == "ai_prompt" and not str(b.get("prompt") or "").strip():
        return False, ("background type 'ai_prompt' needs a prompt — describe the "
                       "backdrop in the Background selector (🤖 AI Generate)")
    return True, b


def _to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*[max(0, min(255, int(round(c)))) for c in rgb])


def key_of(b):
    """Stable id for a resolved choice — used for cache paths and QA messages."""
    b = normalize(b) or {}
    if not b:
        return ""
    if b["type"] == "template":
        return f"template:{b.get('template') or 'studio'}"
    if b["type"] == "gradient":
        return f"gradient:{b.get('a', '')}-{b.get('b', '')}"
    if b["type"] == "ai_prompt":
        stem = "ai_prompt:" + hashlib.sha1(str(b.get("prompt") or "").encode()).hexdigest()[:10]
        # a different seed is a different plate, so it must be a different cache key —
        # otherwise "re-roll with seed 7" quietly returns the file seed 1 produced.
        # Seed 0 keeps the old key so existing plates still resolve.
        sd = int(b.get("seed") or 0)
        return f"{stem}-s{sd}" if sd else stem
    if b["type"] == "image":
        return "image:" + os.path.basename(str(b.get("path") or ""))
    return b["type"]


def label(b):
    """Short human label for stage notes, QA reports and the run log."""
    b = normalize(b) or {}
    if not b:
        return "auto (scene palette)"
    t = b["type"]
    if t == "template":
        name = b.get("template") or "studio"
        return f"template · {TEMPLATES.get(name, {}).get('label', name)}"
    if t == "gradient":
        return f"gradient · {b.get('a', '?')} → {b.get('b', '?')}"
    if t == "image":
        return f"image · {os.path.basename(str(b.get('path') or '')) or 'missing'}"
    if t == "ai_prompt":
        return f"AI plate · {str(b.get('prompt') or '')[:40] or 'unset'}"
    return BACKGROUNDS.get(t, {}).get("label", t)


def luma(raw):
    """0-255 mean luminance of the plate's middle band (QA + the picker warning)."""
    res = resolve(raw, width=8, height=8)
    if not res or res.get("kind") == "missing":
        return 128.0
    top, bot = res.get("top"), res.get("bottom")
    if not top or not bot:
        return 128.0
    mid = [(a + b) / 2.0 for a, b in zip(top, bot)]
    return 0.2126 * mid[0] + 0.7152 * mid[1] + 0.0722 * mid[2]


def contrast_note(b):
    """Advice for the caption colour, or "" when the plate needs none.

    A white plate with a white caption is unreadable, so the picker warns before
    the run using the same luminance rule the QA gate applies afterwards.
    """
    lum = luma(b)
    if lum > 168:
        return "very light plate — use a dark caption colour or a strong outline"
    if lum < 40:
        return "very dark plate — white captions read best here"
    return ""


# ---------------------------------------------------------------------- resolution
def resolve(raw, *, width=720, height=1280, data_root="", seed=0, project_dir=""):
    """Stored spec → a paintable plate description, or ``None`` for "no choice".

    ``image``/``ai_prompt`` plates are files: an absolute ``path`` is kept, a
    relative one is taken from ``data_root`` (uploads) or ``project_dir`` (AI
    plates). A missing file yields ``kind="missing"`` so the caller can say *why*
    instead of silently rendering the wrong backdrop.
    """
    b = normalize(raw)
    if not b:
        return None
    t, w, h = b["type"], max(2, int(width)), max(2, int(height))
    # an explicit call-site seed wins, then the one the Director stored on the
    # background (the picker's 🎲 field) — `background_for` used to pass seed=0,
    # which silently discarded whatever seed the project had chosen
    out = {"type": t, "key": key_of(b), "label": label(b), "w": w, "h": h,
           "seed": int(seed or 0) or int(b.get("seed") or 0)}
    if t == "white_studio":
        out.update({"kind": "studio", "variant": "white", "top": _STUDIO["white"][0],
                    "bottom": _STUDIO["white"][1]})
    elif t == "black_studio":
        out.update({"kind": "studio", "variant": "black", "top": _STUDIO["black"][0],
                    "bottom": _STUDIO["black"][1]})
    elif t == "gradient":
        out.update({"kind": "gradient", "top": _hex(b.get("a"), _GRADIENT_DEFAULTS[0]),
                    "bottom": _hex(b.get("b"), _GRADIENT_DEFAULTS[1])})
    elif t == "image":
        p = str(b.get("path") or "")
        ap = p if os.path.isabs(p) else (os.path.join(data_root, p) if data_root else p)
        if not os.path.exists(ap) and project_dir:
            alt = os.path.join(project_dir, os.path.basename(p))
            ap = alt if os.path.exists(alt) else ap
        out.update({"kind": "missing" if not os.path.exists(ap) else "plate", "path": ap})
    elif t == "ai_prompt":
        stem = out["key"].split(":")[-1]
        cand = os.path.join(project_dir or "", "backgrounds", f"{stem}.png") if project_dir else ""
        cached = cand if cand and os.path.exists(cand) else ""
        out.update({"kind": "plate" if cached else "ai", "path": cached,
                    "prompt": str(b.get("prompt") or "").strip(), "target": cand})
    elif t == "template":
        name = b.get("template") or "studio"
        if name == "studio":
            out.update({"kind": "studio", "variant": "white", "top": _STUDIO["white"][0],
                        "bottom": _STUDIO["white"][1], "template": "studio"})
        else:
            out.update({"kind": "template", "template": name})
    else:
        out.update({"kind": "flat", "top": _GRADIENT_DEFAULTS[0], "bottom": _GRADIENT_DEFAULTS[1]})
    out["phases"] = PHASES_BY_TEMPLATE.get(out.get("template"), PHASES.get(out["kind"], 1))
    return out


# ------------------------------------------------------------------------ plates
# Base plates are baked once per (background, size) and each frame only crops
# (and, for animated plates, cross-fades) them — see the comment in paint().
_BAKED = {}
_BAKED_BYTES = [0]
_BAKED_LIMIT = 220 << 20


def _bake_key(resolved, phase):
    return (resolved.get("key"), resolved.get("kind"), int(resolved["w"]), int(resolved["h"]),
            int(resolved.get("seed") or 0), int(phase), resolved.get("path") or "")


def _remember(key, arr):
    nbytes = int(arr.nbytes)
    while _BAKED_BYTES[0] + nbytes > _BAKED_LIMIT and _BAKED:
        _BAKED.pop(next(iter(_BAKED)))
        _BAKED_BYTES[0] = sum(int(a.nbytes) for a in _BAKED.values())
    _BAKED[key] = arr
    _BAKED_BYTES[0] += nbytes


def paint(resolved, t=0.0, size=None):
    """The plate for one frame as float32 RGB ``(h, w, 3)`` in 0-255, or ``None``.

    Per-frame work is one or two array adds plus a slice — the expensive part
    (drawing the cyclorama, the skyline, the grain) is baked once per background
    and size in :func:`_bake`. Baking at ~4.5% overscan lets the frame drift a
    few pixels for life without ever showing an edge.

    ``size=(w, h)`` lets a renderer ask for the plate at *its* dimensions (previz
    renders 10% oversized, so it needs the plate oversized too); the bake cache is
    keyed by size, so this costs one bake per background per size, not per frame.
    """
    import numpy as np

    if not resolved or resolved.get("kind") in ("missing", "ai"):
        return None
    if size:
        rw, rh = int(size[0]), int(size[1])
        if (rw, rh) != (int(resolved["w"]), int(resolved["h"])):
            resolved = dict(resolved, w=rw, h=rh)
    w, h = int(resolved["w"]), int(resolved["h"])
    n = max(1, int(resolved.get("phases") or 1))
    u = (float(t or 0.0) / CYCLE_SEC) % 1.0
    i = int(u * n) % n
    f = (u * n) - int(u * n) if n > 1 else 0.0
    a = _bake(resolved, i)
    img = a
    if f > 0.001:
        b = _bake(resolved, (i + 1) % n)
        img = a + (b - a) * np.float32(f)
    # slow parallax drift of the overscan window (no resample, so it is free)
    pw, ph = img.shape[1], img.shape[0]
    dx = int(round((pw - w) * (0.5 + 0.5 * math.sin(u * 2 * math.pi))))
    dy = int(round((ph - h) * (0.5 + 0.35 * math.sin(u * 2 * math.pi * 0.7))))
    x0 = max(0, min(pw - w, dx))
    y0 = max(0, min(ph - h, dy))
    return np.ascontiguousarray(img[y0:y0 + h, x0:x0 + w, :])


def _bake(resolved, phase=0):
    """The overscanned plate for one phase (baked + cached)."""
    import numpy as np

    key = _bake_key(resolved, phase)
    hit = _BAKED.get(key)
    if hit is not None:
        return hit
    w, h = int(resolved["w"]), int(resolved["h"])
    pad = max(2, int(round(max(w, h) * PAD)))
    W, H = w + 2 * pad, h + 2 * pad
    ph = (phase / max(1, int(resolved.get("phases") or 1))) * 2.0 * math.pi
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    k = resolved["kind"]
    if k == "plate":
        img = _bake_image(resolved, W, H)
    elif k == "studio":
        img = _bake_studio(resolved, xx, yy, W, H, ph)
    elif k in ("gradient", "flat"):
        img = _bake_gradient(resolved, xx, yy, W, H, ph)
    elif k == "template":
        img = _bake_template(resolved, xx, yy, W, H, ph)
    else:
        img = np.zeros((H, W, 3), dtype=np.float32)
    img = np.clip(img, 0, 255).astype(np.float32)
    _remember(key, img)
    return img


def _bake_image(resolved, W, H):
    """Cover-crop an uploaded/AI plate to the overscanned size, once per run."""
    from PIL import Image

    cache = getattr(_bake_image, "_cache", {})
    key = (resolved["path"], W, H)
    if key in cache:
        return cache[key]
    with Image.open(resolved["path"]) as im:
        im = im.convert("RGB")
        s = max(W / max(1, im.width), H / max(1, im.height))
        im = im.resize((max(W, int(round(im.width * s))), max(H, int(round(im.height * s)))),
                       Image.BILINEAR)
        x0, y0 = (im.width - W) // 2, (im.height - H) // 2
        arr = np.asarray(im.crop((x0, y0, x0 + W, y0 + H)), dtype=np.float32)
    if len(cache) > 6:
        cache.clear()
    cache[key] = arr
    _bake_image._cache = cache
    return arr


def _bake_studio(resolved, xx, yy, W, H, ph):
    """Cyclorama: floor line, wide soft key from upper-left, edge falloff.

    The subject is drawn on top of this by the caller, which is why the light is
    asymmetric — a centred key flattens the mascot against a flat wall.
    """
    import numpy as np

    dark = resolved.get("variant") == "black"
    top = np.array((_STUDIO["black"] if dark else _STUDIO["white"])[0], dtype=np.float32)
    bot = np.array((_STUDIO["black"] if dark else _STUDIO["white"])[1], dtype=np.float32)
    g = np.clip(yy / max(1.0, H - 1.0), 0, 1) ** 1.35
    img = top[None, None, :] * (1 - g[..., None]) + bot[None, None, :] * g[..., None]
    floor_y = H * (0.78 + 0.006 * math.sin(ph))
    band = np.exp(-((yy - floor_y) ** 2) / (2 * (H * 0.055) ** 2))
    img -= band[..., None] * (10.0 if dark else 14.0)
    lx, ly = W * (0.34 + 0.02 * math.sin(ph)), H * 0.26
    r = np.sqrt(((xx - lx) / (W * 0.8)) ** 2 + ((yy - ly) / (H * 0.75)) ** 2)
    img += (np.clip(1.0 - r, 0, 1) ** 2.2)[..., None] * (20.0 if dark else 46.0)
    vig = np.clip(1.0 - (((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.66)) ** 2), 0, 1)
    return img * (0.80 + 0.20 * vig)[..., None]


def _bake_gradient(resolved, xx, yy, W, H, ph):
    """Two colours, blended along a slightly rotating axis (not a flat ramp)."""
    import numpy as np

    top = np.array(resolved.get("top") or _GRADIENT_DEFAULTS[0], dtype=np.float32)
    bot = np.array(resolved.get("bottom") or _GRADIENT_DEFAULTS[1], dtype=np.float32)
    tilt = 0.18 * math.sin(ph * 0.5 + 0.6)
    axis = np.clip((yy / H + tilt * (xx / W)) / (1.0 + abs(tilt)), 0, 1)
    img = top[None, None, :] * (1 - axis[..., None]) + bot[None, None, :] * axis[..., None]
    vig = np.clip(1.0 - (((xx - W / 2) / (W * 0.95)) ** 2 + ((yy - H / 2) / (H * 0.95)) ** 2), 0, 1)
    return img * (0.90 + 0.10 * vig)[..., None]


def _bake_template(resolved, xx, yy, W, H, ph):
    import numpy as np

    name = resolved.get("template")
    if name == "nature":
        top = np.array(_NATURE["sky"][0], dtype=np.float32)
        bot = np.array(_NATURE["sky"][1], dtype=np.float32)
        g = np.clip(yy / (H * 0.7), 0, 1)
        img = top[None, None, :] * (1 - g[..., None]) + bot[None, None, :] * g[..., None]
        img[yy > H * 0.7] = np.array(_NATURE["hills"][2], dtype=np.float32)
        for i, col in enumerate(_NATURE["hills"]):
            base = H * (0.60 + 0.07 * i)
            amp = H * (0.06 + 0.03 * i)
            y = base - amp * np.sin(xx / W * (3.1 + i) + ph * (0.3 + 0.1 * i) + i * 1.7) \
                - (amp * 0.4) * np.sin(xx / W * (8.3 - i) + i)
            img = np.where(yy[..., None] >= y[..., None], np.array(col, dtype=np.float32), img)
        sun = np.clip(1.0 - np.sqrt(((xx - W * 0.7) / (W * 0.5)) ** 2 + ((yy - H * 0.22) / (H * 0.4)) ** 2),
                      0, 1) ** 3
        img += sun[..., None] * np.array(_NATURE["light"], dtype=np.float32) * 0.35
        return img
    if name == "city":
        top = np.array(_CITY["sky"][0], dtype=np.float32)
        bot = np.array(_CITY["sky"][1], dtype=np.float32)
        g = np.clip(yy / H, 0, 1) ** 1.2
        img = top[None, None, :] * (1 - g[..., None]) + bot[None, None, :] * g[..., None]
        haze = np.exp(-((yy - H * 0.72) ** 2) / (2 * (H * 0.12) ** 2))
        img += haze[..., None] * np.array(_CITY["light"], dtype=np.float32) * 0.30
        roof = _city_roofline(W, H, int(resolved.get("seed") or 0))
        img = np.where(yy[..., None] >= roof[None, :, None],
                      np.array(_CITY["towers"][0], dtype=np.float32)[None, None, :], img)
        cw, ch = max(6, W // 90), max(8, H // 70)
        col_i = np.arange(W, dtype=np.int64)
        row_i = np.arange(H, dtype=np.int64)
        cell = (((col_i // cw) * 73856093)[None, :] ^ ((row_i // ch) * 19349663)[:, None]
                ^ np.int64(phase_salt(ph))) % np.int64(7)
        win = ((col_i % cw >= 2) & (col_i % cw < cw - 2))[None, :] \
            & ((row_i % ch >= 2) & (row_i % ch < ch - 3))[:, None] & (cell < 2) \
            & (yy >= roof[None, :] + 6) & (yy < H - 4)
        img[win] = np.array(_CITY["light"], dtype=np.float32) * 0.8
        return img
    if name == "abstract":
        stops = np.stack([np.array(c, dtype=np.float32) for c in _ABSTRACT])
        u = (xx / W + 0.22 * np.sin(ph * 0.6 + yy / H * 2.0)) % 1.0
        v = (yy / H + 0.18 * np.cos(ph * 0.5 + xx / W * 2.4)) % 1.0
        f = np.clip((u + v) / 2.0, 0, 1) * (len(stops) - 1)
        i0 = np.floor(f).astype(np.int32)
        i1 = np.minimum(i0 + 1, len(stops) - 1)
        fr = (f - i0)[..., None]
        return stops[i0] * (1.0 - fr) + stops[i1] * fr
    if name == "paper":
        top = np.array(_PAPER["base"][0], dtype=np.float32)
        bot = np.array(_PAPER["base"][1], dtype=np.float32)
        g = np.clip(yy / H, 0, 1)
        img = top[None, None, :] * (1 - g[..., None] * 0.8) + bot[None, None, :] * (g[..., None] * 0.8)
        n = np.sin(xx * 12.9 + yy * 5.1) * np.cos(xx * 3.3 - yy * 9.7)
        img += n[..., None] * 255.0 * _PAPER["grain"]
        vig = np.clip(1.0 - (((xx - W / 2) / (W * 0.7)) ** 2 + ((yy - H / 2) / (H * 0.75)) ** 2), 0, 1)
        return img * (0.86 + 0.14 * vig)[..., None]
    if name == "neon":
        top = np.array(_NEON["base"][0], dtype=np.float32)
        bot = np.array(_NEON["base"][1], dtype=np.float32)
        g = np.clip(yy / H, 0, 1)
        img = top[None, None, :] * (1 - g[..., None]) + bot[None, None, :] * g[..., None]
        for (fx, fy, col, ph2) in ((0.18, 0.32, _NEON["a"], 1.0), (0.82, 0.44, _NEON["b"], 1.2)):
            cx, cy = W * (fx + 0.05 * math.sin(ph * ph2)), H * fy
            r = np.sqrt(((xx - cx) / (W * 0.75)) ** 2 + ((yy - cy) / (H * 0.55)) ** 2)
            img += (np.clip(1.0 - r, 0, 1) ** 2.6)[..., None] * np.array(col, dtype=np.float32) * 0.5
        img[yy > H * 0.80] *= 0.72
        return img
    return _bake_studio({**resolved, "kind": "studio", "variant": "white",
                         "top": _STUDIO["white"][0], "bottom": _STUDIO["white"][1]},
                        xx, yy, W, H, ph)


def phase_salt(ph):
    """Small per-phase integer so baked keyframes differ (twinkle, not strobe)."""
    return int(ph * 97) % 91 + 1


def _city_roofline(w, h, seed):
    """Deterministic skyline per (w,h,seed) — computed once, reused by every phase."""
    import numpy as np

    cache = getattr(_city_roofline, "_cache", {})
    key = (w, h, seed % 97)
    if key in cache:
        return cache[key]
    rng = seed % 97
    roof = np.full(w, int(h * 0.62), dtype=np.int32)
    x = 0
    while x < w:
        bw = max(6, int(w * (0.03 + 0.05 * (((x * 37 + rng * 11) % 100) / 100.0))))
        bh = int(h * (0.10 + 0.30 * (((x * 53 + rng * 29) % 100) / 100.0)))
        roof[x:x + bw] = h - bh
        x += bw + max(1, int(w * 0.006))
    if len(cache) > 8:
        cache.clear()
    cache[key] = roof
    _city_roofline._cache = cache
    return roof


def plate(resolved, width=None, height=None, t=0.0):
    """A ready-to-use uint8 RGB plate (h, w, 3), or ``None``.

    The convenience most renderers want: they keep their own frame loop and just
    need the base image once per clip.
    """
    import numpy as np

    if not resolved:
        return None
    if width and height:
        resolved = dict(resolved, w=int(width), h=int(height))
    img = paint(resolved, t=t)
    if img is None:
        return None
    return np.clip(img, 0, 255).astype(np.uint8)


def shade_subject(img, resolved):
    """Contact shadow so a character/still sits *in* the plate, not on top of it.

    Cheap on purpose: it runs per frame in numpy, on the composited result.
    """
    import numpy as np

    if img is None or not resolved or resolved.get("kind") != "studio":
        return img
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - w / 2) / (w * 0.30)) ** 2 + ((yy - h * 0.80) / (h * 0.035)) ** 2)
    sh = np.clip(1.0 - d, 0, 1) ** 1.8 * (0.16 if resolved.get("variant") == "black" else 0.30)
    out = img.copy()
    out -= sh[..., None] * out.mean(axis=2, keepdims=True) * 0.85
    return np.clip(out, 0, 255)


def ensure_ai_plate(resolved, *, cfg, progress=None):
    """Generate (or reuse) the AI plate for ``{"type":"ai_prompt"}``.

    Returns (ok, note). One file per prompt-hash per project, so 15 scenes asking
    for the same backdrop cost one generation, not fifteen. The engine is the
    project's illustration engine — ComfyUI when configured, otherwise the local
    procedural generator — and the note says which, so nothing reads as a claim.
    """
    if not resolved or resolved.get("kind") != "ai":
        return True, ""
    dst = resolved.get("target") or ""
    if not dst:
        return False, ("AI background needs a project directory to cache its plate — "
                       "this caller must pass project_dir")
    if os.path.exists(dst):
        resolved["kind"] = "plate"
        resolved["path"] = dst
        return True, f"AI background reused from {os.path.basename(dst)}"
    from .engines import illustration as ill

    # generate_still takes its size from cfg (and cover-cropping happens in
    # _bake_image), so the plate is requested at the engine's own resolution.
    res = ill.generate_still(resolved.get("prompt") or "clean background plate", dst, cfg,
                             progress=progress, seed=int(resolved.get("seed") or 0))
    if not res.get("ok") or not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        return False, ("AI background could not be rendered: "
                       f"{str(res.get('reason') or res.get('error') or 'image engine unavailable')[:180]}"
                       " — switch to 🖼️ Custom Image or 📦 Templates")
    resolved["kind"] = "plate"
    resolved["path"] = dst
    return True, (f"AI background rendered once for all scenes "
                  f"({res.get('engine') or 'local'}) → {os.path.basename(dst)}")


def catalog(data_root=""):
    """Payload for ``GET /api/backgrounds`` — the UI renders this, nothing inline."""
    types = []
    for k in KINDS:
        t = dict(BACKGROUNDS[k])
        # the caption warning the QA gate would give after a render, answered before
        # it: a near-white plate with white subtitles is the usual complaint
        note = contrast_note(t.get("default"))
        if note:
            t["note"] = note
        ok, why = validate(t.get("default"))
        if not ok:
            # "Custom Image" and "AI Generate" start out incomplete by design —
            # the picker must say what is still missing instead of storing the husk
            t["needs"] = str(why)
        types.append(t)
    return {
        "default": DEFAULT_BACKGROUND,
        "types": types,
        "templates": [{"key": k, **v} for k, v in TEMPLATES.items()],
    }


def preview_png(raw, width=320, height=568, data_root=""):
    """A still frame of the plate as PNG bytes, for picker thumbnails."""
    import io

    from PIL import Image

    res = resolve(raw or DEFAULT_BACKGROUND, width=width, height=height, data_root=data_root)
    if not res or res.get("kind") in ("ai", "missing"):
        # no plate on disk to show: an honest stand-in rather than a blank cell
        res = resolve({"type": "gradient", "a": "#101627", "b": "#2b3a63"}
                      if res and res.get("kind") == "ai"
                      else {"type": "gradient", "a": "#3a1c1c", "b": "#7a3b3b"},
                      width=width, height=height)
    img = paint(res, t=0.7)
    if img is None:
        img = paint(resolve({"type": "template", "template": "abstract"},
                            width=width, height=height), t=0.7)
    a = np.clip(img, 0, 255).astype("uint8") if hasattr(np, "clip") else img
    im = Image.fromarray(a)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def prompt_clause(resolved):
    """The ComfyUI/Wan prompt suffix for this background ('' when none)."""
    if not resolved:
        return ""
    t = resolved.get("type")
    if t == "white_studio":
        return "seamless white studio cyclorama, even soft key light, clean professional backdrop"
    if t == "black_studio":
        return "matte black studio backdrop, single soft rim light, high contrast, no props"
    if t == "gradient":
        return (f"smooth two-colour gradient backdrop from {resolved.get('label', '')} "
                "behind the subject, no scenery, no text")
    if t == "template":
        return {"nature": "soft misty green hills at dawn, natural light",
                "city": "night city skyline bokeh behind the subject, warm sodium haze",
                "abstract": "slowly shifting abstract colour mesh backdrop, no objects",
                "paper": "warm paper texture backdrop, faint grain, soft top light",
                "neon": "dark set with cyan and magenta rim glow, reflective floor",
                "studio": "clean studio cyclorama, soft key light"}.get(resolved.get("template"), "")
    if t == "ai_prompt":
        return f"background plate: {resolved.get('prompt') or ''}, static, no text"
    if t == "image":
        return "the supplied background plate stays exactly as provided, static, no text"
    return ""


__all__ = ["KINDS", "TEMPLATES", "BACKGROUNDS", "DEFAULT_BACKGROUND", "normalize", "validate",
           "key_of", "label", "resolve", "paint", "plate", "shade_subject", "ensure_ai_plate",
           "prompt_clause", "contrast_note", "luma", "catalog", "preview_png"]
