"""
PCK-RL stage 3 -- PPO student + RRT* teacher KL regularisation (Eq. 7 / Eq. 9).

WHY THIS FILE EXISTS
--------------------
The author's own trainer is NOT in the repo.  ``scripts/data_generation/rl.sh:5``
says *"then go to the examples/baselines/ppo folder"*, but this fork ships no
``examples/baselines/`` at all, so ``rl.sh`` is an upstream ManiSkill demo script
(its header cites ``haosulab/ManiSkill_Demonstrations``).  There is no
``**/*ppo*`` file anywhere in the fork.  We therefore port the upstream trainer
for exactly the ManiSkill version this fork is based on, v3.0.0b14:

    https://raw.githubusercontent.com/haosulab/ManiSkill/v3.0.0b14/examples/baselines/ppo/ppo_fast.py

and add the paper's teacher term.

DELIBERATE DEVIATIONS FROM UPSTREAM ppo_fast.py
-----------------------------------------------
1. **plain torch tensors instead of tensordict.**  ``tensordict`` is not a
   ManiSkill dependency and is not installed in ``_repro/venv``; keeping it out
   also means the 4090 box needs no extra pinning.  The rollout/GAE/update maths
   is unchanged.
2. **no CudaGraphModule / no torch.compile** -- upstream's graph capture path is
   GPU-only and would not run under ``--sim-backend cpu``.
3. **no wandb, no tensorboard.**  Metrics go to stdout and to
   ``runs/<run_name>/metrics.csv`` (pandas-plottable, no extra dependency).
4. **added**: teacher rollout buffer, masked Gaussian KL, Eq. (9) lambda with a
   warm-up (see below), deterministic checkpoint evaluation, CSV logging.

THE TWO PAPER EQUATIONS, AND WHAT IS ACTUALLY IMPLEMENTABLE
-----------------------------------------------------------
Eq. (7):   L = L_RL + lambda * L_KL
Eq. (9):   lambda = 10 ** (log10 L_RL - log10 L_KL), computed once at the start.
           L_RL here is |E[adv * log pi]| -- Eq. (9) is a ratio of loss MAGNITUDES,
           and the signed policy term is mildly negative early in training, which
           would silently freeze lambda at its initial value 1.0.

Eq. (9) is only a definition of a *balance*: with that lambda the two terms have
equal magnitude at t=0.  Taken literally it is dangerous, because L_KL at t=0 is
measured under the randomly initialised policy, whose sigma_s is the largest it
will ever be (sigma_s starts at exp(0)=1 here), hence L_KL is the *smallest* it
will ever be, hence lambda is the *largest* it will ever be, and a lucky initial
rollout freezes the student at step 0.  [OURS A6]: we recompute lambda every
``--lam-recompute-every`` iterations for the first ``--lam-warmup-iters``
iterations, clamp it to [``--lam-min``, ``--lam-max``], then freeze it for the
rest of training.  This is our engineering fix, not the paper's method.

USAGE (Windows, CPU sim, no mplib, no IK backend)
-------------------------------------------------
Windows can neither build `mplib` nor construct `pd_ee_delta_pose` (that needs a
pinocchio IK model that SAPIEN only ships for Linux), and ManiSkill refuses
`sim_backend="cpu"` with more than one env.  So the Windows smoke test is:

    python _repro/stage3/ppo_kl.py --teacher joint --num-envs 1 --num-steps 50 \\
        --total-timesteps 2000 --eval-freq 10 --num-eval-envs 1

`--teacher joint` selects `pd_joint_delta_pos`, which needs no IK at all.
The `--teacher standin` (EE waypoints) and real `--teacher traj` paths both need
`pd_ee_delta_pose` and therefore only run on Linux.

USAGE (4090 native Linux, GPU sim, real RRT* trajectories from stage 2)
----------------------------------------------------------------------
    python _repro/stage3/ppo_kl.py --teacher traj --teacher-path _repro/stage3/traj/peg_pick.npz \\
        --sim-backend gpu --num-envs 128 --num-steps 50 --total-timesteps 2000000
"""

from __future__ import annotations

import csv
import math
import os
import random
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions.normal import Normal

