# 上云操作单（CompShare / 优云智算）

> 目标：**一天之内**拿到 `G0 Vulkan` / `G1 GPU Sim` / `G2 mplib` 三道门禁的**证实或证伪**，并测得真实 SPS。
> 配套脚本：`_repro/linux/setup.sh`（环境）· `_repro/linux/smoke_gpu.py`（四问门禁）。
> 来源：`https://www.compshare.cn/price-list`、`https://www.compshare.cn/docs/operation/gpu/cardlessmode`（2026-10 拉取）

---

## 0. 为什么是 CompShare 而不是 AutoDL

| | CompShare（优云智算） | AutoDL |
|---|---|---|
| 4090 24G 最低价 | **1.92 元/h**（14C 32G）· 2.13（14C 64G） | ~2.0–2.6 元/h（分区浮动） |
| **3090 24G** | **1.19 元/h**（16C 64G）· 抢占 **0.83** | 少见 |
| 关机计费 | **关机不收费**（保留数据） | 关机不收费 |
| 无卡模式 | **0.15 元/h** | 0.1 元/h |
| 计费粒度 | **秒级** | 按小时/分钟 |
| 免费云硬盘 | **100 GB** | 需注意系统盘/数据盘 |
| 免费私有镜像 | **30 GB** | 有 |
| 公网 IP / SSH | **免费独享 IP** | 需端口映射 |
| 高校优惠 | **95 折** | 有学生认证优惠 |
| 镜像形态 | **虚机（Ubuntu，有 root）** / 容器 / 社区 | 容器为主 |

> **我们需要的恰恰是「虚机 Ubuntu + root」** —— 要往 `/etc/vulkan/icd.d/` 写文件、要 `apt install`。CompShare 这块更顺手。
> **但 CompShare 的 Vulkan 是否可用没有官方文档背书**（AutoDL 有专门一页）⇒ 这是本次唯一的真风险点，见 §3。

---

## 1. 选机器（就一个原则：显存 ≥ 24 GB）

| 卡型 | 配置 | 按量 /元·h | 抢占 /元·h | 选它？ |
|---|---|---|---|---|
| **RTX 3090 24G** | 16C 64G | **1.19** | 0.83 | ⭐ **首选**——论文用的就是 3090 24 GB，**硬件对齐**且最便宜 |
| **RTX 4090 24G** | 14C 64G | 2.13 | 1.38 | ⭐ 要快就选，约 2–2.5× 吞吐 |
| RTX 4090 24G | 14C 32G | 1.92 | 1.31 | 32 G 内存偏紧，128 环境有被 Kill 风险 |
| RTX 5090 32G | 14C 96G | 3.29 | 2.20 | 过贵，没必要 |
| RTX 3080Ti 12G | 12C 32G | 0.74 | 0.52 | ❌ 12 GB 显存装不下 128 环境 |
| P40 24G | 8C 64G | 0.40 | / | ❌ Pascal，torch/Vulkan 都太老 |
| V100S 32G | 10C 64G | 1.41 | 0.98 | ❌ Volta，SAPIEN Vulkan 兼容性未知 |

**镜像**：选 **Ubuntu 22.04 / 24.04 虚机镜像**（要 root）。**不要**选预装 PyTorch 的容器镜像——我们要自己控 Python 版本。

**Python 版本**：装之前 `python3 -V` 确认。我们验证过的 wheel 是 **cp312**（`sapien 3.0.0b1` / `mplib 0.1.1` / `fast_kinematics 0.2.2`）。若系统 python < 3.10，用 conda/apt 装一个 3.12 再跑 `setup.sh`。

---

## 2. Day-1 时间表（照抄）

### T+0 开机（选 3090 16C 64G，有卡模式）

### T+5min ── ① 系统包（**先装，`toppra` 要现场编译**）

```bash
apt update
apt install -y build-essential python3-dev vulkan-tools libvulkan1 libsm6 libegl1 git curl
nvidia-smi -L
```

### T+15min ── ② Vulkan ICD（**G0，唯一的真风险点**）

```bash
mkdir -p /etc/vulkan/icd.d
cat > /etc/vulkan/icd.d/my_nvidia_icd.json <<'EOF'
{ "file_format_version" : "1.0.0",
  "ICD": { "library_path": "/lib/x86_64-linux-gnu/libEGL_nvidia.so.0",
           "api_version" : "1.3.277" } }
EOF
export VK_ICD_FILENAMES=/etc/vulkan/icd.d/my_nvidia_icd.json
vulkaninfo --summary
```

