# PCK-RL 复现 · 项目文件说明

> **这份文件回答一个问题：仓库里每个文件是干嘛的。**
> 维护规则：**新增 / 删除 / 改名文件时同步更新本文件**。
> 三色标注来源：🟦 = 上游 ManiSkill3 `v3.0.0b14` 原生 ｜ 🟨 = 论文作者加的 ｜ 🟩 = 我们加的

---

## 0. 一句话看懂这个仓库

作者（`Aboatsurd` / haosulab 系）把 **整个 ManiSkill3 源码树 fork 了一份**，然后在里面塞了：
1. **4 个他自己写的任务环境**（`tabletop_fhz_*` + `peg_onlyPick_fhz.py` 等）；
2. 一堆**规划 / 点云 / PCA / VLM 的实验脚本**（散落在 `mani_skill/examples/motionplanning/` 和 `examples/tasks/` 里，质量参差）；

**而论文的"配方"（PCK-RL 本体）—— 一个字都没给**。`README.md` 里作者原话只有一句：

> "The source code for pck-rl is being organized and will be released as soon as possible."

（顺带一提，仓库名他拼成了 `PCL-RL`。）

所以我们做的事 = **从零把论文方法实现出来，作者给的代码只当"环境 + 资产 + 任务"用。**

---

## 1. 顶层目录

| 路径 | 来源 | 文件数 | 说明 |
|---|---|---|---|
| `.git/` | — | 77 | 历史：`a3d554c first commit` → `bf3e425 readme` → `349085d source code`（作者，798 文件 / 966,300 行）→ 我们 2 笔 |
| `.gitignore` | 🟩 | — | 排除 `_repro/venv/`(3.8 GB)、`runs/`、`_assets/`、`wandb/`、`__pycache__/`、`.idea/`、`*.ckpt/pt/pth` |
| `.gitattributes` | 🟩 | — | **关键**：`*.sh` / `*.py` / `*.json` / `*.md` 强制 `eol=lf`；`*.bat/.cmd/.ps1` 为 `crlf`；`*.obj/.ply/.png/.npy/.npz/.pt/.stl` 为 binary。**没有它，`.sh` 拷到 Linux 会报 `bash: /bin/bash^M: bad interpreter`** |
| `.idea/` | 🟩 | 8 | PyCharm 工程配置，**不进 git** |
| `README.md` | 🟨 | — | 333 B，只有上面那一句 + License 章节 |
| `mani_skill/` | 🟦+🟨 | 1246 | **整个 ManiSkill3 源码树**（205.4 MB）。见 §2 |
| `scripts/` | 🟦 | 5 | **上游的**，不是作者配置。见 §3 |
| `tests/` | 🟦 | 14 | 上游测试。见 §3 |
| `_assets/` | 🟩 | 0 | **空的**。SAPIEN 资产缓存目录，由 `$env:MS_ASSET_DIR` 指向；首次跑会去下载，**不进 git** |
| `_repro/` | 🟩 | 43980 | **我们的全部工作**。见 §4 |
| `runs/` | 🟩 | 7 | 训练产物（`ppo_kl` 的 `metrics.csv` + ckpt），**不进 git** |

> ⚠️ **没有 `pyproject.toml` / `setup.py` / `requirements.txt`** ⇒ 这个 fork **不能 `pip install -e .`**，只能靠 `sys.path` 遮蔽（见 §5）。

---

## 2. `mani_skill/` —— 上游源码树（含作者的改动）

