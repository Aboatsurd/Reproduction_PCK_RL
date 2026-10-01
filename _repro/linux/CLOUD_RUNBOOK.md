# 上云操作单（CompShare / 优云智算）

> 目标：**一天之内**拿到 `G0 Vulkan` / `G1 GPU Sim` / `G2 mplib` 三道门禁的**证实或证伪**，并测得真实 SPS。
> 配套脚本：`_repro/linux/setup.sh`（环境）· `_repro/linux/smoke_gpu.py`（四问门禁）。
> 来源：官网 `https://www.compshare.cn/price-list`（2026-10 抓取）+ **2026-10-01 用 `compshare` CLI 实测的实时库存与价格**（见 §0.5，两者冲突一律以 §0.5 为准）。
>
> 🛠️ **本机工具链已就位**：`pip install compshare-cli`（0.5.0）+ DSH skill `compshare-cli`，凭证在 `C:\Users\bobxu\.config\compshare\config.json`（`compshare --json doctor` 7 项通过）。
> **开卡 / 关机 / SSH / 传文件 / 跑断线不掉的后台任务全部可以命令行完成**，不必开控制台 —— 命令速查见 §7。

---

## 0. 为什么是 CompShare 而不是 AutoDL

| | CompShare（优云智算） | AutoDL |
|---|---|---|
| 4090 24G 最低价 | **2.05 元/h**（16C 64G，实测）· 抢占 **1.31** | ~2.0–2.6 元/h（分区浮动） |
| **3090 24G** | **1.13 元/h**（16C 64G，实测）· 抢占 0.79 · **⚠️ 当前无库存，见 §0.5** | 少见 |
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

### 1.1 实测可用性（2026-10-01，`compshare instance search`）

| 可用区 | 代号 | 有哪些卡 |
|---|---|---|
| 上海二A | cn-sh2-01 | 5090 |
| **上海二B** | **cn-sh2-02** | **5090 · 4090 · 4090_48G** · 2080Ti |
| 华北一C | cn-bj2-03 | 4090 |
| **华北二A** | **cn-wlcb-01** | 4090 · 5090 · 4090_48G · 3080Ti · **3090** · 2080 · A800 · H20 · P40 · V100S · A100 |
| 华北二C | cn-wlcb-03 | 4090 · 5090 |

**3090 全网只有华北二A有。**

### 1.2 实测价格（元/h，1×GPU / 16C / 64GiB）

| 卡型 | 可用区 | 按量 | 日 | 月 | 抢占 | 库存 |
|---|---|---|---|---|---|---|
| 4090 24G | 上海二B / 华北二A | **2.05** | 45.10 | 1230.01 | **1.31** | ✅ |
| 4090 24G | 华北一C | 2.05 | 47.52 | 1296.00 | — | — |
| 4090 24G | 华北二C | — | — | — | 1.38 | — |
| 5090 32G | 上海二B（16C 96G） | 3.15 | 69.51 | 1895.82 | 2.09 | ✅ |
| 4090 48G | 华北二A（16C 96G） | 3.13 | 68.97 | 1881.00 | — | — |
| **3090 24G** | 华北二A | 1.13 | 25.06 | 683.65 | 0.79 | ❌ **无货** |

> 列表价 2.15，实付 2.05（平台自带折扣）。**系统盘 100GiB 与系统镜像计费均为 0。**

### 1.3 选它？—— **3090 出局，改 4090**

| 方案 | 配置 | 按量 | 抢占 | 结论 |
|---|---|---|---|---|
| ~~3090 24G~~ | 16C 64G | 1.13 | 0.79 | ❌ **实测无库存**：换 Spot / 换镜像 / 去系统盘，四种组合的 `create --dry-run` 全部报「当前无库存」。`search` 里那个 `ResourceEnough=true` 是**乐观值，不可信** |
| **4090 24G** | **16C 64G** | **2.05** | 1.31 | ⭐ **首选**：有货、Vulkan 无障碍、比 3090 贵 0.92 元/h（全周期多花 ~10 元） |
| 5090 32G | 16C 96G | 3.15 | 2.09 | 想快 40–60% 再考虑，贵 54% |
| 4090 48G | 16C 96G | 3.13 | — | 24 GB 已够，不值得 |
| 3080Ti 12G / P40 / V100S | — | — | — | ❌ 显存或架构不达标 |