# --------------------------------------------------------------------------- #
# sys.path[0] trap (see 技术存档 §1)
# `python _repro/stage3/ppo_kl.py` puts `_repro/stage3` at sys.path[0]; a
# `mani_skill` installed in site-packages would then shadow nothing here but a
# *missing* fork would be filled in silently from site-packages.  Force the
# fork to win.
# --------------------------------------------------------------------------- #
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gymnasium as gym  # noqa: E402
from gymnasium import spaces  # noqa: E402
import tyro  # noqa: E402

import mani_skill.envs  # noqa: F401,E402
from mani_skill.utils.wrappers.flatten import FlattenActionSpaceWrapper  # noqa: E402
from mani_skill.vector.wrappers.gymnasium import ManiSkillVectorEnv  # noqa: E402

from teacher import AlignConfig, TrajectoryTeacher, gaussian_kl  # noqa: E402

import mani_skill  # noqa: E402

CSV_COLS = ["iter", "global_step", "l_rl", "l_kl", "lam", "kl_value", "pg_loss",
            "v_loss", "entropy", "clipfrac", "approx_kl", "grad_norm",
            "teacher_coverage", "train_reward", "eval_success", "sps"]

# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
@dataclass
class Args:
    # -- bookkeeping --
    exp_name: str = "PPO_KL"
    seed: int = 1
    cuda: bool = True
    run_dir: str = "runs"
    tag: str = ""

    # -- environment --
    env_id: str = "PegInsertionSide-v1"
    obs_mode: str = "state"
    control_mode: Optional[str] = None
    """None => `pd_joint_delta_pos` for the joint teacher, else `pd_ee_delta_pose`."""
    render_mode: Optional[str] = None
    sim_backend: str = "cpu"
    """`cpu` works everywhere; `gpu` requires native Linux/NVIDIA (see 技术存档 §5)."""
    num_envs: int = 8
    num_eval_envs: int = 4
    partial_reset: bool = True
    eval_partial_reset: bool = False
    reconfiguration_freq: int = 0
    num_steps: int = 50
    num_eval_steps: int = 50
    eval_freq: int = 25

    # -- PPO.  Values come from the paper's Sec. IV unless marked otherwise. --
    total_timesteps: int = 40000
    learning_rate: float = 3e-4        # paper
    anneal_lr: bool = False
    gamma: float = 0.8                 # paper
    gae_lambda: float = 0.9            # paper
    batch_size: int = 256              # [OURS] upstream default, paper does not say
    update_epochs: int = 4             # paper
    norm_adv: bool = True
    clip_coef: float = 0.2             # [OURS] upstream default, paper does not say
    clip_vloss: bool = True
    ent_coef: float = 0.0              # paper
    vf_coef: float = 0.5               # paper
    max_grad_norm: float = 0.5         # paper
    target_kl: float = 0.03            # [OURS] early-stop guard, upstream has it too
    actor_hidden: int = 256            # [OURS] paper does not specify the network
    critic_hidden: int = 256

    # -- teacher / KL distillation --
    kl_enable: bool = True
    teacher: str = "standin"
    """`standin` (scripted EE waypoints) | `joint` (scripted joint waypoints, no IK) |
    `traj` (real RRT* npz) | `none`."""
    teacher_path: Optional[str] = None
    lam: Optional[float] = None
    """None => Eq. (9) with warm-up.  A float => frozen lambda."""
    lam_warmup_iters: int = 10
    lam_recompute_every: int = 5
    lam_min: float = 1e-4
    lam_max: float = 1e4
    sigma_t: float = 0.05              # [OURS A5] the unsupplied constraint stiffness
    align_eps: float = 0.10            # [OURS A3] distance gate [m]
    align_lookahead: int = 1           # [OURS A4]
    align_monotone: bool = True
    standin_reanchor_every: int = 10
    """[OURS] re-anchor the scripted stand-in teacher every N steps; 0 = only on reset.
    Irrelevant for a real `--teacher traj`, which is fixed for the episode."""
    joint_scale: float = 0.1
    """[rad] pd_joint_delta_pos limit (panda.py:90-98 lower/upper = -+0.1)."""
    arm_dim: int = 7
    """number of arm joints; remaining action dims are gripper."""        # [OURS A2]
    align_track_rot: bool = False      # stand-in teacher carries no orientation
    kl_normalize_by_masked: bool = True

    # -- io --
    save_model: bool = False
    log_every: int = 1
    eval_seed: Optional[int] = 12345


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def layer_init(layer, std=np.sqrt(2), bias_const=0.0):
    """Identical to upstream ppo_fast.py."""
    torch.nn.init.orthogonal_(layer.weight, std)
    torch.nn.init.constant_(layer.bias, bias_const)
    return layer