| 子目录 | 文件数 | 说明 |
|---|---|---|
| `agents/` | 172 | 🟦 机器人模型 + 控制器。**复现要懂的都在这**：`agents/robots/panda/panda.py`（控制器超参）、`agents/controllers/pd_ee_pose.py`（动作语义）、`agents/controllers/utils/kinematics.py`（**IK，CPU 后端必须 pinocchio**） |
| `assets/` | 359 | 🟦 181.8 MB 网格 / URDF（含 `panda_wristcam`） |
| `envs/` | 245 | 🟦+🟨 任务环境。作者的 4 个任务在 `envs/tasks/tabletop/`，见下表 |
| `evaluation/` | 4 | 🟦 |
| `examples/` | 130 | 🟦+🟨 **作者塞了大量脚本在这里**，见下表 |
| `render/` | 9 | 🟦 SAPIEN 渲染器 |
| `sensors/` | 12 | 🟦 相机 / 点云传感器 |
| `shaders/` | 1 | 🟦 |
| `trajectory/` | 7 | 🟦 演示轨迹的存 / 读 / 回放 |
| `utils/` | 291 | 🟦 114.4 MB 级工具库。**要用到的**：`utils/geometry/rotation_conversions.py`（四元数 ↔ 欧拉 ↔ 旋转矩阵）、`utils/gym_utils.py`（`clip_and_scale_action`）、`utils/wrappers/flatten.py`、`utils/registration.py` |
| `vector/` | 10 | 🟦 `vector/wrappers/gymnasium.py` 的 `ManiSkillVectorEnv` |
| `viewer/` | 3 | 🟦 交互式 viewer |

### 2.1 🟨 作者自己写的任务环境 —— `mani_skill/envs/tasks/tabletop/`

| 文件 | 大小 | 我们用它吗 |
|---|---|---|
| **`peg_onlyPick_fhz.py`** | 9575 B | ✅ **主力**。注册为 `PegInsertionSide-v1`（第 50 行 `@register_env(..., max_episode_steps=100)`），`_load_agent` 用 `sapien.Pose(p=[-0.615, 0, 0])`（第 107 行），成功判据在第 199–211 行 |
| `peg_onlyInsert_fhzv3.py` | 18513 B | ⬜ 同系列，注册名待查 |
| `old_peg_onlyInsert_fhzv3.py` | 18657 B | ❌ 作者的旧版本残留 |
| `hammer_onlyPickv3_fhz_psl.py` | 8837 B | ⬜ 对应论文任务② |
| `two_hammer_onlyPickv3_fhz_psl.py` | 11765 B | ⬜ 对应论文任务③ |
| `hammer.obj` + `hammer.obj.coacd.ply` | 1.03 MB + 1.35 MB | 🟨 资产（**这两个在 git 里，别删**） |
| `kong.obj` + `.coacd.ply` | 9.4 KB + 27.8 KB | 🟨 资产 |
| `xiao.obj` + `.coacd.ply` | 18.6 KB + 205.8 KB | 🟨 资产 |
| 其余 20+ 个 | — | 🟦 上游任务（`pick_cube.py`、`stack_cube.py`、`plug_charger.py`…） |

### 2.2 🟨 作者的实验脚本 —— `mani_skill/examples/motionplanning/`

**这就是论文第 20%→16% / 20%→4% 那些数字的来源，但它不能自动跑。**

| 路径 | 说明 |
|---|---|
| `panda/generate.sh` 561 B | 🟨 作者手搓的批处理入口 |
| `panda/motionplanner.py` 10579 B | 🟦 上游规划器。⚠️ 作者用的是 `move_to_pose_with_RRTConnect`（第 103 行）= **RRT-Connect，不是论文写的 RRT\*** |
| `panda/run.py` 7415 B | 🟦 |
| `panda/utils.py` 3148 B | 🟦 |
| `panda/solutions/`（8 个） | 🟦 现成的轨迹脚本：`lift_peg_upright.py` `peg_insertion_side.py` `pick_cube.py` `plug_charger.py` `pull_cube.py` `pull_cube_tool.py` `push_cube.py` `stack_cube.py` |
| `panda_stick/` | 🟦 另一个机器人 |
| **`tabletop_fhz_2_hammer/`** | 🟨 论文**任务②**，含两个子目录 `fhz_centerpont&keypoint/` 与 `fhz_pcd4RLevaluation/` |
| **`tabletop_fhz_3_hammer_strike/`** | 🟨 论文**任务③** |
| **`tabletop_fhz_4_peg/`** | 🟨 论文**任务④** |
| **`tabletop_fhz_5_peg_insert/`** | 🟨 论文**任务⑤** |

4 个 `tabletop_fhz_*` 目录里放的（以 `2_hammer` 为例）：

