# PCK-RL 复现 · 项目文件说明（目录树版）

> **这份文件回答一个问题：仓库里每个文件是干嘛的。**
> 维护规则：**新增 / 删除 / 改名文件时同步更新本文件。**
>
> **颜色标注来源**：
> 🟦 = 上游 ManiSkill3 `v3.0.0b14` 原生（跟论文无关，是 fork 来的底座）
> 🟨 = 论文作者加的（只有很少一块）
> 🟩 = **我们加的**
>
> **读法**：`├──` 后面的第一个词是文件名，后面用对齐的批注说明它干嘛。
> 批注里带 **★** 的 = 复现必须懂的；带 **⚠️** 的 = 有坑，别踩。

---

## 一句话看懂这个仓库

作者把 **整个 ManiSkill3 源码树整个 fork 了一份**，然后往里塞了 4 个他自己的任务环境 + 一堆实验脚本。
**论文的"配方"（PCK-RL 本体）一个字都没给。** `README.md` 里就一句：

> "The source code for pck-rl is being organized and will be released as soon as possible."

（仓库名他还拼错成了 `PCL-RL`。）

所以：**作者给的代码只当"环境 + 资产 + 任务"用，方法从零自己实现。**

---

# 完整目录树

```
PCK-RL/                                     ← 仓库根目录（D:\...\PCK-RL 是它的旧副本）
│
├── README.md                        🟨 333 B。就那一句"源码正在整理中" + License 章节
│
├── .gitignore                       🟩 排除 venv(3.8 GB) / runs/ / _assets/ / __pycache__ / .idea / *.ckpt
├── .gitattributes                   🟩 ⚠️★ 关键文件！强制 *.sh/*.py/*.json/*.md 用 LF 换行
│                                          没有它，.sh 拷到 Linux 会报 bash: /bin/bash^M: bad interpreter
│
├── .git/                            -  77 文件。历史：a3d554c first commit → bf3e425 readme
│                                          → 349085d source code（作者，798 文件 / 966,300 行）
│                                          → 我们 3 笔
├── .idea/                           🟩 8 文件。PyCharm 工程配置，不进 git
│
│
├── mani_skill/                      🟦+🟨 整个 ManiSkill3 源码树。1246 文件 / 205.4 MB
│   │
│   ├── agents/                      🟦 172 文件 / 2.3 MB —— 机器人模型 + 控制器
│   │   ├── robots/panda/panda.py     🟦 ★ 控制器超参都在这：
│   │   │                                  arm_pd_ee_delta_pose: pos_lower/upper = ±0.1, rot_* = ±0.1
│   │   │                                  arm_pd_joint_delta_pos: lower/upper = ±0.1  ← joint_scale
│   │   └── controllers/
│   │       ├── pd_ee_pose.py         🟦 ★ 动作语义。第 57-64 行：动作在机器人【基座系】
│   │       │                              第 197-210 行：位置 clip 到 [-1,1]，旋转按范数裁 ≤1
│   │       └── utils/kinematics.py   🟦 ★ IK。CPU 后端【必须】pinocchio（第 79-89 行）
│   │
│   ├── assets/                      🟦 359 文件 / 181.8 MB —— 网格 / URDF（含 panda_wristcam）
│   │
│   ├── envs/                        🟦+🟨 245 文件 / 5 MB —— 任务环境
│   │   └── tasks/tabletop/          ← ★★ 作者的 4 个任务在这
│   │       ├── peg_onlyPick_fhz.py            🟨 9575 B ✅【主力】
│   │       │                                      第 50 行 @register_env("PegInsertionSide-v1", max_episode_steps=100)
│   │       │                                      第 107 行 sapien.Pose(p=[-0.615,0,0]) ⇒ 世界系↔基座系差 0.615 m
│   │       │                                      第 199-211 行 成功判据：z >= 0.15
│   │       ├── peg_onlyInsert_fhzv3.py        🟨 18513 B ⬜ 同系列，注册名待查
│   │       ├── old_peg_onlyInsert_fhzv3.py    🟨 18657 B ❌ 作者的旧版本残留
│   │       ├── hammer_onlyPickv3_fhz_psl.py   🟨 8837 B ⬜ 论文任务②
│   │       ├── two_hammer_onlyPickv3_fhz_psl.py 🟨 11765 B ⬜ 论文任务③
│   │       ├── hammer.obj                     🟨 1.03 MB 资产（在 git 里，别删）
│   │       ├── hammer.obj.coacd.ply           🟨 1.35 MB 凸分解
│   │       ├── kong.obj / .coacd.ply          🟨 9.4 KB / 27.8 KB 资产
│   │       ├── xiao.obj / .coacd.ply          🟨 18.6 KB / 205.8 KB 资产
│   │       └── （其余 20+ 个）                 🟦 上游任务：pick_cube.py / stack_cube.py / plug_charger.py ...
│   │
│   ├── examples/                    🟦+🟨 130 文件 / 5.6 MB
│   │   └── motionplanning/
│   │       ├── panda/
│   │       │   ├── generate.sh                🟨 561 B 作者手搓的批处理入口
│   │       │   ├── motionplanner.py           🟦 10579 B ⚠️★ 第 103 行用的是 move_to_pose_with_RRTConnect
│   │       │   │                                    = RRT-Connect，【不是论文写的 RRT*】！要换得自己加
│   │       │   ├── run.py                     🟦 7415 B
│   │       │   ├── utils.py                   🟦 3148 B
│   │       │   └── solutions/                 🟦 8 个现成轨迹脚本：
│   │       │       lift_peg_upright.py / peg_insertion_side.py / pick_cube.py / plug_charger.py
│   │       │       pull_cube.py / pull_cube_tool.py / push_cube.py / stack_cube.py
│   │       ├── panda_stick/                   🟦 另一个机器人（motionplanner.py 6311 B）
│   │       │
│   │       ├── tabletop_fhz_2_hammer/         🟨 论文【任务②】
│   │       ├── tabletop_fhz_3_hammer_strike/  🟨 论文【任务③】
│   │       ├── tabletop_fhz_4_peg/            🟨 论文【任务④】
│   │       └── tabletop_fhz_5_peg_insert/     🟨 论文【任务⑤】
│   │           │
│   │           │  （下面这个结构，上面 4 个任务目录里【每个都有一份】）
│   │           ├── fhz_centerpont&keypoint/     🟨 子目录：关键点相关
│   │           ├── fhz_pcd4RLevaluation/        🟨 子目录：点云评测相关
│   │           ├── hammer_grasp.json            🟨 67 B   抓取位姿
│   │           ├── hammer_PCA.json              🟨 1164 B PCA 主轴
│   │           ├── hammer_pointcloud_full.npy   🟨 6140 B 完整点云
│   │           │                                （4_peg / 5_peg_insert 里叫 peg_pointcloud_full.npy，7376 B）
│   │           ├── hammer_pointcloud_1.npy      🟨 ⚠️★ 文件名里的数字 <N> = 作者当年的【接近方向】
│   │           │                                 ⇒ 方向可从文件名免费恢复（这是阶段 1 的关键发现）
│   │           ├── PCA_axis_to_jsonv3.py        🟨 3015 B 主轴 → json
│   │           ├── PCA_plot2D_VLMv10_clean.py   🟨 ⚠️★ 9153 B
│   │           │                                 论文说"VLM 选关键点"，这脚本里其实是【人工 input()】
│   │           │                                 第 104 行 ⇒ 论文的 20%→16% / 20%→4% 无法逐位复现
│   │           ├── env_get_all_pointcloud.py    🟨 6404 B 在环境里取点云
│   │           ├── get_all_pointcloud.py        🟨 3226 B 离线取点云
│   │           ├── env_get_graspDirection_pointcloud.py 🟨 7513 B 采集【接近方向】（带环境）
│   │           ├── get_graspDirection_pointcloud.py     🟨 3494 B 采集【接近方向】（离线）
│   │           ├── demo_random_action.py        🟨 5950 B 随机动作 demo
│   │           ├── test.py                      🟨 537 B  （只在 3_hammer_strike 里有）
│   │           └── test2.py                     🟨 4424 B ⚠️★ 第 63-66 行 if segment[element]==17:
│   │                                                   这是【仿真特权信息】，真机拿不到
│   │
│   ├── evaluation/                  🟦 4 文件
│   ├── render/                      🟦 9 文件 —— SAPIEN 渲染器
│   ├── sensors/                     🟦 12 文件 —— 相机 / 点云传感器
│   ├── shaders/                     🟦 1 文件
│   ├── trajectory/                  🟦 7 文件 —— 演示轨迹的存 / 读 / 回放（阶段 2 会用到）
│   ├── viewer/                      🟦 3 文件 —— 交互式 viewer
│   ├── vector/                      🟦 10 文件
│   │   └── wrappers/gymnasium.py     🟦 ManiSkillVectorEnv（第 15 行）
│   │
│   └── utils/                       🟦 291 文件 / 10.4 MB —— 工具库
│       ├── geometry/rotation_conversions.py  🟦 ★ 四元数↔欧拉↔旋转矩阵，教师模块全靠它
│       │                                         quaternion_to_matrix:44 / matrix_to_quaternion:105
│       │                                         euler_angles_to_matrix:197 / matrix_to_euler_angles:269
│       │                                         quaternion_multiply:407 / quaternion_invert:424
│       ├── gym_utils.py             🟦 ★ 第 102-105 行 clip_and_scale_action（动作反解要用）
│       ├── wrappers/flatten.py      🟦 ⚠️ FlattenActionSpaceWrapper（第 81 行）
│       │                                第 115 行对 Box 调 .items() ⇒ 有 bug；本 fork 的 space 本来就是 Box，多余
│       └── registration.py          🟦 环境注册表
│
│
├── scripts/                         🟦 【全是上游的，不是作者配方】5 文件。别在这浪费时间
│   └── data_generation/
│       ├── rl.sh                    🟦 ⚠️ 9048 B。第 5 行自己写着 "go to the examples/baselines/ppo folder"
│       │                                ⇒ 它根本不是给这个 fork 用的
│       ├── learning_from_demos.sh   🟦 136 B
│       ├── motionplanning.sh        🟦 674 B
│       ├── process_rl_trajectories.py 🟦 7967 B
│       └── README.md                🟦 294 B
│
├── tests/                           🟦 【上游的】14 文件。是上游验它自己那套包的，跟复现论文无关
│   ├── run.sh / test_downloads.py / test_envs.py / test_examples.py / test_gpu_envs.py
│   ├── test_replay_trajectory.py / test_sim_state.py / test_venv.py / test_wrappers.py
│   └── utils.py / __init__.py / structs/
│
│
├── _assets/                         🟩 【空的】0 文件。SAPIEN 资产缓存目录，由 $env:MS_ASSET_DIR 指向
│                                        首次跑会自动下载，不进 git
├── runs/                            🟩 7 文件。训练产物（ppo_kl 的 metrics.csv + ckpt），不进 git
│
│
└── _repro/                          🟩 ★★ 我们的全部工作。43980 文件（其中 3.8 GB 是 venv）
    │
    ├── STATUS.md                    🟩 12238 B 阶段性状态快照
    │
    ├── venv/                        🟩 3.8 GB Python 3.11.5 虚拟环境，【不进 git】
    │
    ├── stage0/                      🟩 阶段 0：环境自检（已完成，留着当回归测试）
    │   ├── 01b_fix_and_smoke.ps1      🟩 修 pkg_resources 报错 + 最小冒烟
    │   ├── 03_registry_probe.py       🟩 查 ManiSkill 环境注册表
    │   ├── 03b_task_probe.py          🟩 任务探针（早期版，有 bug，留作对照）
    │   ├── 03c_task_probe_fixed.py    🟩 ✅ 修好的版本：自建任务 + 查注册归属
    │   ├── 04_stage0_core.py          🟩 ✅ 阶段 0.3 / 0.4 / 0.5 综合自检
    │   ├── 05_verify_cuda.py          🟩 ✅ 验 torch CUDA + sm_120 + pointcloud obs
    │   └── 06_parallel_ceiling.py     🟩 ✅ 测并行上限
    │                                      结论：n=8 是天花板，n=16 崩于页面文件不足
    │
    ├── stage1/                      🟩 阶段 1：位姿构造 + mplib/WSL 探针
    │   ├── 10_pose_constructor.py     🟩 ✅【阶段 1.1/1.2 的交付物】纯 numpy
    │   │                                  把"关键点 + 接近方向"变成 6-DoF 目标位姿
    │   │                                  论文没给这一步 ⇒ 是我们的工程决定
    │   ├── build_mplib.bat            🟩 ❌ 试图在 Windows 编 mplib —— 失败
    │   │                                  （PyPI 无 Windows wheel，sdist 不含 CMakeLists.txt）
    │   ├── probe_mplib_wsl.sh         🟩 ❌ 在 WSL 试 mplib —— 失败
    │   ├── wsl_probe_sapien.py        🟩 ❌ 在 WSL 试 SAPIEN
    │   └── wsl_step0*.sh（9 个）      🟩 ⚠️【坟场】WSL 死磕 SAPIEN 的全过程：
    │       wsl_step0_sapien.sh              wsl_step0_sapien.sh → 0b_fix → 0c_vulkan → 0d_extensions
    │       wsl_step0b_fix.sh                → 0e_nvidia → 0f_sapien_src → 0g_decide → 0h_retry
    │       wsl_step0c_vulkan.sh          ⚠️ 别再跑！WSL 已判死：SAPIEN 无条件索要
    │       wsl_step0d_extensions.sh         VK_KHR_external_semaphore_fd，WSL 的 lavapipe 没有
    │       wsl_step0e_nvidia.sh          ⇒ 留作证据，别删
    │       wsl_step0f_sapien_src.sh
    │       wsl_step0g_decide.sh
    │       wsl_step0h_retry.sh
    │
    ├── stage3/                      🟩 ★★★ 阶段 3：PPO + KL 蒸馏训练器（核心）
    │   ├── teacher.py                 🟩 ★【教师模块】
    │   │                                  AlignConfig（eps / lookahead / monotone / pos_scale / rot_scale
    │   │                                                / sigma_t / mode / joint_scale ...）
    │   │                                  pose_delta_action()  ← 目标位姿→控制器动作，【不需要 IK】
    │   │                                  TrajectoryTeacher.action(state) ← 最近邻 + 进度单调 + 距离门控
    │   │                                  gaussian_kl()  ← 掩码高斯 KL
    │   │                                  ✅ 可独立自测：python teacher.py
    │   ├── ppo_kl.py                  🟩 ★【主训练脚本】
    │   │                                  = 上游 ppo_fast.py 的纯 torch 端口 + 论文 Eq.(7)/Eq.(9)
    │   │                                  4 条偏离写在文件头 docstring
    │   │                                  三种教师：--teacher joint / standin / traj / none
    │   │                                  指标落 runs/<run_name>/metrics.csv
    │   └── probe_action_space.py      🟩 探针：实测两种控制模式的 single_action_space
    │                                      查出了本 fork 的 action space 本来就是扁平 Box
    │
    ├── linux/                       🟩 ★ Linux 上机脚本（纯 ASCII + LF）
    │   ├── setup.sh                   🟩 一键环境：
    │   │                                  nvidia-smi → 【Vulkan 门禁】→ venv → setuptools<81
    │   │                                  → mani_skill==3.0.0b14（只为拉依赖）→ torch cu124
    │   │                                  → 校验 fork 完整 → 写 ~/pckrl-env.sh → 导入自检
    │   └── smoke_gpu.py               🟩 【四问门禁】：
    │                                      Q1 sapien.core.Scene() 能否构造
    │                                      Q2 fork 是否遮蔽 site-packages（并 import 作者的任务）
    │                                      Q2b CPU sim num_envs=1 吞吐
    │                                      Q3 GPU sim  ←【一票否决项】
    │                                      Q4 num_envs=8/32/128 吞吐 + 按论文预算 1,996,800 步估墙钟
    │
    └── logs/                        🟩 11 个历史日志。★【结论的证据】，要引用原始错误文本来这翻，进 git
        ├── 01b_fix_setuptools.log
        ├── 02_smoke_pokecube.log
        ├── 04_stage0_core.log
        ├── 05_install_cuda_torch.log
        ├── 05_verify_cuda.log
        ├── 06_parallel_ceiling.log
        ├── 07_parallel_ceiling_fixed.log
        ├── 10_pose_constructor.log
        ├── 11_build_mplib.log
        └── install_maniskill.log
```