def obs_to_vec(obs) -> torch.Tensor:
    """obs_mode='state' already gives a flat tensor; be defensive anyway."""
    if torch.is_tensor(obs):
        return obs.flatten(start_dim=1).float()
    if isinstance(obs, dict):
        keys = ["state"] if "state" in obs else sorted(obs.keys())
        parts = []
        for k in keys:
            v = obs[k]
            v = v if torch.is_tensor(v) else torch.as_tensor(v)
            parts.append(v.flatten(start_dim=1).float())
        return torch.cat(parts, dim=1)
    raise TypeError(f"unsupported obs type {type(obs)}")


def find_env(env, attr: str):
    """Walk the wrapper chain looking for `attr` (the ManiSkill task instance)."""
    e = env
    for _ in range(12):
        if hasattr(e, attr):
            return getattr(e, attr)
        nxt = None
        for cand in ("_env", "env", "unwrapped"):
            if hasattr(e, cand):
                v = getattr(e, cand)
                if v is not None and v is not e:
                    nxt = v
                    break
        if nxt is None:
            break
        e = nxt
    raise AttributeError(f"could not find '{attr}' in the wrapper chain of {type(env)}")


def tcp_pose_base(env) -> torch.Tensor:
    """(N,7) TCP pose in the ROBOT BASE frame -- the frame the delta-pose
    controller works in (pd_ee_pose.py:62 ee_pose_at_base)."""
    base = find_env(env, "agent")
    to_base = base.robot.pose.inv()
    return (to_base * base.tcp.pose).raw_pose


def read_align_scales(env) -> tuple:
    """Read pos_upper / rot_lower off the live controller so the teacher inverts
    exactly the mapping that is actually in use (no hard-coded 0.1)."""
    try:
        agent = find_env(env, "agent")
        ctrl = agent.controller
        arm = ctrl["arm"] if isinstance(ctrl, dict) else ctrl.controllers["arm"]
        cfg = arm.config
        return float(np.abs(np.max(cfg.pos_upper))), float(np.abs(np.min(cfg.rot_lower)))
    except Exception as exc:  # pragma: no cover
        print(f"[warn] could not read controller scales ({exc}); falling back to 0.1")
        return 0.1, 0.1


def find_task_object(env):
    """The manipulated object lives on the TASK env, not on the robot agent."""
    for name in ("peg", "obj", "cube", "hammer", "box", "target_object"):
        try:
            return find_env(env, name)
        except AttributeError:
            continue
    raise AttributeError("no task object found in the env chain (tried .peg/.obj/.cube/...)")


def build_standin_traj(env, n_envs: int) -> tuple:
    """*** NOT THE PAPER'S TEACHER -- A PLUMBING STAND-IN. ***

    Synthesises a 5-waypoint reach/descend/grasp/lift trajectory from the scene's
    own ground-truth object pose, anchored at the robot's current TCP pose (which
    is what RRT* naturally does too: it plans from the current configuration).
    It exists so that the alignment + KL plumbing can be exercised on a machine
    where mplib does not exist (Windows).  Replace it on Linux with the stage-2
    RRT* output loaded via ``--teacher traj --teacher-path ...``.
    """
    agent = find_env(env, "agent")
    to_base = agent.robot.pose.inv()
    tcp = (to_base * agent.tcp.pose).raw_pose.clone()            # (N,7) base frame
    obj_b = (to_base * find_task_object(env).pose).raw_pose      # (N,7) base frame

    n = tcp.shape[0]
    T = 5
    dz = torch.tensor([0.0, 0.12, 0.03, 0.03, 0.25], device=tcp.device, dtype=tcp.dtype)
    xy = obj_b[:, None, 0:2].expand(n, T, 2)
    z = obj_b[:, None, 2:3] + dz[None, :, None]

    tau = torch.zeros(n, T, 7, device=tcp.device, dtype=tcp.dtype)
    tau[:, :, 0:3] = torch.cat([xy, z], dim=2)
    tau[:, 0, 0:3] = tcp[:, 0:3]              # waypoint 0 == where the robot is now
    tau[:, :, 3:7] = tcp[:, None, 3:7]        # stand-in carries no orientation change

    gripper = torch.tensor([1.0, 1.0, -1.0, -1.0, -1.0],
                           device=tcp.device, dtype=tcp.dtype).repeat(n, 1)
    return tau, gripper


