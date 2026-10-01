# 来源说明：作者到底给了多少，我们补了多少

> **这份文件的用途**：写论文 / 汇报 / 答辩时，必须能一句话说清"哪些是作者的代码，哪些是我们写的"。
> **测量方法**：把 fork 的 `mani_skill/` 与 PyPI 上原始的 `mani_skill==3.0.0b14` wheel 逐文件**按内容（去掉 CRLF/LF 差异）比对**。
> 复现该测量的脚本：`_repro/stage0/07_author_share.py`。

---

## 0. 一句话结论

> **作者给的是「环境 + 资产 + 数据工具」，零行「方法」代码。**
> 论文的 PCK-RL 方法（VLM-CoT 与 RRT\*-RL 两条后端）**在这个仓库里一行都没有**。
> 我们的工作在性质上准确的说法是：**在作者发布的环境中重新实现论文方法**，而不是搬运作者的实现。

---

## 1. 仓库的构成（按文件数）

| 部分 | 文件数 | 说明 |
|---|---|---|
| `mani_skill/`（本 fork，去掉 `__pycache__`） | 778 | 全部内容 |
| ├─ 与上游 ManiSkill 3.0.0b14 **完全相同** | 676 | 就是 ManiSkill 框架本身 |
| ├─ 作者**修改**过的上游文件 | **5** | 见 §2 |
| └─ 作者**新增**的文件 | 97 | 见 §3 |
| 上游有、fork 里没有 | 0 | — |

**关键数字：作者只动了 5 个上游文件。** 其余全是原封不动的 ManiSkill。

---

## 2. 作者修改过的 5 个上游文件（全部）

| 文件 | 行数 | 改了什么 |
|---|---|---|
| `mani_skill/envs/tasks/tabletop/__init__.py` | 19 | 把 4 个自建任务注册进去 |
| `mani_skill/envs/tasks/__init__.py` | 24 | 同上 |
| `mani_skill/examples/demo_random_action.py` | 129 | 随机动作 demo 适配调试 |
| `mani_skill/examples/motionplanning/panda/solutions/pick_cube.py` | 92 | 规划示例改动 |
| `mani_skill/utils/wrappers/record.py` | 825 | 录像 wrapper 改动 |

> 前两个是**注册用的胶水**，后三个是**调试便利**。
> **没有一个涉及论文方法。**

---

## 3. 作者新增的 97 个文件 = 73 个自己的 + 24 个上游漏打包的

### 3.1 作者自己的文件（73 个，其中 `.py` 39 个）

**A. 4 个任务环境（`mani_skill/envs/tasks/tabletop/`）**

| 文件 | 行数 |
|---|---|
| `peg_onlyPick_fhz.py` | 246 |
| `peg_onlyInsert_fhzv3.py` | 443 |
| `old_peg_onlyInsert_fhzv3.py` | 445（旧版残留） |
| `hammer_onlyPickv3_fhz_psl.py` | 232 |
| `two_hammer_onlyPickv3_fhz_psl.py` | 290 |
| **小计** | **1,656 行** |

**B. 实验脚本（`mani_skill/examples/motionplanning/tabletop_fhz_{2,3,4,5}_*/`，4 个目录近乎复制粘贴）**

| 脚本 | 行数（单份） | 份数 |
|---|---|---|
| `demo_random_action.py` | 156 | 7 |
| `env_get_graspDirection_pointcloud.py` | 207 / 278 | 4 |
| `get_graspDirection_pointcloud.py` | 100 | 4 |
| `env_get_all_pointcloud.py` | 172 / 250 | 4 |
| `get_all_pointcloud.py` | 97 / 118 | 4 |
| `PCA_plot2D_VLMv10_clean.py` | 186 | 4 |
| `PCA_axis_to_jsonv3.py` | 82 | 4 |
| `test2.py` | 131 | 1 |
| `test.py` | 17 | 1 |

```
磁盘上：39 个 .py，共 6,768 行
按内容去重：24 个，共 4,378 行
扣掉 4 份目录之间的重复：真正的独立逻辑约 3,000 行
```

**C. 数据资产**（这些是**作者真正的价值所在**）：`hammer.obj` / `kong.obj` / `xiao.obj` 及其凸分解、`*_grasp.json`（抓取位姿）、`*_PCA.json`（主轴）、`*_pointcloud_*.npy`（点云，**文件名里的数字编码了作者当年的接近方向**）。

### 3.2 上游漏打包、被误判为"新增"的 24 个
`agents/README.md`、`assets/.gitignore`、`examples/benchmarking/*`、`shaders/postprocessing.comp` 等。
它们在上游 git 仓库里存在，只是 PyPI wheel 没打进去。**不是作者的贡献。**

---

## 4. 作者的代码里有没有论文方法？——没有

对作者自己的目录（`mani_skill/examples/motionplanning/` + `mani_skill/envs/tasks/tabletop/`）做**大小写敏感**扫描：

| 关键词 | 命中 |
|---|---|
| `\bPPO\b` | **0** |
| `\bGAE\b` | **0** |
| `ActorCritic` / `actor_critic` | **0** |
| `clip_coef` | **0** |
| `advantages?` | **0** |
| `log_prob` | **0** |
| `rollout` | **0** |

全仓库范围内：
- `advantage` 命中 2 处 → **都在我们写的 `_repro/stage3/ppo_kl.py`**
- `distill` 命中 1 处 → **在我们写的 `_repro/stage3/ppo_kl.py`**
- `kl_div` 命中 **0** 处

### 决定性证据：`examples/baselines/` 整个目录不存在

