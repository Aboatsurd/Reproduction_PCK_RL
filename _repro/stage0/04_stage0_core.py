"""Stage 0 core acceptance: 0.3 (custom tasks) + 0.4 (pointcloud) + 0.5 (parallel).

Self-contained: forces the FORK repo root onto sys.path[0] so it cannot be
shadowed by the site-packages mani_skill regardless of cwd.

Run:
    E:\\Users\\bobxu\\PycharmProjects\\PCK-RL\\_repro\\venv\\Scripts\\python.exe ^
        E:\\Users\\bobxu\\PycharmProjects\\PCK-RL\\_repro\\stage0\\04_stage0_core.py
"""
import os
import sys
import traceback

REPO = r"E:\Users\bobxu\PycharmProjects\PCK-RL"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import gymnasium as gym  # noqa: E402
import mani_skill  # noqa: E402
import mani_skill.envs  # noqa: E402

print("fork mani_skill :", mani_skill.__file__)
print("=" * 78)


def brief(ex, n=160):
    return "%s: %s" % (type(ex).__name__, str(ex).replace("\n", " ")[:n])


def trial(title, env_id, **kw):
    print("\n--- %s ---" % title)
    print("    make(%s, %s)" % (env_id, ", ".join("%s=%r" % kv for kv in kw.items())))
    env = None
    try:
        env = gym.make(env_id, **kw)
        obs, _ = env.reset()
        try:
            import torch
            shape = tuple(obs.shape) if hasattr(obs, "shape") else type(obs).__name__
        except Exception:  # noqa: BLE001
            shape = type(obs).__name__
        print("    reset OK   obs shape =", shape)
        if hasattr(obs, "keys"):
            try:
                print("    obs keys   =", list(obs.keys()))
            except Exception:  # noqa: BLE001
                pass
        a = env.action_space.sample()
        _, r, _, _, _ = env.step(a)
        print("    step  OK   reward =", getattr(r, "shape", r))
        return True
    except Exception as ex:  # noqa: BLE001
        print("    FAIL       %s" % brief(ex, 300))
        if os.environ.get("S0_TRACE"):
            traceback.print_exc()
        return False
    finally:
        if env is not None:
            try:
                env.close()
            except Exception:  # noqa: BLE001
                pass


print("\n############ 0.3 自定义任务（fork 版必须是真的） ############")
r1 = trial("0.3a PegInsertionSide-v1  <- peg_onlyPick_fhz (作者自建)", "PegInsertionSide-v1")

# Which class backs it, to be sure
try:
    e = gym.make("PegInsertionSide-v1")
    c = type(e.unwrapped)
    print("    实际类:", c.__module__ + "." + c.__name__)
    e.close()
except Exception as ex:  # noqa: BLE001
    print("    类查询失败", brief(ex))

r2 = trial("0.3b PickCube-v1  <- pick_cube_plate (作者自建)", "PickCube-v1")

print("\n############ sim_backend 判定：gpu vs cpu ############")
r_gpu = trial("gpu backend", "PickCube-v1", sim_backend="gpu", num_envs=1)
r_cpu = trial("cpu backend", "PickCube-v1", sim_backend="cpu", num_envs=1)
print("\n    >>> gpu backend usable = %s ; cpu backend usable = %s" % (r_gpu, r_cpu))

print("\n############ 0.4 pointcloud 观测 ############")
r_pc = trial("pointcloud (cpu)", "PickCube-v1", obs_mode="pointcloud",
             sim_backend="cpu", num_envs=1)

print("\n############ 0.5 并行上限（cpu backend） ############")
for n in (1, 4, 8, 16, 32):
    ok = trial("num_envs=%d" % n, "PickCube-v1", sim_backend="cpu", num_envs=n)
    if not ok:
        print("    >>> 在 num_envs=%d 处失败，上限在此之前" % n)
        break
