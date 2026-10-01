# -*- coding: utf-8 -*-
"""
阶段 1.2：把「关键点 x_i + 方向 d_i」变成 6-DoF 目标位姿。

设计原则：几何约定全部来自仓库里【已经存在】的代码，我们不发明任何东西，
          唯一自己定的是 closing（绕接近轴的自转），因为论文没给，脚本里显式标出。

出处：
  [A] 方向候选 {v1, v2, v3=v1×v2} 的构造：
      mani_skill/examples/motionplanning/tabletop_fhz_4_peg/fhz_pcd4RLevaluation/
      env_get_graspDirection_pointcloud.py:33-43
  [B] TCP 位姿的列向量约定（局部 x/y/z 在世界的方向）：
      mani_skill/agents/robots/panda/panda.py:270-280  build_grasp_pose()
  [C] 「先沿 -z 退 5cm 再过去」的 reach_pose 习惯：
      mani_skill/examples/motionplanning/panda/solutions/pick_cube.py:57

用法：
    python 10_pose_constructor.py <含 *_grasp.json / *_PCA.json 的目录> [direction]
    direction 省略时，自动从该目录的 *_pointcloud_<N>.npy 文件名反推作者当年的选择。
"""
import glob
import json
import os
import sys

import numpy as np

# Windows 控制台默认 GBK，中文和上下标字符会直接抛 UnicodeEncodeError；强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REACH_OFFSET = 0.05   # [C] 上游惯例：沿 TCP 局部 -z 退 5 cm


def load_pair(d):
    """读 <d>/<name>_grasp.json 与 <name>_PCA.json。"""
    grasp_files = glob.glob(os.path.join(d, "*_grasp.json"))
    if not grasp_files:
        raise SystemExit("在 %s 下找不到 *_grasp.json" % d)
    grasp_path = grasp_files[0]
    name = os.path.basename(grasp_path)[: -len("_grasp.json")]
    pca_path = os.path.join(d, name + "_PCA.json")
    with open(grasp_path, "r", encoding="utf-8") as f:
        grasp_point = np.array(json.load(f), dtype=float)
    with open(pca_path, "r", encoding="utf-8") as f:
        pca = json.load(f)
    return name, grasp_point, pca


def guess_direction(d):
    """作者把当年选的 direction 写在文件名里了：*_pointcloud_<N>.npy / *_pointcloud_full.npy。"""
    hits = glob.glob(os.path.join(d, "*_pointcloud_*.npy"))
    for h in hits:
        tag = os.path.basename(h).split("_pointcloud_")[-1][:-4]
        if tag in ("1", "2", "3"):
            return int(tag), os.path.basename(h)
    return None, (os.path.basename(hits[0]) if hits else None)


def build_axes(pca):
    """[A] 复刻作者的构造，连 cross 的先后顺序都保持一致。"""
    center = np.array(pca["center_point"], dtype=float)
    v1 = np.array(pca["principal_axes"][0]["component"], dtype=float)
    v2 = np.array(pca["principal_axes"][1]["component"], dtype=float)
    v3 = np.cross(v1, v2)                      # ★ 与作者完全一致
    axes = [v1 / np.linalg.norm(v1), v2 / np.linalg.norm(v2), v3 / np.linalg.norm(v3)]
    return center, axes


def build_grasp_pose(approaching, closing, center):
    """[B] 逐行复刻 panda.py:270-280，好让脚本不依赖环境就能算。"""
    approaching = np.asarray(approaching, dtype=float)
    closing = np.asarray(closing, dtype=float)
    assert np.abs(1 - np.linalg.norm(approaching)) < 1e-6, "approaching 必须单位化"
    assert np.abs(1 - np.linalg.norm(closing)) < 1e-6, "closing 必须单位化"
    assert np.abs(approaching @ closing) <= 1e-6, "approaching 与 closing 必须正交"
    ortho = np.cross(closing, approaching)
    T = np.eye(4)
    T[:3, :3] = np.stack([ortho, closing, approaching], axis=1)   # 列 = (x, y, z)
    T[:3, 3] = center
    return T