> **代价**：论文用的是 3090，我们只能用 4090 ⇒ **汇报时必须写明「复现环境 = RTX 4090 24G，论文 = RTX 3090 24G」**，不要假装硬件一致。

**镜像**：`Ubuntu-nvidia 22.04` = **`compshareImage-1b6bx62uvf70`**（系统镜像，`ImageType=System`，价格 0）。要 root。
备选 `Ubuntu 24.04 64位` = `compshareImage-12rjyhwynazd`。**不要**选预装 PyTorch 的容器镜像——我们要自己控 Python 版本。

**镜像**：选 **Ubuntu 22.04 / 24.04 虚机镜像**（要 root）。**不要**选预装 PyTorch 的容器镜像——我们要自己控 Python 版本。

**Python 版本**：装之前 `python3 -V` 确认。我们验证过的 wheel 是 **cp312**（`sapien 3.0.0b1` / `mplib 0.1.1` / `fast_kinematics 0.2.2`）。若系统 python < 3.10，用 conda/apt 装一个 3.12 再跑 `setup.sh`。

---

## 2. Day-1 时间表（照抄）

### T+0 开机（**4090 @ 上海二B（cn-sh2-02），16C 64G，按量**；3090 无货，见 §1.3）

> 用 CLI 开，不用控制台。先 `--dry-run` 看价格，确认后再去掉它并加 `--yes`，命令见 §7.1。
> **同时设一个 4–6 小时的定时关机**当兜底（§7.5）—— 这是唯一真正防超支的机制。

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
# 方式 A：git clone（推荐；仓库已推上 GitHub 且是 public，无需任何凭证）
cd /root && git clone https://github.com/Aboatsurd/Reproduction_PCK_RL.git && cd Reproduction_PCK_RL

# 方式 B：本机打包上传（本机 PowerShell 执行）
#   tar -czf pckrl-src.tgz --exclude=_repro/venv --exclude=.git --exclude=__pycache__ -C E:\Users\bobxu\PycharmProjects PCK-RL
#   然后用 CompShare 控制台的「文件上传」/JupyterLab 传上去
```

> 远程：`origin` = `https://github.com/Aboatsurd/Reproduction_PCK_RL.git`（**public**，clone 免登录），
> `upstream` = `https://github.com/lqxsds/PCK-RL`（论文作者原仓库，只读）。

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

| 卡型 | 单价（实测） | 7–28 卡时 |
|---|---|---|
| ~~RTX 3090 24G（16C 64G）~~ | ~~1.13 元/h~~ | ❌ **无库存，不可用** |
| **RTX 4090 24G（16C 64G）** | **2.05 元/h** | **14.4 – 57.4 元** |
| RTX 4090 抢占 | 1.31 元/h | 9.2 – 36.7 元 |
| RTX 5090 32G（16C 96G） | 3.15 元/h | 22.1 – 88.2 元 |

### 5.2b 按「开机时长」而不是「卡时」理解

计费单位是**实例处于 Running 的墙钟时间**，与 GPU 利用率无关。**装环境、下载 wheel、apt、我读日志、你等我 —— 只要开机就按秒计费。**
所以上表里的「卡时」应当读作「**开机小时**」，其中包含了所有非计算时间。

**最坏情况对照**：忘关机 12 h（一夜）= **24.6 元**；忘两天 48 h = **98 元**。
⇒ **真正的超支风险是忘关机，不是装环境。** 每次开机都必须配一个定时关机。

### 5.3 建议

> **先充 20 元，只做 A + B（门禁）。**
> 拿到 Q4 的实测 SPS 之后，成本就是**确定数字**了，再决定要不要充第二笔。