| 文件 | 说明 |
|---|---|
| `hammer_grasp.json` 67 B | 🟨 **抓取位姿** |
| `hammer_PCA.json` 1164 B | 🟨 **PCA 主轴** |
| `hammer_pointcloud_full.npy` 6140 B | 🟨 完整点云 |
| `PCA_axis_to_jsonv3.py` 3015 B | 🟨 主轴 → json |
| **`PCA_plot2D_VLMv10_clean.py`** 9153 B | 🟨 ★**论文说"VLM 选关键点"，这个脚本里其实是 `input()` 人工输入**（第 104 行）⇒ **论文数字无法逐位复现** |
| `env_get_all_pointcloud.py` 6404 B | 🟨 在环境里取点云 |
| `get_all_pointcloud.py` 3226 B | 🟨 离线取点云 |
| `env_get_graspDirection_pointcloud.py` 7513 B / `get_graspDirection_pointcloud.py` 3494 B | 🟨 **接近方向**采集 |
| `demo_random_action.py` 5950 B | 🟨 随机动作 demo |
| `test.py` 537 B / `test2.py` 4424 B | 🟨 ⚠️ `test2.py:63-66` 的 `if segment[element]==17:` 是**仿真特权信息**，真机拿不到 |

---

## 3. `scripts/` 与 `tests/` —— 都是🟦上游的，不是作者配方

**`scripts/`**（`data_generation/` 下）：

| 文件 | 说明 |
|---|---|
| `rl.sh` 9048 B | 上游 RL 训练入口。⚠️ 第 5 行自己写着 "go to the examples/baselines/ppo folder" —— **它不是给这个 fork 用的** |
| `learning_from_demos.sh` 136 B | 上游 |
| `motionplanning.sh` 674 B | 上游 |
| `process_rl_trajectories.py` 7967 B | 上游 |
| `README.md` 294 B | 上游 |

**`tests/`**：`run.sh`、`test_downloads.py`、`test_envs.py`、`test_examples.py`、`test_gpu_envs.py`、`test_replay_trajectory.py`、`test_sim_state.py`、`test_venv.py`、`test_wrappers.py`、`utils.py`、`__init__.py`、`structs/`。
> 这些是**上游拿来验证它自己那套包的**，跑它们跟复现论文没关系，**别浪费时间**。

---

## 4. `_repro/` —— 我们的全部工作🟩

```
_repro/
├── STATUS.md                    # 阶段性状态快照
├── venv/                        # 3.8 GB，不进 git
├── stage0/                      # 阶段 0：环境自检
├── stage1/                      # 阶段 1：位姿构造 + mplib/WSL 探针
├── stage3/                      # 阶段 3：PPO + KL 蒸馏（★ 核心）
├── linux/                       # Linux 上机脚本
└── logs/                        # 11 个运行日志
```

### 4.1 `stage0/` —— 环境自检（**已完成，留着当回归测试**）

| 文件 | 干嘛的 |
|---|---|
| `01b_fix_and_smoke.ps1` | 修 `pkg_resources` 报错 + 最小冒烟 |
| `03_registry_probe.py` | 查 ManiSkill 的**环境注册表**都注册了啥 |
| `03b_task_probe.py` | 任务探针（**早期版本，有 bug**，保留作对照） |
| `03c_task_probe_fixed.py` | ✅ **修好的版本**：自建任务 + 查注册归属 |
| `04_stage0_core.py` | ✅ 阶段 0.3 / 0.4 / 0.5 综合自检 |
| `05_verify_cuda.py` | ✅ 验 torch CUDA + sm_120 + `pointcloud` obs |
| `06_parallel_ceiling.py` | ✅ 测并行上限（得出 **n=8 上限、n=16 崩于页面文件不足**） |

> 这些脚本开头都自带 `sys.path` 修复，**可以从任意目录运行**。

### 4.2 `stage1/` —— 位姿构造 + mplib 探针