| 路径 | 上游 ManiSkill v3.0.0b14 | 本 fork |
|---|---|---|
| `examples/baselines/ppo/ppo_fast.py` | ✅ 存在 | ❌ **不存在** |
| `examples/baselines/ppo/ppo.py` | ✅ 存在 | ❌ 不存在 |
| `examples/baselines/sac/sac.py` | ✅ 存在 | ❌ 不存在 |
| `examples/baselines/` 整个目录 | ✅ 存在 | ❌ **不存在** |

> 我们阶段 3 的 PPO 骨架是从**上游 ManiSkill 的 GitHub**（`raw.githubusercontent.com/mani-skill/ManiSkill/v3.0.0b14/examples/baselines/ppo/ppo_fast.py`）单独下载的，**不是作者给的**。
> 所以 `_repro/stage3/ppo_kl.py` 属于「我们移植的上游代码 + 我们实现的论文方法」，跟作者无关。

---

## 5. 我们补了什么（`_repro/`，共 3,038 行）

| 部分 | 行数 | 性质 |
|---|---|---|
| **`stage3/ppo_kl.py`** | **746** | ★ 论文 Eq.(7)(9) 的 KL 蒸馏 + 上游 PPO 的纯 torch 移植 |
| **`stage3/teacher.py`** | **354** | ★ 教师模块（轨迹→动作反解、最近邻对齐、掩码高斯 KL） |
| **`stage1/10_pose_constructor.py`** | **182** | ★ 目标姿态构造（论文完全没给） |
| **核心方法小计** | **1,282** | |
| `stage0/*` 探针（7 个） | ~590 | 环境自检 / 并行上限 / 本次的来源测量 |
| `stage3/probe_action_space.py` | 42 | 动作空间探针 |
| `linux/setup.sh` + `smoke_gpu.py` | 323 | Linux 上机 |
| `stage1/wsl_*`（坟场） | ~490 | WSL 路线的失败证据 |
| `STATUS.md` | 255 | 状态快照 |

**论文方法部分的代码，100% 是我们写的。**

---

## 6. 论文里作者没给、我们只能自己定的部分

| 缺的东西 | 论文给了吗 | 我们的处理 |
|---|---|---|
| 目标姿态构造（关键点 + 方向 → 6-DoF pose） | ❌ | `10_pose_constructor.py`，标 `[OURS]` |
| 轨迹 → 策略的时间对齐 | ❌（只有 Fig.3 一张图） | 最近邻 + 进度单调 + 距离门控 ε |
| 教师分布的温度 σ_t | ❌ | 自己定 0.05，需扫 |
| 教师动作生成（位姿 → delta action） | ❌ | 反解控制器语义，**不需要 IK** |
| λ 的数值处理 | ⚠️ 只有式 (9) | 式 (9) 直接用会得到负数 ⇒ 取 `abs()` + 预热 |
| 学生网络结构与规模 | ❌ | 自选 256×3 |
| PPO 的操作性超参（batch/clip/lr schedule） | ⚠️ 只给了 lr/γ/λ/epochs | 其余自选 |
| **"VLM 选关键点"** | ⚠️ 声称用 VLM | 作者代码里是**人工 `input()`**（`PCA_plot2D_VLMv10_clean.py:104`）⇒ 论文数字**无法逐位复现** |

---

## 7. 那这还算"复现"吗？

**分两层说，别混。**

### ❌ 按最严格的定义（复现 = 拿作者的代码跑出作者的数字）——不成立
不是因为环境不行，而是因为**作者的仓库里根本没有方法实现**。
"复现作者代码"这件事**没有对象**。

### ✅ 按"复现论文"的定义（用同一环境、按论文方法重建系统、给出可比结果）——成立，但用词要改
准确的表述是：

> **在作者发布的仿真环境与任务资产上，重新实现（re-implement）论文方法，并报告我们自己的实验数字。**

英文对应：**method re-implementation on author-provided environments**，不是 **reproduction of a reference implementation**。

### 为什么这仍然是一次合格的复现工作
1. **作者给的 4 个任务环境 + 资产 + 数据工具是必需的**。没有 `peg_onlyPick_fhz.py` 和那些 `.obj`/`.json`/`.npy`，连"复现什么"都无从谈起。
2. **作者 README 明说源码还在整理**（"being organized and will be released as soon as possible"）⇒ 他**承诺过要放方法代码但还没放**。我们等不到。
3. **论文细节不全是复现的常见难点**，逐位对齐本就不可能——尤其那个"VLM 选点"实际是人工输入。

### 所以汇报时必须写清的三种标签

```
🟦 上游 ManiSkill      —— 仿真框架（第三方）
🟨 本文作者            —— 4 个任务环境 + 资产 + 数据采集脚本（无方法）
🟩 我们                —— 论文方法的全部实现（PPO + KL 蒸馏 + 教师 + 姿态构造）
```

**绝对不能说的话**：把我们的实现说成"作者的代码"，或者把我们的成功率说成"复现了论文的 x%"。
**应该说的话**：「论文未发布方法代码，本文在作者发布的仿真环境上重新实现其方法，得到如下结果」。

---

## 8. 复现这份测量

```powershell
$repo='E:\Users\bobxu\PycharmProjects\PCK-RL'
& "$repo\_repro\venv\Scripts\python.exe" "$repo\_repro\stage0\07_author_share.py"
```

脚本做的事：遍历 fork 的 `mani_skill/` 与 venv 里的原始 wheel `mani_skill/`，**归一化换行符**后按 MD5 比较，输出「新增 / 修改 / 删除」三张清单与行数统计。

> ⚠️ 不做换行归一化会得出"459 个文件被修改"的**假结论**——那只是 CRLF 与 LF 的差别。
