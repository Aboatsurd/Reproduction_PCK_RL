# Stage 0 断点状态 · PCK-RL 复现

> 本文件是「随时叫停 → 从断点继续」的载体。**每完成一个子步骤就更新这里。**
> 对应主清单：`C:\Users\bobxu\Desktop\PCK-RL复现_TODOLIST.md`
> 代码仓：`E:\Users\bobxu\PycharmProjects\PCK-RL`（fork，ManiSkill 3.0.0b14）
> 工作目录：`E:\Users\bobxu\PycharmProjects\PCK-RL\_repro\`
> 最后更新：**2026-09-30 21:15**

---

## 进度速览

| 步骤 | 状态 | 说明 |
|---|---|---|
| 0.0 平台判定 | ✅ 完成 | WSL 出局（Rendering ❌ / GPU Sim ❌）；Windows 可做**单环境**任务 |
| A 只读侦察（PyPI） | ✅ 完成 | go/no-go 全通过，见 §A |
| 0.1a 建 venv | ✅ 完成 | Python 3.11.5，`_repro\venv`，pip 走清华镜像 |
| 0.1b 装依赖 | ✅ **完成**（09-30 20:50） | 另修了一个 setuptools 坑，见 §2 |
| 0.2 标准任务冒烟 | ✅ **通过** | `PokeCube-v1` make/reset/step/close 全过 |
| 0.3 注册自建任务 | ✅ **通过** | 两个作者自建任务都能跑，见 §3 |
| 0.4 `pointcloud` 观测 | 🔄 **正在解除** | 卡在 CPU 版 torch；已定 `torch 2.14.1+cu130`，后台安装中（见 §6） |
| 0.5 并行上限 | ⚠️ **实测完成** | 多进程最多 ~12 路、最佳 n=8；点云最高仅 1.71×。128 并行不可达（见 §5） |

---

## §1 ★ 陷阱：`sys.path[0]` 会让 fork 被**静默** shadow

> `python 某个脚本.py` 时，**`sys.path[0]` = 脚本所在目录，不是当前工作目录**。

后果：放在 `_repro\stage0\` 下的脚本会去 `site-packages` 找 `mani_skill`，
**fork 被忽略且不报任何错** —— 作者自建任务全部"消失"，`PegInsertionSide-v1`
悄悄变成上游原版。（这正是原来那句「从仓库根运行就能 shadow」的漏洞。）

| 做法 | 安全 |
|---|---|
| `python -c "..."`（cwd = 仓库根） | ✅ |
| `python -m 模块`（cwd = 仓库根） | ✅ |
| 脚本开头 `sys.path.insert(0, r"E:\Users\bobxu\PycharmProjects\PCK-RL")` | ✅ |
| `python _repro\stage0\xxx.py` | ❌ **会静默走 site-packages** |

- 证据：fork 的 `mani_skill\envs\tasks\tabletop\__pycache__\` 里有
  `peg_onlyPick_fhz.*.pyc`、`pick_cube_plate.*.pyc`，
  却**没有** `peg_insertion_side.*.pyc`、`pick_cube.*.pyc`。
- `_repro\stage0\03c_task_probe_fixed.py` 与 `04_stage0_core.py` 已在开头自行修复，可直接用。

---

## §2 环境的精确版本（实测）

```
Python          3.11.5
sapien          3.0.0b1        （cp311 win wheel）
mani_skill      3.0.0b14       （从 PyPI 装；运行时被 fork 覆盖，见 §1）
torch           2.14.0         ⚠️ **CPU 版**，这是 0.4 卡住的原因
gymnasium       0.29.1
numpy           1.26.4
trimesh         5.1.0
huggingface_hub 2.0.0
scipy 1.17.1   matplotlib 3.11.2   opencv-python 4.11.0.86   pytorch_kinematics 0.7.4
setuptools      80.10.2         ← 从 84.0.0 降下来的，见下
mplib           ❌ 未装（被标 platform_system=="Linux"，Windows pip 跳过）
rl/torchrl/tensordict  ❌ 未装（阶段 3 才需要）
```

**0.1b 修过的坑 —— `pkg_resources`**
`setuptools 84.0.0` 已移除 `pkg_resources`，而 `sapien/__init__.py:2` 就 `import pkg_resources`
⇒ `import sapien` 直接 `ModuleNotFoundError`。
**修法**：`pip install "setuptools<81"`（现为 80.10.2，会打一条 deprecation warning，无害）。

**另一个假错误**：`[exit code: 1]` 看着吓人，其实是 PowerShell 把 pip 的 stderr
（`[notice] A new release of pip...`）当异常抛出。**pip 本身是成功的**，日志第 234 行有
`Successfully installed ... mani_skill-3.0.0b14 ...`。

---

## §3 0.3 结论：作者自建任务可用，但**有 ID 抢占**

fork 的 `mani_skill\envs\tasks\tabletop\__init__.py` 实际只启用这些导入：

```python
# from .peg_onlyInsert_fhzv3 import PegInsertionSideEnv     ← 被注释掉
from .peg_onlyPick_fhz import PegInsertionSideEnv          ← 生效
from .pick_cube_plate import PickCubeEnv                   ← 生效（覆盖上游 PickCube）
```

实测（fork 生效时）：

| env id | 实际由哪个文件提供 | 能否 make/reset/step |
|---|---|---|
| `PegInsertionSide-v1` | **`peg_onlyPick_fhz.PegInsertionSideEnv`**（作者自建） | ✅ obs `(1,32)` |
| `PickCube-v1` | **`pick_cube_plate.PickCubeEnv`**（作者自建） | ✅ obs `(1,42)` |
| `PokeCube-v1` | `poke_cube.PokeCubeEnv`（上游同名） | ✅ |
| `PlugCharger-v1` / `PushCube-v1` | 上游同名文件 | ✅（已 make 过） |

⚠️ **`hammer_onlyPickv3_fhz_psl` 与 `two_hammer_onlyPickv3_fhz_psl` 跑不到**：
它们也 `@register_env("PegInsertionSide-v1")`，但被 `peg_onlyPick_fhz` 抢先注册，
ManiSkill 只打一条 warning 就跳过：
```
WARNING - Env PegInsertionSide-v1 is already registered. Skip registration.
```
⇒ **想跑论文的 Hammer Strike Peg，必须改 `tabletop/__init__.py` 的导入顺序/注释**（那会改动作者仓的文件，需先记录）。**目前未改。**

其余自建模块均可 `import`（`peg_onlyInsert_fhzv3`、`old_peg_onlyInsert_fhzv3`、
`two_hammer_onlyPickv3_fhz_psl`、`pick_cube`、`pick_cube_plate` 全部 `IMPORT_OK`）。

---

## §4 ❌ 0.4 卡住的原因：`pointcloud` 需要 **CUDA 版 torch**

```
gym.make("PickCube-v1", obs_mode="pointcloud", sim_backend="cpu", num_envs=1)
  -> AssertionError: Torch not compiled with CUDA enabled