| 文件 | 干嘛的 |
|---|---|
| **`10_pose_constructor.py`** | ✅ **阶段 1.1 / 1.2 的交付物**。纯 numpy，把"关键点 + 接近方向"变成 6-DoF 目标位姿。论文没给这一步，是**我们的工程决定** |
| `build_mplib.bat` | 试图在 Windows 编 mplib —— **失败**（PyPI 无 Windows wheel，sdist 不含 `CMakeLists.txt`） |
| `probe_mplib_wsl.sh` | 在 WSL 试 mplib —— 失败 |
| `wsl_probe_sapien.py` | 在 WSL 试 SAPIEN |
| `wsl_step0*.sh`（9 个） | **WSL 死磕 SAPIEN 的全过程**，从 `wsl_step0_sapien.sh` 一路到 `wsl_step0h_retry.sh` |
| — | ⚠️ **这 10 个脚本是"坟场"，别再跑**。WSL 已判死（SAPIEN 无条件索要 `VK_KHR_external_semaphore_fd`，WSL 的 lavapipe 没有）。**留作证据**，别删 |

### 4.3 `stage3/` —— ★ 核心：PPO + KL 蒸馏训练器

| 文件 | 大小 | 干嘛的 |
|---|---|---|
| **`teacher.py`** | — | **教师模块**。`AlignConfig`（`eps`/`lookahead`/`monotone`/`pos_scale`/`rot_scale`/`sigma_t`/`mode`/`joint_scale`…）+ `pose_delta_action()`（把目标位姿反解成控制器动作，**不需要 IK**）+ `TrajectoryTeacher.action(state)`（最近邻 + 进度单调 + 距离门控）+ `gaussian_kl()`（掩码高斯 KL）。**可独立运行自测**：`python teacher.py` |
| **`ppo_kl.py`** | — | **主训练脚本** = 上游 `ppo_fast.py` 的**纯 torch 端口** + 论文 Eq.(7)/Eq.(9)。4 条偏离写在文件头 |
| `probe_action_space.py` | — | 探针：实测 `pd_joint_delta_pos` / `pd_ee_delta_pose` 各自的 `single_action_space`。**它查出了本 fork 的 action space 本来就是扁平 Box**，所以上游那个 `FlattenActionSpaceWrapper` 既多余又有 bug |

**`teacher.py` 的关键设计**（论文全没给，都是我们的决定）：
- `pose_delta_action()` 反解 `a[:3] = (p_tgt − p_cur)/pos_scale`、`a[3:6] = euler_XYZ(q_tgt · q_cur⁻¹)/rot_scale`，再按控制器语义裁剪 —— **因此完全绕开了 IK，Windows 也能跑**
- `mode="ee_pose"` 走 `pd_ee_delta_pose`（**需 IK ⇒ 只能 Linux**）；`mode="joint"` 走 `pd_joint_delta_pos`（**不需要 IK ⇒ Windows 能跑**）
- `monotone=True`：教师进度只能前进，防相位崩塌
- `sigma_t=0.05`：论文没给这个温度，自己定的

**`ppo_kl.py` 的关键设计**：
- **λ [OURS A6]**：用 `|−E[adv·logπ]|` 算 Eq.(9) 的比值（**原式在早期会得到负数，导致 λ 静默卡死在 1.0**），配预热重算 + `clip(λ, 1e-4, 1e4)`
- 三种教师：`--teacher joint`（关节航点，**Windows 可跑**）/ `standin`（EE 航点，需 Linux）/ `traj`（吃真 RRT\* 轨迹 npz）/ `none`（消融）
- ⚠️ `build_standin_joint_traj()` 造的是**占位轨迹，不是论文的教师**，docstring 里写明了 "NOT THE PAPER'S TEACHER -- A PLUMBING STAND-IN"
- 指标落 `runs/<run_name>/metrics.csv`，列见文件里的 `CSV_COLS`

**阶段 2 的轨迹导出契约**（`load_traj_npz()` 就是按这个读的）：
```
tau      (K, T, 7)  float  多起点轨迹；7 = [x,y,z,qw,qx,qy,qz]，机器人基座系
gripper  (K, T)     float  可选，取值 [-1, 1]
```
> ⚠️ **基座系**：`peg_onlyPick_fhz.py:107` 用 `sapien.Pose(p=[-0.615, 0, 0])` 放机器人 ⇒ 世界系与基座系差 **0.615 m**，喂错坐标系教师会全程指向 0.615 m 外的空气。

