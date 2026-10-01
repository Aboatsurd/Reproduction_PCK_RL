"""Stage 0.3 probe: which env IDs are registered, which class backs them, do they run.

Run from the FORK repo root so the fork's mani_skill shadows the PyPI one:
    cd E:\\Users\\bobxu\\PycharmProjects\\PCK-RL
    _repro\\venv\\Scripts\\python.exe _repro\\stage0\\03_registry_probe.py
"""
import gymnasium as gym
import mani_skill.envs  # noqa: F401  triggers task registration

reg = gym.envs.registry
ids = sorted(reg.keys())
print("TOTAL_REGISTERED:", len(ids))

KEY = ("Peg", "Pick", "Poke", "Plug", "Hammer", "Stack", "Push", "Pull")
focus = [i for i in ids if any(s in i for s in KEY)]
print("FOCUS:", focus)
print()

print("=== which class backs each focus id (module name tells us the fork file) ===")
for eid in focus:
    spec = reg[eid]
    ep = getattr(spec, "entry_point", None)
    mod = getattr(ep, "__module__", None) or str(ep)
    cls = getattr(ep, "__qualname__", None) or ""
    print("  %-28s %s . %s" % (eid, mod, cls))

print()
print("=== can they actually be made and stepped? ===")
for eid in ["PokeCube-v1", "PickCube-v1", "PegInsertionSide-v1", "PlugCharger-v1"]:
    if eid not in reg:
        print("  MISSING  %s" % eid)
        continue
    try:
        e = gym.make(eid)
        e.reset()
        e.close()
        print("  OK       %s" % eid)
    except Exception as ex:  # noqa: BLE001
        print("  FAIL     %s  %s: %s" % (eid, type(ex).__name__, str(ex)[:150]))
