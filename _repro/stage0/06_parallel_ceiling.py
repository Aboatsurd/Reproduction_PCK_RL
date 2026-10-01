"""Stage 0.5：pointcloud 观测细节 + Windows 多进程并行上限（AsyncVectorEnv）。

自含 sys.path 修复（STATUS.md §1）。Windows 用 spawn，必须放在 __main__ 保护里。
"""
import os
import sys
import time

REPO = r"E:\Users\bobxu\PycharmProjects\PCK-RL"
if REPO not in sys.path:
    sys.path.insert(0, REPO)


def dump_pointcloud():
    import gymnasium as gym
    import mani_skill  # noqa: F401
    import mani_skill.envs  # noqa: F401

    print("=" * 72)
    print("A) pointcloud 观测到底长什么样")
    print("=" * 72)
    env = gym.make("PickCube-v1", obs_mode="pointcloud", sim_backend="cpu", num_envs=1)
    obs, _ = env.reset()
    print("  顶层 keys:", list(obs.keys()))

    pc = obs["pointcloud"]
    print("  pointcloud 子 keys:", list(pc.keys()))
    for k, v in pc.items():
        if isinstance(v, dict):
            print("    %-20s dict -> %s" % (k, list(v.keys())))
            for k2, v2 in v.items():
                shp = tuple(v2.shape) if hasattr(v2, "shape") else ""
                print("        %-16s %-12s %s" % (k2, type(v2).__name__, shp))
        else:
            shp = tuple(v.shape) if hasattr(v, "shape") else ""
            print("    %-20s %-12s %s" % (k, type(v).__name__, shp))

    for sec in ("sensor_param", "agent"):
        if sec in obs and isinstance(obs[sec], dict):
            print("  %s 子 keys: %s" % (sec, list(obs[sec].keys())))
            for k, v in obs[sec].items():
                if isinstance(v, dict):
                    print("    %-20s dict -> %s" % (k, list(v.keys())))
                    for k2, v2 in v.items():
                        shp = tuple(v2.shape) if hasattr(v2, "shape") else ""
                        print("        %-16s %-12s %s" % (k2, type(v2).__name__, shp))
    env.close()
    print()


def make_env(env_id, obs_mode, seed=None):
    def _f():
        import gymnasium as gym
        import mani_skill.envs  # noqa: F401
        e = gym.make(env_id, obs_mode=obs_mode, sim_backend="cpu", num_envs=1)
        if seed is not None:
            e.reset(seed=seed)
        return e
    return _f


def bench_vector(n, obs_mode="state", steps=10, timeout_s=300):
    import gymnasium as gym
    label = "AsyncVectorEnv n=%d obs=%s" % (n, obs_mode)
    t0 = time.time()
    try:
        vec = gym.vector.AsyncVectorEnv([make_env("PickCube-v1", obs_mode, seed=1000 + i)
                                         for i in range(n)])
        obs, _ = vec.reset()
        shp = tuple(obs.shape) if hasattr(obs, "shape") else type(obs).__name__
        t_reset = time.time() - t0
        act = vec.action_space.sample()
        # 只计【纯推进】阶段：reset 很贵（进程 spawn + 建 env），混进去会把数算飞
        t1 = time.time()
        done = 0
        for _ in range(steps):
            vec.step(act)
            done += 1
            if time.time() - t1 > timeout_s:
                break
        dt = time.time() - t1
        gps = (done / dt) if dt > 0 else float("nan")   # vec.step() 次/秒
        print("  %-40s OK  obs=%-14s reset %5.1fs  组步/s %6.2f  总环境步/s %7.2f  每环境/s %6.2f  [%.0fs]"
              % (label, shp, t_reset, gps, gps * n, gps, time.time() - t0))
        vec.close()
        return True
    except Exception as ex:  # noqa: BLE001
        print("  %-42s FAIL %s: %s" % (label, type(ex).__name__,
                                       str(ex).replace("\n", " ")[:160]))
        return False


def bench_single(obs_mode="state", steps=30):
    import gymnasium as gym
    import mani_skill.envs  # noqa: F401
    t0 = time.time()
    env = gym.make("PickCube-v1", obs_mode=obs_mode, sim_backend="cpu", num_envs=1)
    env.reset()
    act = env.action_space.sample()
    t1 = time.time()   # 同样只计纯推进
    for _ in range(steps):
        env.step(act)
    dt = time.time() - t1
    print("  %-40s OK  %6.2f 环境步/s（单环境基准）  [make+reset %.1fs]"
          % ("单环境 num_envs=1 obs=%s" % obs_mode, steps / dt, t1 - t0))
    env.close()


def main():
    dump_pointcloud()

    print("=" * 72)
    print("B) 单环境基线（CPU backend, num_envs=1）")
    print("=" * 72)
    bench_single("state")
    bench_single("pointcloud", steps=10)
    print()

    print("=" * 72)
    print("C) AsyncVectorEnv 多进程能起几路（Windows 并行天花板）")
    print("=" * 72)
    for n in (2, 4, 8, 12, 16):
        if not bench_vector(n, "state", steps=15):
            print("  -> n=%d 失败，停止上探" % n)
            break
    print()
    print("=" * 72)
    print("D) 点云 + 多进程（真正关心的组合）")
    print("=" * 72)
    for n in (2, 4, 8):
        if not bench_vector(n, "pointcloud", steps=6, timeout_s=420):
            print("  -> n=%d 点云版失败，停止上探" % n)
            break


if __name__ == "__main__":
    main()