| 阶段 | 充值 | 买到什么 |
|---|---|---|
| 第一笔 | **20 元** | 拿到 G0/G1/G2 的结论 + 真实 SPS + 一个存好的私有镜像 |
| 第二笔（可选） | **30–50 元** | 阶段 2 + 阶段 3 + 一轮消融 |
| **总计上限** | **~70 元** | 一套可复现的训练结果 |

**20 块钱买一个确定性，比去实验室求人一周划算得多** —— 而且拿到数字之后，你跟实验室谈"要不要给我独占机器"时，手里是有依据的。

### 5.4 云 vs 实验室：不是二选一，是**先后**关系

**结论：先问实验室，云卡是它的补充而不是替代。**

| | 实验室 4090 | CompShare 4090 |
|---|---|---|
| 钱 | 免费 | 2.05 元/h |
| 能不能 SSH | 要谈 | ✅ 天生 |
| **无人值守 / 随时开随时关** | ❌ 得人在那儿 | ✅ **`instance job` 断线不掉** |
| 非工作时间 | 要谈 | ✅ 随时 |
| 环境坏了 | 你自己修 | 删了重开 |

⇒ 理想分工：**实验室机器跑长训练（免费），云卡跑门禁验证、调试、以及你不在实验室时的无人值守任务。**
先花 20 块在云上把 G0/G1/G2 三问和 SPS 测出来，再去实验室就有**实测依据**，谈条件时不用空口要机器。

### 5.5 关于「配环境的时间算不算钱」

**算。** 见 §5.2b。但有三个杠杆把它压下去：

1. **秒级计费** ⇒ 关了就停，不按整小时取整
2. **关机不收费 + 系统盘保留** ⇒ 环境**只装一次**；装完立刻做私有镜像（30 GB 免费），以后从零到能跑只要 ~2 分钟
3. **定时关机兜底** ⇒ §7.5

---

## 6. 变通记录

| 日期 | 变更 |
|---|---|
| 2026-10 | 新建。平台从 AutoDL 改为 **CompShare 为主**（关机不收费 + 秒级计费 + 100 GB 免费盘 + 虚机 root）；AutoDL 降为 G0 失败时的备选 |
| 2026-10 | 修正一条早期错误建议：**无卡模式装不了 torch**（内存不足），不要用它装环境 |
| 2026-10-01 | 装上 `compshare-cli` 0.5.0 + DSH skill，**改用 CLI 实测**。改写 §0/§1（新增 §1.1 库存、§1.2 实测价、§1.3 选型）与 §5.2/§5.2b/§5.4/§5.5。**关键更正：3090 实测无库存，首选改为 4090 @ 上海二B 2.05 元/h**；此前从官网抄的 1.19/2.13 均作废。新增 §7 CLI 速查 |
| 2026-10-01 | 明确「计费按**开机墙钟时长**，装环境的时间照样算钱」（§5.2b），并把**忘关机**列为头号超支风险 |

---

## 7. CLI 速查（`compshare` 0.5.0，已实测）

> 本机 `compshare.exe` = `C:\Users\bobxu\AppData\Local\Programs\Python\Python311\Scripts\compshare.exe`
> **自动化一律加 `--json`**；全局选项放在子命令**之前**（`compshare --json --profile X instance list`）。
> ⚠️ PowerShell 里 `npm`/`npx`/`compshare` 的 `.ps1` shim 可能被执行策略拦住 ⇒ **直接用 `.exe` 全路径**。
> ⚠️ 远程命令参数必须放在 `--` 之后，否则会被 CLI 当成自己的选项。

```powershell
$exe = "$env:USERPROFILE\AppData\Local\Programs\Python\Python311\Scripts\compshare.exe"
```

### 7.1 开卡（**先 dry-run，确认后才真开**）

```powershell
# ① 看真实库存与价格（不会产生费用）
& $exe --json instance search --region cn-sh2 --zone cn-sh2-02 `
    --gpu 4090 --image compshareImage-1b6bx62uvf70

# ② 预演：打印选中的规格 / 库存 / 价格 / 原始请求
& $exe --json instance create `
    --region cn-sh2 --zone cn-sh2-02 --gpu 4090 --count 1 `
    --cpu 16 --memory 64GiB `
    --image compshareImage-1b6bx62uvf70 --image-source platform `
    --disk 100GiB --charge Postpay `
    --max-count 1 --max-price 20 `
    --name pckrl --dry-run