```

**不是渲染问题**（Windows 渲染是 ✅），而是 ManiSkill 的点云管线在 **torch 侧**做
深度→点云的投影，硬性要求 CUDA torch。当前装的是 CPU 版 torch（当初为了绕开 `sm_120`）。

**⇒ 当初"阶段 0 用 CPU torch"的决策在此处失效**，必须换 CUDA torch。
待验证：`sm_120`（RTX 5060 Blackwell）要 torch ≥ 2.7 ⇒ 需确认可用的 cu12x wheel。

---

## §5 0.5 结论：Windows 的并行天花板 = **~8 路，最佳加速比 2.6×**

### 5.1 `num_envs>1` 在 CPU backend 上被硬性禁止

```
gym.make("PickCube-v1", sim_backend="cpu", num_envs=4)
  -> RuntimeError: Cannot set the sim backend to 'cpu' and have multiple environments.
     If you want to do CPU sim backends and have environment vectorization you must
     use multi-processing across CPUs. This can be done via the gymnasium's AsyncVectorEnv API
```

GPU backend 也不通（与 torch 无关，是 SAPIEN 的 PhysX GPU 库）：
```
gym.make("PickCube-v1", sim_backend="gpu", num_envs=1)
  -> FileNotFoundError: Could not find module 'cuda.dll' (or one of its dependencies).
