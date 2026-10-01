"""Probe: what does gym.make(...) actually return for action_space, and what does
FlattenActionSpaceWrapper see?  Windows / CPU-sim only, num_envs=1."""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
for p in (_REPO_ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import gymnasium as gym  # noqa: E402
from gymnasium import spaces  # noqa: E402

import mani_skill  # noqa: E402
from mani_skill.utils.wrappers.flatten import FlattenActionSpaceWrapper  # noqa: E402

print("mani_skill:", os.path.dirname(mani_skill.__file__))

for cm in ("pd_joint_delta_pos", "pd_ee_delta_pose"):
    print(f"\n=== control_mode={cm} ===")
    try:
        e = gym.make("PegInsertionSide-v1", num_envs=1, reconfiguration_freq=0,
                     obs_mode="state", sim_backend="cpu", control_mode=cm)
    except Exception as exc:
        print(f"  gym.make FAILED: {type(exc).__name__}: {str(exc)[:200]}")
        continue
    print("  type(e)            :", type(e).__name__)
    print("  e.action_space     :", type(e.action_space).__name__, e.action_space)
    print("  e.unwrapped        :", type(e.unwrapped).__name__)
    print("  unwrapped.act_space:", type(e.unwrapped.action_space).__name__,
          getattr(e.unwrapped, "action_space", None))
    print("  unwrapped.single   :", type(getattr(e.unwrapped, "single_action_space", None)).__name__,
          getattr(e.unwrapped, "single_action_space", None))
    try:
        w = FlattenActionSpaceWrapper(e)
        print("  after flatten      :", type(w.action_space).__name__, w.action_space)
        print("  _orig single       :", type(w._orig_single_action_space).__name__)
    except Exception as exc:
        print(f"  FlattenActionSpaceWrapper FAILED: {type(exc).__name__}: {str(exc)[:200]}")
    e.close()