def robot_qpos(env, arm_dim: int = 7) -> torch.Tensor:
    """(N, arm_dim) current ARM joint positions -- the state the joint-space
    teacher aligns against (joint mode needs no IK, so it also runs on Windows)."""
    robot = find_env(env, "agent").robot
    q = robot.get_qpos()
    if q.dim() == 1:
        q = q.unsqueeze(0)
    return q[:, :arm_dim]


def build_standin_joint_traj(env, n_envs: int, arm_dim: int = 7, act_dim: int = 8) -> torch.Tensor:
    """*** NOT THE PAPER'S TEACHER -- A PLUMBING STAND-IN (joint space). ***

    (N,T,act_dim) joint-waypoint trajectory anchored at the robot's CURRENT arm
    qpos, so `pd_joint_delta_pos` can be exercised without any IK backend.
    Waypoint 0 is exactly where the robot is now (dist == 0 => teacher active).
    """
    q = robot_qpos(env, arm_dim)
    n, dev, dt = q.shape[0], q.device, q.dtype
    T = 5
    prof = torch.tensor([0.0, 1.0, 1.6, 1.2, 0.4], device=dev, dtype=dt)          # (T,)
    sign = torch.tensor([1.0, -1.0, 1.0, -1.0, 1.0, 0.0, 0.0][:arm_dim],
                        device=dev, dtype=dt)                                     # (arm,)
    tau = torch.zeros(n, T, act_dim, device=dev, dtype=dt)
    tau[:, :, :arm_dim] = q[:, None, :] + 0.06 * prof[None, :, None] * sign[None, None, :]
    g = torch.tensor([1.0, 1.0, -1.0, -1.0, -1.0], device=dev, dtype=dt)         # (T,)
    tau[:, :, arm_dim:] = g[None, :, None]
    return tau


def load_traj_npz(path: str):
    """Stage-2 output contract:  tau (K,T,7) [x,y,z,qw,qx,qy,qz] in ROBOT BASE
    frame, optional `gripper` (K,T) in raw action range (-1 closed .. +1 open)."""
    z = np.load(path, allow_pickle=True)
    tau = z["tau"]
    gripper = z["gripper"] if "gripper" in z else None
    return tau, gripper


def write_metric_row(writer, row: dict):
    writer.writerow(row)


# --------------------------------------------------------------------------- #
# policy
# --------------------------------------------------------------------------- #
class Agent(nn.Module):
    """Identical structure to upstream ppo_fast.py Agent, with the MLP width
    exposed (the paper never specifies the network)."""

    def __init__(self, obs_dim: int, act_dim: int, actor_hidden=256, critic_hidden=256):
        super().__init__()

        def mlp(inp, hidden, out, out_std):
            return nn.Sequential(
                layer_init(nn.Linear(inp, hidden)), nn.Tanh(),
                layer_init(nn.Linear(hidden, hidden)), nn.Tanh(),
                layer_init(nn.Linear(hidden, hidden)), nn.Tanh(),
                layer_init(nn.Linear(hidden, out), std=out_std),
            )

        self.critic = mlp(obs_dim, critic_hidden, 1, 1.0)
        self.actor_mean = mlp(obs_dim, actor_hidden, act_dim, 0.01)
        # state-independent log-std, exactly as upstream
        self.actor_logstd = nn.Parameter(torch.zeros(1, act_dim))

    def get_value(self, x):
        return self.critic(x)

    def get_action_and_value(self, x, action=None, deterministic=False):
        mean = self.actor_mean(x)
        logstd = self.actor_logstd.expand_as(mean)
        std = logstd.exp()
        probs = Normal(mean, std)
        if action is None:
            action = mean if deterministic else probs.sample()
        return action, probs.log_prob(action).sum(1), probs.entropy().sum(1), self.critic(x)

    def distribution(self, x):
        mean = self.actor_mean(x)
        std = self.actor_logstd.expand_as(mean).exp()
        return mean, std