**✅ 通过判据**：输出里出现 `deviceType = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU` 和 `deviceName = NVIDIA GeForce RTX 30/40 series`
**❌ 失败判据**：出现 `PHYSICAL_DEVICE_TYPE_CPU`（= lavapipe，就是 WSL 死掉的那个）或 `libEGL_nvidia.so.0: cannot open shared object file`

> **为什么必须是 `libEGL_nvidia` 不是 `libGLX_nvidia`**：云服务器没有桌面，headless 下 EGL 才有 vendor-neutral 的初始化路径。AutoDL 官方文档专门强调过这点。
> 先 `ls -l /lib/x86_64-linux-gnu/libEGL_nvidia.so.0` 确认文件存在。

### T+30min ── ③ 拿代码

服务器上**没有**这个仓库。二选一：

```bash
# 方式 A：你已推到 GitHub（推荐）
cd /root && git clone https://github.com/Aboatsurd/PCK-RL.git && cd PCK-RL

# 方式 B：本机打包上传（本机 PowerShell 执行）
#   tar -czf pckrl-src.tgz --exclude=_repro/venv --exclude=.git --exclude=__pycache__ -C E:\Users\bobxu\PycharmProjects PCK-RL
#   然后用 CompShare 控制台的「文件上传」/JupyterLab 传上去
```

> 全仓 tracked 只有 **203.8 MB**（`mani_skill/assets/robots` 145 MB + `environment_maps` 32 MB 是大头，任务加载要用，别删）。`.git` 另有 86 MB。
> 若嫌大：`git clone --depth 1` 可省掉 86 MB 历史。

### T+35min ── ④ 装环境（**2–3 h，主要耗时**）

```bash
cd /root/PCK-RL
bash _repro/linux/setup.sh
source ~/pckrl-env.sh
```

`setup.sh` 会依次：查 `nvidia-smi` → **Vulkan 门禁** → 建 venv → `setuptools<81` → `pip install mani_skill==3.0.0b14` → torch cu124 → 校验 fork 遮蔽 → 写 `~/pckrl-env.sh` → 自检 import。

> ⚠️ **`mplib` / `fast_kinematics` 不用单独装**：`mani_skill` 的 `requires_dist` 里带着
> `mplib==0.1.1; platform_system == "Linux"` 和 `fast_kinematics==0.2.2; platform_system == "Linux"`，
> 且这两个在 PyPI 上**都有 manylinux x86_64 预编译 wheel** ⇒ Linux 上是直接下 wheel，**不编译**。
> 唯一要现编的是 **`toppra`**（只有 sdist）⇒ 所以第 ① 步的 `build-essential` 不能省。

### T+3h ── ⑤ 跑门禁（15 min）

```bash
source ~/pckrl-env.sh
python _repro/linux/smoke_gpu.py --envs 8 32 128 --steps 50
```

四个问题：
- **Q1** `sapien.core.Scene()` 能不能构造（= Vulkan 真的通了）
- **Q2** fork 有没有遮蔽 site-packages（必须指向 `/root/PCK-RL`，不是 `site-packages`）
- **Q3 ⭐ GPU Sim** `backend='gpu', num_envs=1` 能建能 step —— **唯一一票否决项**
- **Q4** `num_envs=8/32/128` 的实测 SPS + 按 **1,996,800 步**估算单任务墙钟

> 脚本只对 `step` 阶段计时（SAPIEN 首次 reset 要 10–15 s，算进去没意义）。

### T+3h15 ── ⑥ G2：mplib 出一条轨迹

```bash
python -c "import mplib; print(mplib.__version__)"
# 然后跑作者的运动规划脚本
python mani_skill/examples/motionplanning/panda/run.py --env-id PegInsertionSide-v1 --obs-mode none --num-traj 1
```

**顺便做一件重要的事**：打印 `mplib.Planner.__init__` 的签名，确认有没有 `planner_type="rrt_star"`。
如果有 ⇒ 阶段 2.1「把 RRT-Connect 换成论文的 RRT\*」就从"自己实现规划器"降级成"**改一个参数**"。

### T+4h ── ⑦ 存镜像 + 取数据 + 关机

```bash
# 控制台 → 制作私有镜像（30 GB 免费）—— 这一步做一次，以后每次租卡省 3 小时
# 回收结果（本机执行）
scp -r root@<ip>:/root/PCK-RL/runs ./runs_cloud
# 然后控制台关机（关机不收费，秒级计费停止）
```

---

## 3. 止损决策树

