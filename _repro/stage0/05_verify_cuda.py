"""Stage 0.4 验证：CUDA torch 是否真的可用 + pointcloud 观测 + gpu backend 重测。

自含 sys.path 修复（见 STATUS.md §1）。
Run:
    E:\\Users\\bobxu\\PycharmProjects\\PCK-RL\\_repro\\venv\\Scripts\\python.exe ^
        E:\\Users\\bobxu\\PycharmProjects\\PCK-RL\\_repro\\stage0\\05_verify_cuda.py
"""
import os
import sys
import traceback

REPO = r"E:\Users\bobxu\PycharmProjects\PCK-RL"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import torch  # noqa: E402

print("=" * 70)
print("A) torch 是不是真的 CUDA 版")
print("=" * 70)
print("  torch.__version__        :", torch.__version__)
print("  torch.version.cuda       :", torch.version.cuda)
print("  torch.cuda.is_available():", torch.cuda.is_available())
if torch.cuda.is_available():
    print("  device name              :", torch.cuda.get_device_name(0))
    print("  compute capability       : sm_%d%d" % torch.cuda.get_device_capability(0))
try:
    print("  arch_list                :", torch.cuda.get_arch_list())
except Exception as ex:  # noqa: BLE001
    print("  arch_list                : (n/a) %s" % ex)
try:
    _a = torch.randn(64, 64, device="cuda")
    _b = _a @ _a
    torch.cuda.synchronize()
    print("  GPU matmul               : OK", tuple(_b.shape))
except Exception as ex:  # noqa: BLE001
    print("  GPU matmul               : FAIL %s: %s" % (type(ex).__name__, str(ex)[:200]))

print()
print("=" * 70)
print("B) gym.make 各种组合（这次 CUDA torch 已就位）")
print("=" * 70)

import gymnasium as gym  # noqa: E402
import mani_skill  # noqa: E402
import mani_skill.envs  # noqa: E402

print("  fork mani_skill:", mani_skill.__file__)
print()


def brief(ex, n=200):
    return "%s: %s" % (type(ex).__name__, str(ex).replace("\n", " ")[:n])


def trial(title, env_id, **kw):
    desc = ", ".join("%s=%r" % kv for kv in kw.items())
    print("--- %s ---" % title)
    print("    gym.make(%r, %s)" % (env_id, desc))
    env = None
    try:
        env = gym.make(env_id, **kw)
        obs, _ = env.reset()
        dev = type(obs).__name__
        shp = tuple(obs.shape) if hasattr(obs, "shape") else ""
        print("    reset OK   obs=%s %s" % (dev, shp))
        if hasattr(obs, "keys"):
            print("    obs keys  :", list(obs.keys()))
        _, r, _, _, _ = env.step(env.action_space.sample())
        print("    step  OK   reward shape=%s" % (getattr(r, "shape", r),))
        if os.environ.get("S0_TRACE_DETAIL") and hasattr(obs, "keys"):
            for k, v in obs.items():
                print("      [%s] %s %s" % (k, type(v).__name__,
                                           tuple(v.shape) if hasattr(v, "shape") else ""))
        return True
    except Exception as ex:  # noqa: BLE001
        print("    FAIL       %s" % brief(ex))
        if os.environ.get("S0_TRACE"):
            traceback.print_exc()
        return False
    finally:
        if env is not None:
            try:
                env.close()
            except Exception:  # noqa: BLE001
                pass
        print()


os.environ.setdefault("S0_TRACE_DETAIL", "1")

print("### 0.4 主目标：pointcloud 观测 ###")
trial("pointcloud / cpu backend / 1 env", "PickCube-v1",
      obs_mode="pointcloud", sim_backend="cpu", num_envs=1)

print("### pointcloud 的经典组合：rgb+depth（很多 RL 流程用这个）###")
trial("rgbd / cpu backend / 1 env", "PickCube-v1",
      obs_mode="rgbd", sim_backend="cpu", num_envs=1)

print("### 重测 gpu backend（之前缺 cuda.dll，现在 CUDA torch 已装）###")
trial("gpu backend / 1 env", "PickCube-v1", sim_backend="gpu", num_envs=1)
trial("gpu backend / 4 env", "PickCube-v1", sim_backend="gpu", num_envs=4)
trial("gpu backend / 16 env", "PickCube-v1", sim_backend="gpu", num_envs=16)
trial("gpu backend / pointcloud / 4 env", "PickCube-v1",
      obs_mode="pointcloud", sim_backend="gpu", num_envs=4)
