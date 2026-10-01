#!/usr/bin/env python3
"""
PCK-RL reproduction -- Linux GPU-sim gate (G1, single-vote veto).

Why this file exists
--------------------
The ManiSkill support matrix says `WSL/Anything -> GPU Sim: NO` and
`Linux/NVIDIA -> GPU Sim: YES`.  That is a *document*, not a measurement.
This script measures.  Run it BEFORE installing anything else expensive.

It answers, in order, four questions that fail independently:

  Q1 does sapien.core.Scene() construct?      (Vulkan / VK_KHR_external_semaphore_fd)
  Q2 can the CPU sim backend build an env?    (pure-python / asset path)
  Q3 can the GPU sim backend build an env?    (THE GATE -- everything depends on it)
  Q4 how fast is it at num_envs = 8/32/128?   (decides whether 312 iterations is a day or a month)

ASCII only, no non-ASCII output: server locales are frequently not UTF-8.

Usage (on the Linux box, from the repo root, inside the venv):
    python _repro/linux/smoke_gpu.py
    python _repro/linux/smoke_gpu.py --env-id PegInsertionSide-v1 --envs 8 32 128
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
# sys.path[0] trap: running `python subdir/script.py` puts the SCRIPT dir on the
# path, not the repo root, so the fork's mani_skill/ is silently shadowed by
# site-packages and the authors' tasks "disappear" with no error at all.
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def q1_sapien_scene() -> bool:
    try:
        import sapien  # noqa: F401
        import sapien.core

        print(f"       sapien version: {sapien.__version__}")
        s = sapien.core.Scene()
        del s
        record("Q1 sapien.core.Scene()", True)
        return True
    except Exception as e:  # noqa: BLE001
        record("Q1 sapien.core.Scene()", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def q2_import_path() -> bool:
    try:
        import mani_skill

        path = os.path.abspath(mani_skill.__file__)
        is_fork = os.path.normcase(path).startswith(os.path.normcase(_REPO_ROOT))
        print(f"       mani_skill imported from: {path}")
        if not is_fork:
            record("Q2 fork shadows site-packages", False,
                   "site-packages mani_skill won -- the authors' tasks are INVISIBLE")
            return False
        from mani_skill.envs.tasks.tabletop.peg_onlyPick_fhz import (  # noqa: F401
            PegInsertionSideEnv,
        )
        record("Q2 fork shadows site-packages", True)
        return True
    except Exception as e:  # noqa: BLE001
        record("Q2 fork shadows site-packages", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def _make(env_id: str, num_envs: int, sim_backend: str, obs_mode: str = "state"):
    import gymnasium as gym

    return gym.make(
        env_id,
        num_envs=num_envs,
        sim_backend=sim_backend,
        obs_mode=obs_mode,
        reconfiguration_freq=0,
    )


def q3_push_and_step(env_id: str, num_envs: int, sim_backend: str, steps: int) -> float:
    """Build an env, run `steps` env-steps, return env steps per second."""
    env = _make(env_id, num_envs, sim_backend)
    try:
        import numpy as np

        n_act = int(np.prod(env.single_action_space.shape))
        env.reset(seed=0)
        # NOTE: time ONLY the stepping phase.  SAPIEN's reset takes 10-15 s at
        # first call; including it makes the throughput number meaningless.
        t0 = time.perf_counter()
        for _ in range(steps):
            env.step(np.zeros((num_envs, n_act), dtype=np.float32))
        dt = time.perf_counter() - t0
        return num_envs * steps / max(dt, 1e-9)
    finally:
        try:
            env.close()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-id", default="PegInsertionSide-v1")
    ap.add_argument("--envs", type=int, nargs="+", default=[8, 32, 128])
    ap.add_argument("--steps", type=int, default=30)
    args = ap.parse_args()

    print("=" * 72)
    print("PCK-RL Linux GPU-sim gate")
    print(f"  repo root : {_REPO_ROOT}")
    print(f"  env id    : {args.env_id}")
    print(f"  cwd       : {os.getcwd()}")
    print("=" * 72)

    ok1 = q1_sapien_scene()
    ok2 = q2_import_path()
    if not (ok1 and ok2):
        print("\nSTOP: the CPU-side prerequisites failed. Fix those first.")
        return 1

    # ---- Q2b: CPU sim, single env (this works on Windows too) --------------
    try:
        sps = q3_push_and_step(args.env_id, 1, "cpu", args.steps)
        record("Q2b CPU sim, num_envs=1", True, f"{sps:.0f} env steps/s")
    except Exception as e:  # noqa: BLE001
        record("Q2b CPU sim, num_envs=1", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()

    # ---- Q3: THE GATE ------------------------------------------------------
    print("\n--- Q3: GPU sim (single-vote veto) ---")
    gpu_ok = False
    try:
        sps = q3_push_and_step(args.env_id, max(args.envs), "gpu", args.steps)
        record(f"Q3 GPU sim, num_envs={max(args.envs)}", True, f"{sps:.0f} env steps/s")
        gpu_ok = True
    except Exception as e:  # noqa: BLE001
        record(f"Q3 GPU sim, num_envs={max(args.envs)}", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()

    # ---- Q4: throughput curve ---------------------------------------------
    if gpu_ok:
        print("\n--- Q4: throughput ---")
        for n in args.envs:
            try:
                sps = q3_push_and_step(args.env_id, n, "gpu", args.steps)
                print(f"       num_envs={n:4d}  {sps:9.0f} env steps/s")
            except Exception as e:  # noqa: BLE001
                print(f"       num_envs={n:4d}  FAILED: {type(e).__name__}: {e}")

        print("\n  paper budget = 312 iterations x 128 envs x 50 steps = 1,996,800 steps")
        print("  per-task wall clock = 1,996,800 / (env steps per second above)")

    print("\n" + "=" * 72)
    bad = [n for n, ok, _ in RESULTS if not ok]
    if bad:
        print("FAILED: " + ", ".join(bad))
        print("Do not proceed to stage 1.3/2 or stage 3 until the gate passes.")
        return 1
    print("ALL GATES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
