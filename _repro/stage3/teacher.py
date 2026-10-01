"""
PCK-RL stage 3 -- RRT* teacher -> PPO student alignment + KL loss.

The paper (Sec. III-C) gives only a concept figure (Fig. 3) for this step, so
every choice marked [OURS] below is OUR engineering decision and must be
reported as such (TodoList discipline #1).

Frames
------
Everything here lives in the ROBOT BASE frame, which is exactly the frame the
delta-pose controller works in::

    mani_skill/agents/controllers/pd_ee_pose.py:62
        ee_pose_at_base = articulation.pose.inv() * ee_link.pose

so a trajectory ``tau`` is ``(T, 7) = [x, y, z, qw, qx, qy, qz]`` in the base
frame, and the teacher action is a raw (un-normalised) action of the
environment action space.

Action space convention (``pd_ee_delta_pose``, 7 dims)
------------------------------------------------------
``mani_skill/agents/controllers/pd_ee_pose.py:197-238`` plus
``mani_skill/agents/robots/panda/panda.py:113-118`` (``pos_* = rot_* = -+0.1``)::

    p_target = p_cur + 0.1 * a[:3]                              # clip_and_scale_action
    q_target = quat_from_euler_xyz(0.1 * a[3:6]) * q_cur        # |a[3:6]| clipped to 1

inverting it gives::

    a[:3]  = (p_target - p_cur) / 0.1
    a[3:6] = euler_XYZ(q_target * q_cur^-1) / 0.1,  clipped to |a[3:6]| <= 1
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import torch

from mani_skill.utils.geometry.rotation_conversions import (
    matrix_to_euler_angles,
    quaternion_invert,
    quaternion_multiply,
    quaternion_to_matrix,
)

# --------------------------------------------------------------------------- #
# [OURS] alignment hyper-parameters -- the paper gives NONE of these.
# --------------------------------------------------------------------------- #
@dataclass
class AlignConfig:
    mode: str = "ee_pose"
    """[OURS A7] which action space the teacher emits into.

    ``"ee_pose"`` -- tau is (K,T,7) = [x,y,z,qw,qx,qy,qz] in the robot base frame and
    the emitted action is a 6-dim ``pd_ee_delta_pose`` delta (plus gripper). Needs a
    controller with a CPU/GPU IK solver: ``fast_kinematics`` (Linux-only) or the
    ``pinocchio`` package. NOT available in the Windows venv.

    ``"joint"`` -- tau is (K,T,A) = joint-space waypoints ``q_ref`` (panda: 7 arm
    joints + 1 gripper = 8). The emitted action is a ``pd_joint_delta_pos`` delta
    ``clip((q_ref - q)/joint_scale, -1, 1)``, which needs NO IK at all, so it also
    runs on Windows/CPU.  Alignment distance uses the first 3 joints as a
    position-like proxy -- coarse but adequate for a plumbing smoke test.
    """

    eps: float = 0.05
    """[OURS A3] distance gate [m]: teacher is silent unless ||p_tcp - p_tau[j]|| < eps."""

    lookahead: int = 1
    """[OURS A4] aim at tau[j + lookahead] instead of tau[j] (turns a point cloud of
    waypoints into a direction; lookahead=0 would give a zero target and the
    teacher would say nothing)."""

    monotone: bool = True
    """[OURS A2] enforce j_t >= j_{t-1} inside an episode (anti phase-collapse)."""

    pos_scale: float = 0.1
    """[m] the controller's pos_upper (panda.py:116). Read from the env at runtime
    when the trainer can find it; this is only the fallback."""

    rot_scale: float = 0.1
    """[rad] the controller's rot_lower (panda.py:117)."""

    joint_scale: float = 0.1
    """[rad] the ``pd_joint_delta_pos`` joint delta limit (mode='joint')."""

    arm_dim: int = 7
    """number of arm joints (mode='joint'); the remaining action dims are gripper."""

    sigma_t: float = 0.05
    """[OURS A5] teacher action std. THE constraint-stiffness knob the paper never
    specifies. Small => hard constraint, large => soft. This is the single number
    to sweep if the student is either locked to the teacher or ignores it."""

    dim_weight: tuple = (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    """[OURS A5b] per-dimension weight on the KL term. Set the 3 rotation dims to 0
    when the teacher trajectory carries no meaningful orientation (e.g. the
    Windows stand-in teacher)."""

    track_rot: bool = True
    """If False the teacher always emits 0 on the 3 rotation dims (and they should
    be zero-weighted in dim_weight)."""

    clip_action: bool = True
    """Clip the emitted action exactly the way the controller does."""

    def weight_tensor(self, n_act: int, device, dtype) -> torch.Tensor:
        w = torch.as_tensor(self.dim_weight, device=device, dtype=dtype)
        w = w[:n_act]
        if w.numel() < n_act:  # pad (e.g. a 4-dim pd_ee_delta_pos action space)
            w = torch.cat([w, torch.zeros(n_act - w.numel(), device=device, dtype=dtype)])
        return w


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
def pose_delta_action(
    cur_pose: torch.Tensor,
    tgt_pose: torch.Tensor,
    pos_scale: float = 0.1,
    rot_scale: float = 0.1,
    track_rot: bool = True,
) -> torch.Tensor:
    """(N,7)x(N,7) in base frame -> (N,6) raw action dims (no gripper)."""
    n = cur_pose.shape[0]
    out = torch.zeros(n, 6, device=cur_pose.device, dtype=cur_pose.dtype)

    out[:, :3] = (tgt_pose[:, :3] - cur_pose[:, :3]) / pos_scale

    if track_rot:
        # controller composes q_target = delta_q * q_cur, so delta_q = q_tgt * q_cur^-1
        q_delta = quaternion_multiply(tgt_pose[:, 3:7], quaternion_invert(cur_pose[:, 3:7]))
        rot_mat = quaternion_to_matrix(q_delta)
        eul = matrix_to_euler_angles(rot_mat, "XYZ")
        out[:, 3:6] = eul / rot_scale
    return out


def _clip_like_controller(action: torch.Tensor) -> torch.Tensor:
    """Mirror pd_ee_pose.py:197-210 -- pos clipped to [-1,1], rot clipped by norm."""
    action = action.clone()
    action[:, :3] = torch.clip(action[:, :3], -1, 1)
    rot = action[:, 3:6]
    norm = torch.linalg.norm(rot, dim=1, keepdim=True)
    action[:, 3:6] = torch.where(norm > 1, rot / norm.clamp(min=1e-8), rot)
    # anything beyond 6 dims (gripper) is passed through
    return action


# --------------------------------------------------------------------------- #
# the teacher
# --------------------------------------------------------------------------- #
class TrajectoryTeacher:
    """Batched nearest-neighbour teacher over one reference trajectory per env.

    ``tau`` is ``(K, T, 7)`` in the robot base frame; env ``i`` follows
    ``tau[traj_id[i]]``.  ``gripper`` is ``(K, T)`` in the raw gripper action
    range (typically -1 closed .. +1 open) and is emitted verbatim.

    The teacher is *stateful* (it remembers the monotone pointer j), so
    :meth:`reset` MUST be called on every env reset.
    """

    def __init__(
        self,
        cfg: Optional[AlignConfig] = None,
        n_envs: int = 1,
        act_dim: int = 7,
        device="cpu",
        dtype=torch.float32,
    ):
        self.cfg = cfg or AlignConfig()
        self.n_envs = n_envs
        self.act_dim = act_dim
        self.device = device
        self.dtype = dtype

        self.tau: Optional[torch.Tensor] = None      # (K, T, 7)
        self.gripper: Optional[torch.Tensor] = None  # (K, T)
        self.traj_id = torch.zeros(n_envs, dtype=torch.long, device=device)
        self.j = torch.zeros(n_envs, dtype=torch.long, device=device)

    # -- trajectory management -------------------------------------------------
    def set_trajectory(self, tau, gripper=None, traj_id=None):
        """tau: (T,7) or (K,T,7).  gripper: (K,T) or (T,) or None."""
        tau = torch.as_tensor(np.asarray(tau), device=self.device, dtype=self.dtype)
        if tau.dim() == 2:
            tau = tau.unsqueeze(0)
        assert tau.dim() == 3, f"bad tau shape {tuple(tau.shape)}"
        if self.cfg.mode == "ee_pose":
            assert tau.shape[-1] == 7, f"ee_pose tau must be (K,T,7), got {tuple(tau.shape)}"
        else:
            assert tau.shape[-1] == self.act_dim, (
                f"joint tau must be (K,T,{self.act_dim}), got {tuple(tau.shape)}"
            )
        self.tau = tau

        if gripper is None:
            self.gripper = None
        else:
            g = torch.as_tensor(np.asarray(gripper), device=self.device, dtype=self.dtype)
            if g.dim() == 1:
                g = g.unsqueeze(0)
            self.gripper = g

        if traj_id is not None:
            self.traj_id = torch.as_tensor(np.asarray(traj_id), device=self.device).long()
        elif tau.shape[0] == self.n_envs:
            self.traj_id = torch.arange(self.n_envs, device=self.device)

        self.j = torch.zeros(self.n_envs, dtype=torch.long, device=self.device)

    def reset(self, mask: Optional[torch.Tensor] = None):
        """Zero the progress pointer.  ``mask`` (bool (N,)) selects which envs reset."""
        if mask is None:
            self.j.zero_()
        else:
            self.j = torch.where(mask.to(self.device), torch.zeros_like(self.j), self.j)

    # -- query -----------------------------------------------------------------
    @torch.no_grad()
    def action(self, state):
        """``state``: (N,7) base-frame TCP pose when mode='ee_pose', else (N,act_dim)
        joint positions when mode='joint'.

        Returns ``(action (N,A), mask (N,), dist (N,))``.  ``action`` is a raw env
        action; ``mask`` is True where the teacher is active (KL is applied).
        """
        assert self.tau is not None, "call set_trajectory() first"
        dev = self.device
        state = torch.as_tensor(state, device=dev, dtype=self.dtype)
        n = state.shape[0]
        tau = self.tau[self.traj_id[:n]]           # (N, T, D)
        T = tau.shape[1]

        # nearest waypoint in the first 3 dims (xyz / first 3 joints)
        d = torch.linalg.norm(tau[:, :, :3] - state[:, None, :3], dim=2)  # (N,T)
        j_nn = torch.argmin(d, dim=1)

        j = torch.maximum(j_nn, self.j[:n]) if self.cfg.monotone else j_nn
        j = torch.clamp(j, 0, T - 1)
        self.j[:n] = j

        dist = d[torch.arange(n, device=dev), j]

        # aim lookahead waypoints ahead (lookahead=0 would be a zero target)
        j_tgt = torch.clamp(j + self.cfg.lookahead, 0, T - 1)
        tgt = tau[torch.arange(n, device=dev), j_tgt]

        action = torch.zeros(n, self.act_dim, device=dev, dtype=self.dtype)

        if self.cfg.mode == "ee_pose":
            action[:, :6] = pose_delta_action(
                state, tgt, self.cfg.pos_scale, self.cfg.rot_scale, self.cfg.track_rot
            )
            if self.gripper is not None:
                g = self.gripper[self.traj_id[:n]]
                action[:, -1] = g[torch.arange(n, device=dev), j]
            if self.cfg.clip_action:
                action = _clip_like_controller(action)
        else:
            arm = min(self.cfg.arm_dim, self.act_dim)
            action[:, :arm] = torch.clip(
                (tgt[:, :arm] - state[:, :arm]) / max(self.cfg.joint_scale, 1e-8), -1, 1
            )
            if tgt.shape[-1] > arm:
                action[:, arm:] = tgt[:, arm:]
            if self.cfg.clip_action:
                action = torch.clip(action, -1, 1)

        mask = dist < self.cfg.eps
        return action, mask, dist


# --------------------------------------------------------------------------- #
# losses
# --------------------------------------------------------------------------- #
def gaussian_kl(
    mu_s: torch.Tensor,
    sigma_s: torch.Tensor,
    a_t: torch.Tensor,
    mask: torch.Tensor,
    sigma_t: float,
    weight: Optional[torch.Tensor] = None,
    normalize_by_masked: bool = True,
    eps: float = 1e-8,
) -> torch.Tensor:
    """[OURS A5]  KL( N(a_t, sigma_t^2 I) || N(mu_s, sigma_s^2 I) )  over masked samples.

    = sum_d [ log(sigma_s/sigma_t) + (sigma_t^2 + (a_t - mu_s)^2) / (2 sigma_s^2) - 1/2 ]

    With ``sigma_t == sigma_s`` the first and last terms cancel and this is exactly
    the sigma_s-normalised MSE of the paper's "narrow Gaussian teacher" reading.
    """
    m = mask.unsqueeze(-1).to(mu_s.dtype)                       # (B,1)
    diff2 = (a_t - mu_s) ** 2
    kl = (
        torch.log(sigma_s.clamp(min=eps)) - math.log(max(sigma_t, eps))
        + (sigma_t ** 2 + diff2) / (2.0 * sigma_s.clamp(min=eps) ** 2)
        - 0.5
    )
    if weight is not None:
        kl = kl * weight.unsqueeze(0)
    kl = kl.sum(dim=-1) * m.squeeze(-1)

    denom = m.sum() if normalize_by_masked else m.new_tensor(float(m.shape[0]))
    return kl.sum() / denom.clamp(min=1.0)


if __name__ == "__main__":  # tiny self-test: math sanity, no simulator needed
    torch.manual_seed(0)
    cfg = AlignConfig(eps=10.0, track_rot=True)
    t = TrajectoryTeacher(cfg, n_envs=2, act_dim=7)
    # a straight line in +x with identity rotation
    tau = torch.zeros(5, 7)
    tau[:, 0] = torch.linspace(0.0, 0.4, 5)
    tau[:, 3] = 1.0
    t.set_trajectory(tau, gripper=torch.tensor([1.0, 1.0, -1.0, -1.0, -1.0]))
    cur = torch.zeros(2, 7)
    cur[:, 3] = 1.0
    a, m, dist = t.action(cur)
    print("action", a)
    print("mask", m, "dist", dist)
    # teacher wants +x, so a[:,0] must be positive and ~ 0.1/0.1 = 1
    assert a[0, 0] > 0.9, a[0, 0]
    print("pose_delta_action OK")

    # KL sanity: identical distributions -> 0 when sigma_t == sigma_s
    mu = torch.zeros(4, 7)
    s = torch.full((4, 7), 0.2)
    at = torch.randn(4, 7)
    k = gaussian_kl(mu, s, at, torch.ones(4, dtype=torch.bool), 0.2)
    print("KL(mu=0,s=0.2 || a_t~N(0,1), sigma_t=0.2) =", float(k))

    # joint mode: no IK, no quaternion -- pure q_ref - q
    jcfg = AlignConfig(mode="joint", eps=10.0, lookahead=1,
                       dim_weight=(1.0,) * 8, joint_scale=0.1)
    jt = TrajectoryTeacher(jcfg, n_envs=2, act_dim=8)
    q_tau = torch.zeros(6, 8)
    q_tau[:, 0] = torch.linspace(0.0, 0.5, 6)   # joint 0 sweeps 0 -> 0.5 rad
    q_tau[:, -1] = 1.0                          # gripper open
    jt.set_trajectory(q_tau)
    q0 = torch.zeros(2, 8)
    ja, jm, jd = jt.action(q0)
    print("joint action", ja)
    assert ja.shape == (2, 8), ja.shape
    assert ja[0, 0] > 0.9, ja[0, 0]             # (0.1 - 0.0)/0.1 = 1.0
    assert abs(float(ja[0, -1]) - 1.0) < 1e-6, ja[0, -1]
    print("joint mode OK")