### 4.4 `linux/` —— Linux 上机脚本🟩

| 文件 | 干嘛的 |
|---|---|
| `setup.sh` | **一键环境**：`nvidia-smi` → **Vulkan 门禁** → venv → `setuptools<81` → `mani_skill==3.0.0b14`（**只为拉依赖**）→ torch cu124 → 校验 fork 完整 → 写 `~/pckrl-env.sh` → 导入自检 |
| `smoke_gpu.py` | **四问门禁**：Q1 `sapien.core.Scene()` ｜ Q2 fork 是否遮蔽 site-packages ｜ Q2b CPU sim ｜ **Q3 GPU sim（一票否决）** ｜ Q4 `num_envs=8/32/128` 吞吐 + 按论文预算 `312×128×50 = 1,996,800` 估墙钟 |

> 两个文件都是**纯 ASCII + LF**（`bash -n` / `py_compile` 都过了）。**写 Linux 脚本时务必保持纯 ASCII**，中文会带来编码麻烦。

### 4.5 `logs/` —— 11 个历史日志

`01b_fix_setuptools.log` · `02_smoke_pokecube.log` · `04_stage0_core.log` · `05_install_cuda_torch.log` · `05_verify_cuda.log` · `06_parallel_ceiling.log` · `07_parallel_ceiling_fixed.log` · `10_pose_constructor.log` · `11_build_mplib.log` · `install_maniskill.log`

> 这些日志是**结论的证据**，论文/汇报里要引用原始错误文本时来这里翻。**进 git**。

---

## 5. 关键环境事实（踩过的坑，别再踩）

1. **`sys.path[0]` 陷阱**：`_repro/venv/Lib/site-packages/` 里装着 **PyPI 的上游 `mani_skill 3.0.0b14`**（没有 `direct_url.json` ⇒ **非 editable**），它**没有**作者的 `peg_onlyPick_fhz.py`。⇒ 从子目录跑脚本时 fork 会被**静默遮蔽**，你改的代码根本不生效。
   - 所有 `_repro/` 脚本开头都内置了 `sys.path.insert(0, _REPO_ROOT)`
   - 自检：`python -c "import sys;sys.path.insert(0,'.');import mani_skill;print(mani_skill.__file__)"` **必须指向仓库**
2. **本机 Windows 做不了 GPU Sim**（SAPIEN 要真 GPU 的 Vulkan 驱动），也做不了 `mplib`（Linux-x86_64 专属）。
3. **Windows 上 `pd_ee_delta_pose` 构造不出来**（CPU 后端要 pinocchio 做 IK，SAPIEN 只为 Linux 打包）⇒ 必须用 `--teacher joint`。
4. **`sapien_env.py:272` 硬性拒绝「CPU 后端 + `num_envs>1`」** ⇒ Windows 冒烟只能 1 环境。
5. **不要用 WSL / 虚拟机跑 SAPIEN**，已判死。
6. **`.sh` 必须 LF**（靠 `.gitattributes` 保证）。

---

## 6. 桌面上的三份文件（**不在仓库里**）

| 文件 | 干嘛的 |
|---|---|
| `PCK-RL复现_TODOLIST.md` | **主线**。只列**还没做完**的事；做完的移出，历史进 §7 |
| `PCK-RL复现_技术存档.md` | 证据 / 考古 / 踩坑。每个结论都附可复现的实测 |
| `PCK-RL复现_LINUX_TODOLIST.md` | **只在 Linux 上做的事**（上机照这个走） |

---

## 7. 维护规则

1. **新增 / 删除文件** → 同步更新本文件。
2. **新增的 Linux 脚本** → 必须**纯 ASCII + LF**。
3. **不要把作者没给的东西说成"论文的做法"** —— 凡是我们的工程决定，标 `[OURS]`。
4. **作者不给的目录不要自己造**（比如 `_repro/stage2/` 要等真跑 RRT\* 时再建）。