```

### 5.2 `AsyncVectorEnv` 多进程实测（纯推进阶段计时，reset 不计入）

单环境基准（CPU backend，`num_envs=1`）：**state 485.38 环境步/s、pointcloud 124.35 环境步/s**

| n | state 总环境步/s | 加速比 | pointcloud 总环境步/s | 加速比 | reset 耗时 |
|---|---|---|---|---|---|
| 1 | 485.38 | 1.00× | 124.35 | 1.00× | ~1 s |
| 2 | 502.43 | 1.04× | 107.26 | **0.86×（反而更慢）** | 7–13 s |
| 4 | 701.32 | 1.44× | 204.23 | 1.64× | ~10 s |
| **8** | **1262.88** | **2.60×** | **212.52** | **1.71×** | ~10–12.6 s |
| 12 | 1005.44 | 2.07×（回落） | 未测 | | 17.9 s |
| 16 | **FAIL `EOFError`** | | | | |

### 5.3 两个原因

1. **内存提交（commit）打满** —— n=16 时 worker 成批崩：
   ```
   OSError: [WinError 1455] 页面文件太小，无法完成操作
     Error loading "...\torch\lib\shm.dll" / "nvrtc64_130_0.alt.dll" / ...
   ```
   实测：物理内存 **15.4 GB** + 页面文件 **16.2 GB**（C 盘，自动管理）⇒ 提交上限 ≈ **31.6 GB**；
   而 **`torch\lib` = 2.72 GB CUDA DLL，每个 worker 各加载一份**
   （`cublasLt64_13.dll` 456MB、`torch_cuda.dll` 403MB、`torch_cpu.dll` 292MB、`cufft64_12.dll` 271MB）。
   ⇒ **CUDA torch 让每个 worker 变重，是并行的主要瓶颈。**
   **可操作杠杆**：把页面文件移到 E 盘（剩 126.9 GB）并设到 32–48 GB。
2. **点云的 IPC 开销** —— 32768 点 × 4 float ≈ 512 KB/环境/步，`AsyncVectorEnv` 要经管道序列化，
   ⇒ n=2 时点云吞吐**低于单环境**，n=8 也只有 1.71×。

### 5.4 对项目排期的判断

论文 PPO 预算 = `312 iteration × 128 env × 50 step` = **1,996,800 环境步**。
- 按 Windows 最佳（n=8 点云 212.52 步/s）算纯采样时间 ≈ **2.6 小时** —— 单看吞吐并非不可接受。
- **但并行度 8 而非 128，意味着每次迭代只有 1/16 的数据量**，PPO 的批构成、
  λ/KL 正则调度、梯度噪声全都与论文不同步。**这不是"慢一点"，是"换了实验条件"。**
- n=128 在 Windows 上**结构性不可达**（n=16 就已经撞内存墙）。

**⇒ 结论**：Windows 可以做**端到端打通的缩比验证**（n=8，够验证流水线是否正确），
但**论文口径的 128 并行必须换原生 Linux**（GPU Sim ✅ + Rendering ✅）。


---

## §A 侦察结论（PyPI，09-30 已查实，保留备查）

| 判定项 | 结果 |
|---|---|
| `mani_skill 3.0.0b14` 在 PyPI？ | ✅ `py3-none-any.whl`，`requires_python >=3.9` |
| `sapien 3.0.0b1` 有 Windows wheel？ | ✅ `cp310/cp311/cp312-win_amd64` |
| `torch` 是否被 pin 死？ | ❌ 不 pin（`requires_dist` 里没有 torch） |
| `pytorch_kinematics 0.7.4` | ✅ `py3-none-any.whl` |
| `gymnasium` / `numpy` | ✅ pin `0.29.1` / `>=1.22,<2.0` |

⚠️ `mplib==0.1.1` 与 `fast_kinematics==0.2.2` 被标 **`platform_system == "Linux"`**
⇒ Windows 上 pip 不会装。`mplib` 正是 **RRT\* 运动规划器**的底座
（`examples/motionplanning/panda/motionplanner.py`）⇒ **阶段 2 在 Windows 上可能做不了**。

---

## §6 解除 0.4 阻塞的方案（2026-09-30 21:30 决定）

### 选定的 torch
各 CUDA 索引上能取到的最高版本（实测 `pip --dry-run --force-reinstall`）：

| 索引 | 最高 torch | 评价 |
|---|---|---|
| `cu128` | `2.11.0+cu128` | 能用，但比当前 2.14.0 旧，**要降级** |
| `cu129` | `2.9.0+cu129` | 更旧 |
| **`cu130`** | **`2.14.1+cu130`** | ✅ **比当前 2.14.0+cpu 还新，不降级** |
| Aliyun 镜像 | 无 cu130 | ❌ |
| **SJTU 镜像** | 有 | ✅ **选定（国内快）** |

**决定**：`torch==2.14.1+cu130`，源 `https://mirror.sjtu.edu.cn/pytorch-wheels/cu130`
（附 `--extra-index-url` 清华 PyPI 兜底依赖）。日志 `_repro\logs\05_install_cuda_torch.log`。