```
G0 vulkaninfo 出 DISCRETE_GPU ?
├── 否 → 试 AutoDL（它有官方 Vulkan 文档背书）→ 仍失败 ⇒ 放弃云，走双系统/实验室
└── 是
    └── G1 GPU Sim (backend='gpu', num_envs=1) 能 step ?
        ├── 否 → ❌ 一票否决，立刻退租；说明 SAPIEN 与这个平台不兼容
        └── 是
            ├── G2 import mplib ?
            │   ├── 否 → 补 apt / 换 Python 版本；2 小时内搞不定就只做阶段 3（不需要 mplib 也能训）
            │   └── 是 → ✅ 平台可用，按 Q4 的 SPS 决定要不要继续租
```

**任何一个门禁不过就立刻关机**，别为了"再试试"烧钱。

---

## 4. 省钱要点

1. **秒级计费 + 关机不收费** ⇒ 不跑就关机，被中断也不亏。
2. **装好环境立刻做私有镜像**（30 GB 免费）⇒ 以后从零到能跑只要 **2 分钟**，省掉每次 3 h ≈ 6 元。
3. **不要用"无卡模式"装 torch**：无卡模式内存只有 2 GB 量级，`torch` + `mani_skill` 装不动，还会**释放 GPU**（切回来可能卡就没了）。
   无卡模式只用来：传代码、`apt install` 小包、写脚本。
4. **抢占式**便宜 30%（3090 抢占 0.83 元/h），但**随时可能被回收** ⇒ 只适合短任务（门禁、冒烟），**别拿来跑几小时的训练**。
5. **高校 95 折**：注册后走学生认证。
6. **免费 100 GB 云硬盘**够我们用（代码 204 MB + venv ~5 GB + 镜像 ~10 GB），**存储费 ≈ 0**。
   超出才 0.01 元/GB/天。

---

## 5. 成本估算（**诚实版：SPS 没测之前都是区间**）

### 5.1 工作量拆解

| # | 内容 | 卡时 |
|---|---|---|
| A | `apt` + Vulkan ICD + venv + torch cu124 + mani_skill(+mplib) | **2–3.5 h** |
| B | G0/G1/G2 三问 + SPS 测量 | **1–2 h** |
| C | 阶段 2：RRT\* 给 4 个任务生成轨迹 + 调试 | **2–6 h** |
| D | 阶段 3：4 任务 × 199.68 万步训练 | **待 Q4 实测**（乐观 <1 h，悲观 8 h） |
| E | 消融 / 超参扫 / 重跑（对齐 ε、lookahead、σ_t） | **2–8 h** |
| | **合计** | **7–28 卡时** |

> D 之所以区间这么大：Windows CPU Sim 单环境实测 ~150 SPS；GPU Sim 128 环境的吞吐**没有实测过**。按经验应在 3,000–20,000 SPS，2M 步 = 2–11 分钟/任务。但这个数**不能拍脑袋，要等 Q4**。

### 5.2 折算成钱

| 卡型 | 单价 | 7–28 卡时 |
|---|---|---|
| **RTX 3090 24G**（16C 64G） | 1.19 元/h | **8.3 – 33.3 元** |
| RTX 3090 抢占 | 0.83 元/h | 5.8 – 23.2 元 |
| **RTX 4090 24G**（14C 64G） | 2.13 元/h | **14.9 – 59.6 元** |
| RTX 4090 抢占 | 1.38 元/h | 9.7 – 38.6 元 |

### 5.3 建议

> **先充 20 元，只做 A + B（门禁）。**
> 拿到 Q4 的实测 SPS 之后，成本就是**确定数字**了，再决定要不要充第二笔。

| 阶段 | 充值 | 买到什么 |
|---|---|---|
| 第一笔 | **20 元** | 拿到 G0/G1/G2 的结论 + 真实 SPS + 一个存好的私有镜像 |
| 第二笔（可选） | **30–50 元** | 阶段 2 + 阶段 3 + 一轮消融 |
| **总计上限** | **~70 元** | 一套可复现的训练结果 |

**20 块钱买一个确定性，比去实验室求人一周划算得多** —— 而且拿到数字之后，你跟实验室谈"要不要给我独占机器"时，手里是有依据的。

---

## 6. 变通记录

| 日期 | 变更 |
|---|---|
| 2026-10 | 新建。平台从 AutoDL 改为 **CompShare 为主**（关机不收费 + 秒级计费 + 100 GB 免费盘 + 虚机 root）；AutoDL 降为 G0 失败时的备选 |
| 2026-10 | 修正一条早期错误建议：**无卡模式装不了 torch**（内存不足），不要用它装环境 |