def check_rotation(T):
    """正交感 + 右手系 + det=+1。"""
    R = T[:3, :3]
    orth = np.abs(R.T @ R - np.eye(3)).max()
    det = float(np.linalg.det(R))
    return orth, det


def quat_wxyz(R):
    """sapien.Pose 用的 [w, x, y, z]。"""
    tr = np.trace(R)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return np.array([w, x, y, z])


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    d = sys.argv[1]
    forced = int(sys.argv[2]) if len(sys.argv) > 2 else None

    name, grasp_point, pca = load_pair(d)
    center, axes = build_axes(pca)
    auto, npy = guess_direction(d)

    print("=" * 78)
    print("阶段 1.2 「关键点 + 方向 -> 6-DoF 目标位姿」  目录 = %s" % d)
    print("=" * 78)
    print("物体名           : %s" % name)
    print("关键点 x_i       : [%s]" % ", ".join("%+.6f" % v for v in grasp_point))
    print("PCA 中心点       : [%s]" % ", ".join("%+.6f" % v for v in center))
    for i, a in enumerate(axes):
        print("主轴 v%d          : [%s]   |v%d|=%.6f" %
              (i + 1, ", ".join("%+.6f" % v for v in a), i + 1, np.linalg.norm(a)))
    print("v1·v2 = %+.2e   v1·v3 = %+.2e   v2·v3 = %+.2e   (应全 ~0)"
          % (axes[0] @ axes[1], axes[0] @ axes[2], axes[1] @ axes[2]))
    print("关键点 - 中心点  : [%s]   |距离| = %.6f m"
          % (", ".join("%+.6f" % v for v in (grasp_point - center)),
             np.linalg.norm(grasp_point - center)))
    print("作者当年用的方向 : direction = %s   (从文件名 %s 反推)" % (auto, npy))
    if forced is not None:
        print("本次强制使用     : direction = %d" % forced)

    targets = [forced] if forced is not None else [1, 2, 3]
    print("\n" + "-" * 78)
    print("对每个候选方向构造位姿（closing 取「下一个主轴」，这是我们自己的选择）")
    print("-" * 78)
    for k in targets:
        i = k - 1
        approaching = axes[i]
        closing = axes[(i + 1) % 3]          # ★ 我们的选择，论文没给
        T = build_grasp_pose(approaching, closing, grasp_point)
        orth, det = check_rotation(T)
        q = quat_wxyz(T[:3, :3])
        reach = T.copy()
        reach[:3, 3] = T[:3, 3] - REACH_OFFSET * approaching   # [C] 沿 -z 退 5cm
        mark = "  <== 作者当年选的" if (auto == k and forced is None) else ""
        print("\n direction = %d   (d = v%d)" % (k, k) + mark)
        print("   approaching (= TCP +z) : [%s]" % ", ".join("%+.6f" % v for v in approaching))
        print("   closing     (= TCP +y) : [%s]" % ", ".join("%+.6f" % v for v in closing))
        print("   |R^T R - I|max = %.2e    det(R) = %+.6f   (应 0 / +1)" % (orth, det))
        print("   grasp_pose  p = [%s]" % ", ".join("%+.6f" % v for v in T[:3, 3]))
        print("               q(wxyz) = [%s]" % ", ".join("%+.6f" % v for v in q))
        print("   reach_pose  p = [%s]  (沿 -z 退 %.0f mm)"
              % (", ".join("%+.6f" % v for v in reach[:3, 3]), REACH_OFFSET * 1000))

    print("\n" + "=" * 78)
    print("阶段 1.2 几何部分：完成（未接触仿真）")
    print("下一步 1.3：把 grasp_pose / reach_pose 喂给 mplib，验证可达")
    print("=" * 78)


if __name__ == "__main__":
    main()
