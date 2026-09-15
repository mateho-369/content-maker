#!/usr/bin/env python3
"""Compatibility entry point — DEPRECATED NAME.

The White Studio edition of "Love vs Situationship" is rendered by
``render_love_vs_situationship_white.py``, which is also the script invoked by
``3_RENDER_ALL_VIDEOS.bat``. It writes the file the web gallery
(``GET /gallery`` in ``ai_studio/app.py``) actually serves:

    outputs/love_vs_situationship_white/Love_vs_Situationship_White_Final.mp4

Historically this module was a second, divergent implementation that wrote to
``outputs/love_vs_situationship_white_bg/Love_vs_Situationship_WhiteBG.mp4`` —
a path the gallery never matched (it showed up as a 404 in the Uvicorn logs).
To keep a single source of truth, this file now simply delegates to the
canonical renderer and may be removed in a future release.
"""

import runpy
import os

if __name__ == "__main__":
    canonical = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "render_love_vs_situationship_white.py",
    )
    print(
        "[deprecated] render_love_vs_situationship_white_bg.py now delegates to\n"
        "             render_love_vs_situationship_white.py (canonical pipeline)\n"
        "             -> outputs/love_vs_situationship_white/Love_vs_Situationship_White_Final.mp4"
    )
    runpy.run_path(canonical, run_name="__main__")