# --------------------------------------------------------------------------- #
# rollout
# --------------------------------------------------------------------------- #
def gae_advantages(rewards, values, dones, next_value, next_done, gamma, gae_lambda):
    """rewards/values/dones: (T, N).  Standard GAE-lambda.
    (Upstream additionally bootstraps from `final_observation` for envs that
    terminated; that correction is dropped here -- see README 'deviations'.)"""
    T = rewards.shape[0]
    # rewards/values live on `device`; dones come straight from the env, which with
    # sim_backend="cpu" hands back CPU tensors -> align devices here.
    dones = dones.to(rewards.device)
    next_done = next_done.to(rewards.device)
    next_value = next_value.to(rewards.device)
    adv = torch.zeros_like(rewards)
    last = torch.zeros_like(values[0])
    for t in reversed(range(T)):
        if t == T - 1:
            nextnonterminal = (~next_done).float()
            nextvalues = next_value
        else:
            nextnonterminal = (~dones[t + 1]).float()
            nextvalues = values[t + 1]
        delta = rewards[t] + gamma * nextvalues * nextnonterminal - values[t]
        adv[t] = last = delta + gamma * gae_lambda * nextnonterminal * last
    return adv, adv + values


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(args: Args):
    # ---- seeding -------------------------------------------------------- #
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.backends.cudnn.deterministic = True

    device = torch.device("cuda" if (args.cuda and torch.cuda.is_available()) else "cpu")
    if args.sim_backend == "gpu" and device.type != "cuda":
        raise SystemExit("--sim-backend gpu needs CUDA; native Linux/NVIDIA only.")

    run_name = f"{args.env_id}__{args.exp_name}__{args.tag + '__' if args.tag else ''}{args.seed}__{int(time.time())}"
    run_path = os.path.join(args.run_dir, run_name)
    os.makedirs(run_path, exist_ok=True)
    print(f"[info] run      : {run_path}")
    print(f"[info] device   : {device}  sim_backend={args.sim_backend}")
    print(f"[info] mani_skill fork: {os.path.dirname(mani_skill.__file__)}")

    # ---- envs ----------------------------------------------------------- #
    # a joint-space teacher cannot drive an ee-pose action space and vice versa;
    # pd_ee_delta_pose additionally needs an IK backend (Linux-only fast_kinematics
    # or the `pinocchio` package -- see teacher.py), so joint mode is the only
    # option on a Windows CPU-sim smoke test.
    teacher_mode = "joint" if args.teacher == "joint" else "ee_pose"
    if args.control_mode is None:
        args.control_mode = "pd_joint_delta_pos" if teacher_mode == "joint" else "pd_ee_delta_pose"
    print(f"[info] teacher_mode={teacher_mode}  control_mode={args.control_mode}")

    env_kwargs = dict(obs_mode=args.obs_mode, sim_backend=args.sim_backend)
    if args.control_mode is not None:
        env_kwargs["control_mode"] = args.control_mode
    if args.render_mode is not None:
        env_kwargs["render_mode"] = args.render_mode

    envs = gym.make(
        args.env_id, num_envs=args.num_envs,
        reconfiguration_freq=args.reconfiguration_freq, **env_kwargs,
    )
    eval_envs = gym.make(
        args.env_id, num_envs=args.num_eval_envs,
        reconfiguration_freq=1, **env_kwargs,
    )
    # NOTE: in this fork BaseEnv.single_action_space is ALREADY a flat Box for
    # pd_joint_delta_pos, and FlattenActionSpaceWrapper.action() calls .items() on
    # it -> AttributeError.  So wrap only when the space really is a Dict.
    if isinstance(envs.action_space, spaces.Dict):
        envs = FlattenActionSpaceWrapper(envs)
        eval_envs = FlattenActionSpaceWrapper(eval_envs)
        print("[info] wrapped action space with FlattenActionSpaceWrapper")

    envs = ManiSkillVectorEnv(envs, args.num_envs,
                              ignore_terminations=not args.partial_reset, record_metrics=True)
    eval_envs = ManiSkillVectorEnv(eval_envs, args.num_eval_envs,
                                   ignore_terminations=not args.eval_partial_reset, record_metrics=True)

    obs, _ = envs.reset(seed=args.seed)
    obs = obs_to_vec(obs).to(device)
    obs_dim = obs.shape[1]
    act_dim = int(np.prod(envs.single_action_space.shape))
    print(f"[info] obs_dim={obs_dim}  act_dim={act_dim}  single_action_space={envs.single_action_space}")

    # ---- teacher -------------------------------------------------------- #
    pos_scale, rot_scale = read_align_scales(envs)
    print(f"[info] controller scales: pos_scale={pos_scale} rot_scale={rot_scale}")

    align_cfg = AlignConfig(
        mode=teacher_mode,
        eps=args.align_eps, lookahead=args.align_lookahead, monotone=args.align_monotone,
        pos_scale=pos_scale, rot_scale=rot_scale,
        joint_scale=args.joint_scale, arm_dim=args.arm_dim, sigma_t=args.sigma_t,
        track_rot=args.align_track_rot,
        dim_weight=(1.0,) * act_dim if teacher_mode == "joint" else (
            (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0) if args.align_track_rot
            else (1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0)),
    )
    teacher = None
    if args.kl_enable and args.teacher != "none":
        teacher = TrajectoryTeacher(align_cfg, n_envs=args.num_envs, act_dim=act_dim, device=device)
        if args.teacher == "traj":
            assert args.teacher_path, "--teacher traj needs --teacher-path"
            tau, gripper = load_traj_npz(args.teacher_path)
            teacher.set_trajectory(tau, gripper)
            print(f"[info] loaded teacher trajectory {args.teacher_path}  tau={np.shape(tau)}")
        elif args.teacher == "joint":
            tau = build_standin_joint_traj(envs, args.num_envs, args.arm_dim, act_dim)
            teacher.set_trajectory(tau)
            print("[info] teacher = joint standin (*** plumbing stand-in, NOT the paper's RRT* teacher ***)")
        else:
            tau, gripper = build_standin_traj(envs, args.num_envs)
            teacher.set_trajectory(tau, gripper)
            print("[info] teacher = standin (*** plumbing stand-in, NOT the paper's RRT* teacher ***)")
        teacher.reset()

    def teacher_state():
        return robot_qpos(envs, args.arm_dim) if teacher_mode == "joint" else tcp_pose_base(envs)

    # ---- agent / optim --------------------------------------------------- #
    agent = Agent(obs_dim, act_dim, args.actor_hidden, args.critic_hidden).to(device)
    print(f"[info] policy params: {sum(p.numel() for p in agent.parameters())}")
    optimizer = optim.Adam(agent.parameters(), lr=args.learning_rate, eps=1e-5)

    # ---- buffers --------------------------------------------------------- #
    T, N = args.num_steps, args.num_envs
    obs_buf = torch.zeros((T, N, obs_dim), device=device)
    act_buf = torch.zeros((T, N, act_dim), device=device)
    logp_buf = torch.zeros((T, N), device=device)
    rew_buf = torch.zeros((T, N), device=device)
    done_buf = torch.zeros((T, N), device=device)
    val_buf = torch.zeros((T, N), device=device)
    teach_buf = torch.zeros((T, N, act_dim), device=device)
    tmask_buf = torch.zeros((T, N), dtype=torch.bool, device=device)

    n_updates = max(1, args.total_timesteps // (T * N))
    batch_size = min(args.batch_size, T * N)
    n_minibatches = max(1, (T * N) // batch_size)
    print(f"[info] updates={n_updates}  batch_size={batch_size}  minibatches={n_minibatches}"
          f"  (paper: 312 iters x 128 envs x 50 steps = {312*128*50} steps)")

    csv_path = os.path.join(run_path, "metrics.csv")
    csv_f = open(csv_path, "w", newline="")
    csv_w = csv.writer(csv_f)
    csv_w.writerow(CSV_COLS)

    next_obs, next_done = obs, torch.zeros(N, device=device)
    start_time = time.time()
    global_step = 0
    lam = args.lam if args.lam is not None else 1.0
    ep_rew = deque(maxlen=100)

    for iteration in range(1, n_updates + 1):
        if args.anneal_lr:
            frac = 1.0 - (iteration - 1.0) / n_updates
            optimizer.param_groups[0]["lr"] = frac * args.learning_rate

        # ---------------- rollout ---------------- #
        rollout_t0 = time.time()
        for step in range(T):
            global_step += N
            obs_buf[step] = next_obs
            done_buf[step] = next_done

            if teacher is not None:
                with torch.no_grad():
                    ta, tm, _ = teacher.action(teacher_state())
                teach_buf[step] = ta
                tmask_buf[step] = tm

            with torch.no_grad():
                action, logp, _, value = agent.get_action_and_value(next_obs)
            act_buf[step] = action
            logp_buf[step] = logp
            val_buf[step] = value.flatten()

            next_obs, reward, term, trunc, info = envs.step(action)
            next_obs = obs_to_vec(next_obs).to(device)
            rew_buf[step] = reward.flatten()
            done = (term | trunc).flatten()
            next_done = done.float()
            ep_rew.extend(reward[term | trunc].flatten().cpu().numpy().tolist())

            # Re-anchor the scripted STAND-IN teacher.  A real RRT* trajectory is
            # fixed for the episode; the stand-in is re-anchored periodically so the
            # KL path stays exercised during a short plumbing run (README deviations).
            if teacher is not None and args.teacher in ("joint", "standin"):
                reanchor = bool(done.any()) or (
                    args.standin_reanchor_every > 0
                    and (step + 1) % args.standin_reanchor_every == 0
                )
                if reanchor:
                    if args.teacher == "joint":
                        teacher.tau = build_standin_joint_traj(
                            envs, N, args.arm_dim, act_dim).to(teacher.device)
                        teacher.gripper = None
                    else:
                        _t, _g = build_standin_traj(envs, N)
                        teacher.tau = _t.to(teacher.device)
                        teacher.gripper = None if _g is None else _g.to(teacher.device)
                if bool(done.any()):
                    teacher.reset(mask=done)

        rollout_time = time.time() - rollout_t0

        with torch.no_grad():
            next_value = agent.get_value(next_obs).flatten()
            adv, ret = gae_advantages(rew_buf, val_buf, done_buf.bool(), next_value,
                                      next_done.bool(), args.gamma, args.gae_lambda)
            adv = (adv - adv.mean()) / (adv.std() + 1e-8) if args.norm_adv else adv

        b_obs = obs_buf.reshape(-1, obs_dim)
        b_act = act_buf.reshape(-1, act_dim)
        b_logp = logp_buf.reshape(-1)
        b_adv = adv.reshape(-1)
        b_ret = ret.reshape(-1)
        b_val = val_buf.reshape(-1)
        b_teach = teach_buf.reshape(-1, act_dim)
        b_tmask = tmask_buf.reshape(-1)
        b_inds = np.arange(T * N)

        # ---------------- lambda (Eq. 9) ---------------- #
        l_rl = l_kl = float("nan")
        if args.kl_enable:
            if args.lam is not None:
                lam = float(args.lam)
            elif iteration <= args.lam_warmup_iters and (iteration - 1) % args.lam_recompute_every == 0:
                with torch.no_grad():
                    m, s = agent.distribution(b_obs)
                    _, newlogp, _, _ = agent.get_action_and_value(b_obs, b_act)
                    # Eq. (9) is a ratio of LOSS MAGNITUDES, so both terms must be
                    # positive; -E[adv*logpi] is signed and is mildly negative early
                    # in training, hence the abs() [OURS A6].
                    l_rl = abs(float(-(b_adv * newlogp).mean()))
                    if bool(b_tmask.any()):
                        w = align_cfg.weight_tensor(act_dim, device, m.dtype)
                        l_kl = float(gaussian_kl(m, s, b_teach, b_tmask, args.sigma_t, w,
                                                 args.kl_normalize_by_masked))
                if l_kl > 1e-8 and l_rl > 1e-8:
                    lam = float(10 ** (math.log10(l_rl) - math.log10(l_kl)))
                    lam = float(np.clip(lam, args.lam_min, args.lam_max))
                print(f"  [lambda] iter={iteration} L_RL={l_rl:.6g} L_KL={l_kl:.6g} -> lambda={lam:.6g}")

        # ---------------- update ---------------- #
        upd_t0 = time.time()
        kl_value = torch.tensor(0.0)
        for epoch in range(args.update_epochs):
            np.random.shuffle(b_inds)
            for start in range(0, T * N, batch_size):
                mb = b_inds[start:start + batch_size]
                _, newlogp, entropy, newvalue = agent.get_action_and_value(b_obs[mb], b_act[mb])
                logratio = newlogp - b_logp[mb]
                ratio = logratio.exp()
                with torch.no_grad():
                    approx_kl = ((ratio - 1) - logratio).mean()
                    clipfrac = ((ratio - 1.0).abs() > args.clip_coef).float().mean()

                mb_adv = b_adv[mb]
                pg_loss = torch.max(-mb_adv * ratio,
                                    -mb_adv * torch.clamp(ratio, 1 - args.clip_coef, 1 + args.clip_coef)).mean()
                newvalue = newvalue.view(-1)
                if args.clip_vloss:
                    v_unclipped = (newvalue - b_ret[mb]) ** 2
                    v_clipped = b_val[mb] + torch.clamp(newvalue - b_val[mb], -args.clip_coef, args.clip_coef)
                    v_loss = 0.5 * torch.max(v_unclipped, (v_clipped - b_ret[mb]) ** 2).mean()
                else:
                    v_loss = 0.5 * ((newvalue - b_ret[mb]) ** 2).mean()
                entropy_loss = entropy.mean()

                loss = pg_loss - args.ent_coef * entropy_loss + args.vf_coef * v_loss

                if args.kl_enable and bool(b_tmask[mb].any()):
                    m, s = agent.distribution(b_obs[mb])
                    w = align_cfg.weight_tensor(act_dim, device, m.dtype)
                    kl_value = gaussian_kl(m, s, b_teach[mb], b_tmask[mb], args.sigma_t, w,
                                           args.kl_normalize_by_masked)
                    loss = loss + lam * kl_value

                optimizer.zero_grad()
                loss.backward()
                gn = nn.utils.clip_grad_norm_(agent.parameters(), args.max_grad_norm)
                optimizer.step()

            if args.target_kl is not None and approx_kl > args.target_kl:
                break
        update_time = time.time() - upd_t0

        # ---------------- eval ---------------- #
        eval_success = float("nan")
        if args.eval_freq > 0 and iteration % args.eval_freq == 0:
            eval_success = evaluate(agent, eval_envs, args.num_eval_steps, device, args.eval_seed)

        sps = int(global_step / (time.time() - start_time))
        cov = float(tmask_buf.float().mean()) if args.kl_enable else float("nan")
        bcov = float(b_tmask.float().mean()) if args.kl_enable else float("nan")
        train_rew = float(np.mean(ep_rew)) if ep_rew else float("nan")

        row = dict(iter=iteration, global_step=global_step, l_rl=l_rl, l_kl=l_kl, lam=lam,
                   kl_value=float(kl_value), pg_loss=float(pg_loss), v_loss=float(v_loss),
                   entropy=float(entropy_loss), clipfrac=float(clipfrac), approx_kl=float(approx_kl),
                   grad_norm=float(gn), teacher_coverage=cov, train_reward=train_rew,
                   eval_success=eval_success, sps=sps)
        csv_w.writerow([row[k] for k in CSV_COLS])
        csv_f.flush()

        if iteration % args.log_every == 0:
            rew_s = "     nan" if train_rew != train_rew else f"{train_rew:8.3f}"
            ev_s = "  none" if eval_success != eval_success else f"{eval_success:.3f}"
            print(f"it {iteration:4d}/{n_updates}  step {global_step:8d}  "
                  f"rew {rew_s}  pg {row['pg_loss']:+.4f}  v {row['v_loss']:.4f}  "
                  f"kl {row['kl_value']:.5f}  lam {lam:.4g}  "
                  f"cover {cov:.3f}/{bcov:.3f}  evalS {ev_s}"
                  f"  | rollout {rollout_time:.2f}s upd {update_time:.2f}s  {sps} SPS")

    # ---- done ---------------- #
    if args.save_model:
        p = os.path.join(run_path, "final_ckpt.pt")
        torch.save(agent.state_dict(), p)
        print(f"[info] saved {p}")
    csv_f.close()
    envs.close()
    eval_envs.close()


@torch.no_grad()
def evaluate(agent, eval_envs, num_eval_steps, device, seed=None) -> float:
    obs, _ = eval_envs.reset(seed=seed)
    obs = obs_to_vec(obs).to(device)
    succ = torch.zeros(eval_envs.num_envs, dtype=torch.bool, device=device)
    for _ in range(num_eval_steps):
        action, _, _, _ = agent.get_action_and_value(obs, deterministic=True)
        obs, _, _, _, info = eval_envs.step(action)
        obs = obs_to_vec(obs).to(device)
        s = extract(info, "success")
        if s is not None:
            succ |= s.to(device).bool().flatten()
    return float(succ.float().mean())


def extract(info, key):
    """ManiSkill vector envs put per-env scalars either at the top level or
    nested under `final_info` / `episode`."""
    if not isinstance(info, dict):
        return None
    if key in info:
        return info[key]
    for nest in ("final_info", "episode"):
        v = info.get(nest)
        if isinstance(v, dict) and key in v:
            return v[key]
    return None


if __name__ == "__main__":
    main(tyro.cli(Args))
