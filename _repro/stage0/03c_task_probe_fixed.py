"""Stage 0.3 probe #3 -- FIXED.

TRAP DISCOVERED: `python path/to/script.py` puts the SCRIPT'S DIRECTORY at sys.path[0],
NOT the cwd. So any probe living under _repro/stage0/ silently imported the
site-packages mani_skill instead of the fork.

This script forces the fork repo root onto sys.path[0] itself, so it is correct
no matter where it is run from.

Run (from anywhere):
    E:\\Users\\bobxu\\PycharmProjects\\PCK-RL\\_repro\\venv\\Scripts\\python.exe ^
        E:\\Users\\bobxu\\PycharmProjects\\PCK-RL\\_repro\\stage0\\03c_task_probe_fixed.py
"""
import os
import sys

REPO = r"E:\Users\bobxu\PycharmProjects\PCK-RL"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import gymnasium as gym  # noqa: E402
import mani_skill  # noqa: E402
import mani_skill.envs  # noqa: E402
import mani_skill.envs.tasks.tabletop as TT  # noqa: E402

print("REPO                :", REPO)
print("sys.path[0]         :", sys.path[0])
print("mani_skill.__file__ :", mani_skill.__file__)
print("mani_skill.__path__ :", list(mani_skill.__path__))
print("tabletop.__path__   :", list(TT.__path__))
print()

FOCUS = ["PegInsertionSide-v1", "PickCube-v1", "PokeCube-v1", "PlugCharger-v1", "PushCube-v1"]
print("=== [1] which FILE backs each id ===")
for eid in FOCUS:
    try:
        e = gym.make(eid)
        cls = type(e.unwrapped)
        print("  %-22s <- %s.%s" % (eid, cls.__module__, cls.__name__))
        print("  %-22s    %s" % ("", sys.modules[cls.__module__].__file__))
        e.close()
    except Exception as ex:  # noqa: BLE001
        print("  %-22s FAIL %s: %s" % (eid, type(ex).__name__, str(ex)[:120]))

print()
print("=== [2] direct import of each custom module (fork must now win) ===")
import importlib  # noqa: E402

CUSTOM = [
    "peg_insertion_side", "peg_onlyPick_fhz", "peg_onlyInsert_fhzv3",
    "old_peg_onlyInsert_fhzv3", "hammer_onlyPickv3_fhz_psl",
    "two_hammer_onlyPickv3_fhz_psl", "pick_cube", "pick_cube_plate",
]
for mod in CUSTOM:
    full = "mani_skill.envs.tasks.tabletop." + mod
    try:
        m = importlib.import_module(full)
        print("  IMPORT_OK    %-32s %s" % (mod, getattr(m, "__file__", "?")))
    except Exception as ex:  # noqa: BLE001
        print("  IMPORT_FAIL  %-32s %s: %s" % (mod, type(ex).__name__, str(ex)[:120]))

print()
print("=== [3] which of the paper's custom files exist on disk (fork) ===")
ttdir = list(TT.__path__)[0]
for mod in CUSTOM:
    p = os.path.join(ttdir, mod + ".py")
    print("  %-32s %s" % (mod, "EXISTS" if os.path.exists(p) else "MISSING"))
