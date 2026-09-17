"""Prepare a throwaway studio data dir for the click test.

Usage: python tests/ui_clickflow/prep.py <data-dir>

max_scenes=3 with a 15-row manual board is the trap that used to silently delete
12 scenes of narration on every run; keeping it tiny makes the regression loud.
"""
import json
import os
import sys

DATA = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/studio-uiclick/data")
os.makedirs(DATA, exist_ok=True)
os.environ["STUDIO_DATA_DIR"] = DATA
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ai_studio import config as cfg_mod
from ai_studio.app import StudioState

st = StudioState(DATA)
cfg = st.config()
cfg["machine"]["profile"] = "machine_b"
cfg["tts"]["engine"] = "placeholder"
cfg["rvc"]["engine"] = "bypass"
cfg["video"]["engine"] = "previz"
cfg["sfx"]["engine"] = "procedural"
cfg["video"].update(width=128, height=224, fps=8, steps=4, max_frames=7, min_frames=7)
cfg["assembly"]["fps"] = 8
cfg["pipeline"].update({"scene_target_seconds": 2.5, "scene_min_seconds": 1.5,
                        "scene_max_seconds": 4.0, "max_scenes": 3})
cfg_mod.save(cfg, st.settings_path)
st.invalidate()
print(json.dumps({"data": st.data_root, "max_scenes": cfg["pipeline"]["max_scenes"]}))
