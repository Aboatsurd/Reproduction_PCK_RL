"""Stage 0.3 probe #2:
  1) which fork FILE backs each focus env id
  2) can each custom task module be imported directly (re-registration behaviour)

Run from the FORK repo root."""
import importlib

import gymnasium as gym
import mani_skill.envs  # noqa: F401

FOCUS = ["PegInsertionSide-v1", "PickCube-v1", "PokeCube-v1", "PlugCharger-v1", "PushCube-v1"]
CUSTOM = [
    "peg_insertion_side",
    "peg_onlyPick_fhz",
    "peg_onlyInsert_fhzv3",
    "old_peg_onlyInsert_fhzv3",
    "hammer_onlyPickv3_fhz_psl",
    "two_hammer_onlyPickv3_fhz_psl",
    "pick_cube",
    "pick_cube_plate",
]

print("=== [1] which module/class backs each id ===")
for eid in FOCUS:
    try:
        e = gym.make(eid)
        cls = type(e.unwrapped)
        print("  %-24s <- %s.%s" % (eid, cls.__module__, cls.__name__))
        e.close()
    except Exception as ex:  # noqa: BLE001
        print("  %-24s FAIL %s: %s" % (eid, type(ex).__name__, str(ex)[:120]))

print()
print("=== [2] direct import of each custom module ===")
for mod in CUSTOM:
    full = "mani_skill.envs.tasks.tabletop." + mod
    try:
        importlib.import_module(full)
        print("  IMPORT_OK    %s" % mod)
    except Exception as ex:  # noqa: BLE001
        print("  IMPORT_FAIL  %s  %s: %s" % (mod, type(ex).__name__, str(ex)[:140]))