**为什么 cu130 够**：`sm_120`（Blackwell）从 torch **2.7** 起支持，2.14.1 远高于此；
本机驱动 **610.62** 很新，支持 CUDA 13。**不需要动驱动、不装系统 CUDA Toolkit**
（CUDA wheel 自带 runtime）。

**隔离性**：torch 只落在 `E:\...\_repro\venv\Lib\site-packages\torch`，**不影响全局 Python、
其他项目、游戏/显示**。失败模式也只是"我们的脚本报错"，不是系统级故障。

### 顺带把资产缓存搬离 C 盘
ManiSkill 由环境变量 **`MS_ASSET_DIR`** 决定资产目录（`mani_skill/__init__.py:14-18`，
默认 `~/.maniskill/data`），而 **C 盘只剩 33.9 GB**。

已执行：`setx MS_ASSET_DIR "E:\Users\bobxu\PycharmProjects\PCK-RL\_assets"` + 建目录。
⚠️ `setx` 只对**新开的**进程生效，已有终端要重开。
（`~/.maniskill` 尚未创建，`~/.sapien` 仅 0.22 GB ⇒ 无存量需要搬。）

---

## 下一步（按优先级）

1. ⏳ 等日志出现 `EXIT=0`，验证 `torch.version.cuda` / `cuda.is_available()` /
   `get_arch_list()` 是否含 `sm_120`。
2. 0.4 重跑：确认 `obs_mode="pointcloud"` 的观测结构与点数。
3. 0.5 用 `AsyncVectorEnv` 实测多进程能起几路，作为 Windows 的并行天花板证据。
4. 决定 **Hammer Strike Peg** 要不要改 `__init__.py` 导入顺序（要改动作者仓文件，先记录）。
5. 把 §5 结论写回主 TodoList（阶段 4 的平台决定）。

---

## 复现命令（备用）

```powershell
$repo='E:\Users\bobxu\PycharmProjects\PCK-RL'
$py="$repo\_repro\venv\Scripts\python.exe"
# fork 版任务自检（脚本自带 sys.path 修复）
& $py -W ignore "$repo\_repro\stage0\03c_task_probe_fixed.py"
& $py -W ignore "$repo\_repro\stage0\04_stage0_core.py"
# setuptools 修复（若 pkg_resources 又报错）
& $py -m pip install "setuptools<81"
```

---
*仅供断点续跑用，勿删。*