---

# 桌面上的三份文件（**不在仓库里**）

```
C:\Users\bobxu\Desktop\
├── PCK-RL复现_TODOLIST.md              ← 【主线】只列还没做完的事；做完的移出，历史进 §7
├── PCK-RL复现_技术存档.md              ← 证据 / 考古 / 踩坑。每个结论都附可复现的实测
└── PCK-RL复现_LINUX_TODOLIST.md        ← 【只在 Linux 上做的事】上机照这个走
```

---

# 六条关键环境事实（踩过的坑，别再踩）

```
1. sys.path[0] 陷阱  ★★★ 最坑
   venv 的 site-packages 里装着 PyPI 的上游 mani_skill 3.0.0b14（没有 direct_url.json
   ⇒ 非 editable），它【没有】作者的 peg_onlyPick_fhz.py。
   ⇒ 从子目录跑脚本，fork 会被【静默遮蔽】，你改的代码根本不生效。
   ⇒ 所有 _repro/ 脚本开头都内置了 sys.path.insert(0, _REPO_ROOT)
   ⇒ 自检：python -c "import sys;sys.path.insert(0,'.');import mani_skill;print(mani_skill.__file__)"
           必须指向仓库

2. 本机 Windows 做不了 GPU Sim（SAPIEN 要真 GPU 的 Vulkan 驱动）
   也做不了 mplib（Linux-x86_64 专属）

3. Windows 上 pd_ee_delta_pose 构造不出来
   原因：CPU 后端要 pinocchio 做 IK，而 SAPIEN 只为 Linux 打包
   ⇒ 必须用 --teacher joint

4. sapien_env.py:272 硬性拒绝「CPU 后端 + num_envs>1」
   ⇒ Windows 冒烟只能 1 环境

5. 不要用 WSL / 虚拟机跑 SAPIEN —— 已判死

6. .sh 必须 LF —— 靠 .gitattributes 保证

7. 仓库里【没有】pyproject.toml / setup.py / requirements.txt
   ⇒ 这个 fork 不能 pip install -e .，只能靠 sys.path 遮蔽
```

---

# 维护规则

```
1. 新增 / 删除 / 改名文件  →  同步更新本文件
2. 新增的 Linux 脚本       →  必须【纯 ASCII + LF】
3. 不要把作者没给的东西说成"论文的做法"  →  凡是我们的决定，标 [OURS]
4. 作者不给的目录不要自己造  →  比如 _repro/stage2/ 要等真跑 RRT* 时再建
```