# ③ 真开：去掉 --dry-run，加 --yes 和超时（**只有用户点头才执行**）
#    同上，末尾改为：--yes --wait --timeout 900
```

### 7.2 查价格（不创建实例）

```powershell
& $exe --json instance price --gpu 4090 --cpu 16 --memory 64GiB `
    --region cn-sh2 --zone cn-sh2-02 --image compshareImage-1b6bx62uvf70
# 返回 Postpay / Day / Month / Spot 四档；Instance 字段单位 = 元/h
```

### 7.3 生命周期

```powershell
& $exe --json instance list --all                       # 列出全部（含已关机）
& $exe --json instance show <ID> --status --spec --billing
& $exe --json instance stop  <ID> --yes --timeout 600   # 关机（停止计费，磁盘保留）
& $exe --json instance start <ID> --timeout 600
& $exe --json instance wait  <ID> --state Running --timeout 600
& $exe --json instance delete <ID> --yes --timeout 600  # 永久删除；加 --release-disk 连数据盘一起删
```

### 7.4 SSH 与传文件

```powershell
& $exe instance ssh <ID>                                    # 交互式 shell
& $exe --json instance ssh <ID> -- nvidia-smi               # 同步跑一条命令
& $exe --json instance ssh <ID> -- sh -lc 'cd /root/PCK-RL && bash _repro/linux/setup.sh'

& $exe --json instance cp <ID> ./pckrl-src.tgz :/root/pckrl-src.tgz   # 上传（远端路径前缀 :）
& $exe --json instance cp <ID> :/root/runs ./runs_cloud                # 下载
```
> 密码重置 / 重装系统后用 `--refresh` 刷新缓存的连接信息；`--no-cache` 强制不用缓存。

### 7.5 ⭐ 断线不掉的后台任务（**这是云卡最大的价值**）

```powershell
# 提交：本地断了、网断了、你关电脑了，Linux 上照样跑
& $exe --json instance job submit <ID> --name setup --cwd /root/PCK-RL `
    -- bash _repro/linux/setup.sh

& $exe --json instance job list <ID>
& $exe --json instance job show <ID> <JOB_ID>
& $exe --json instance job logs <ID> <JOB_ID> --tail 200
& $exe --json instance job wait <ID> <JOB_ID> --timeout 3600

# 增量读日志（拿上一轮的 offset，只读新增部分，省 token）
& $exe --json instance job logs <ID> <JOB_ID> `
    --stdout-offset <STDOUT_OFFSET> --stderr-offset <STDERR_OFFSET> --limit 65536
```
> ⚠️ `job wait` 超时**不会取消**远端任务。重试前先 `job show` 查状态，别重复提交。
> ⚠️ 这正好解决「我不能全天待在实验室」的问题 —— 任务提交后与本地是否连着无关。

### 7.6 定时关机（兜底，**强烈建议每次开卡都设**）

```powershell
& $exe --json instance schedule set    <ID> ...   # 设定自动关机时刻
& $exe --json instance schedule show   <ID>
& $exe --json instance schedule extend <ID> ...   # 跑不完就延
& $exe --json instance schedule cancel <ID>
```

### 7.7 镜像与诊断

```powershell
& $exe --json image list --source platform --region cn-sh2 --zone cn-sh2-02 --all
& $exe --json image create ...            # 装好环境后做私有镜像（30 GB 免费）
& $exe --json doctor                      # 凭证 / 网络 / SSH 自检
& $exe --json <任意命令> --help           # 不确定参数就先看 help（不需凭证）
```

### 7.8 JSON 返回约定

```json
{ "ok": true,  "schema_version": "1", "data": { "items": [...] }, "meta": {...} }
{ "ok": false, "schema_version": "1", "error": { "code": "...", "message": "...", "details": {...} } }
```
**除 `ok` 外还要看进程退出码** —— 批量操作可能部分成功、部分失败并以非零退出。
