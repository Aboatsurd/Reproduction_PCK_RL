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
    """[OURS A2] (legacy alias) enforce j_t >= j_{t-1} inside an episode.

    Kept only as the fallback for ``align=""``; ``align`` supersedes it."""

    # ---- [OURS A8..A11] time alignment ----------------------------------- #
    align: str = ""
    """[OURS A8] how student step t is matched to a trajectory index j.

    ``""``      -- legacy: ``"mono"`` if ``monotone`` else ``"nn"``.
    ``"index"`` -- j = step counter. The author's ``follow_path`` semantics
                   (open loop, one waypoint per env step). Breaks as soon as the
                   student's tempo differs from the planner's.
    ``"nn"``    -- j = argmin_i ||s_t - tau_i||. Phase can collapse backwards and
                   a self-intersecting path is ambiguous.
    ``"mono"``  -- max(nn, j_{t-1}). Kills the backwards collapse, but still lets
                   j jump arbitrarily far forward, and locks onto the wrong branch
                   irreversibly where the path crosses itself.
    ``"window"``-- **default / recommended**. argmin over the bounded window
                   ``[j_{t-1}, j_{t-1} + window]``. Monotone (no collapse), rate
                   limited (no runaway jump), density independent (argmin picks the
                   genuinely closest waypoint, so it works for 1 mm and 10 cm
                   spacing alike), and never globally ambiguous (it cannot see the
                   crossing branch).

    Why not DTW: DTW is *non-causal* -- it needs the whole student trajectory, so it
    cannot emit an action online. Use it offline as a diagnostic only.
    """

    window: int = 8
    """[OURS A8] forward window (in waypoints) for ``align="window"``. Too small =>
    j lags when the student sprints; too large => a wide lateral excursion can pick a
    wrong-but-nearby forward waypoint. 8 waypoints ~ a few cm of path."""

    lookahead_dist: float = 0.05
    """[OURS A9] pure-pursuit target distance [m] ALONG THE PATH.

    This is the fix for a silent failure: with ``lookahead=1`` the teacher aims one
    *index* ahead, so on a densely sampled RRT* trajectory (spacing ~1 cm) it asks
    for ~0.1 of an action -- i.e. the teacher is present but says nothing useful.
    Aiming a fixed ARC LENGTH ahead makes the guidance independent of how finely the
    planner sampled the path. Set to 0 to fall back to the integer ``lookahead``
    (the old behaviour); it then only differs when the spacing exceeds this value.
    """

    gate: str = "soft"
    """[OURS A10] how the per-sample KL weight is built from the tracking distance.

    ``"hard"`` -- w = 1[dist < eps]. If the student starts (or drifts) outside the
                  tube, EVERY weight is 0, the KL term is identically 0, and the
                  whole RRT*-RL stage silently does nothing while the losses still
                  go down because plain PPO is still working. Hard to notice.
    ``"soft"`` -- **default**. w = exp(-dist^2 / (2 gate_sigma^2)), never exactly 0,
                  so Eq. (7)'s KL term has a gradient from step 0. Far-away samples
                  decay to ~0 by themselves, so this does not pollute the signal.
    """

    gate_sigma: float = 0.05
    """[OURS A10] length scale [m] of the soft gate. ~the tube radius you would have
    used for ``eps``; sweep together with ``eps`` (TodoList 3.10)."""

    gripper_src: str = "j"
    """[OURS A11] which phase drives the gripper dimension.

    ``"j"``   -- the matched phase (default).
    ``"tgt"`` -- the pure-pursuit target phase (a bit early).
    ``"none"``-- never emit a gripper action (zero that dim AND zero its
                 ``dim_weight``); use when the grasp timing is being learned by RL.

    Rationale: a grasp is triggered by a *contact event*, not by a coordinate. Since
    ``j`` is now a bounded monotone phase estimate it is a far better clock than the
    raw nearest neighbour was, but this knob exists because mis-timed gripper
    commands are a known, concrete failure mode of NN-aligned teachers.
    """

    dist_dims: int = 3
    """[OURS] how many leading dims form the alignment metric (3 = xyz / first three
    joints). Rotation is deliberately excluded: near the goal the orientation swings
    fast and would dominate an otherwise positional match."""

    reanchor_on_reset: bool = True
    """[OURS A8b] on ``reset(state=...)`` snap j to the nearest waypoint instead of
    blindly 0. Safe because a fresh trajectory starts where the robot is; it matters
    when a trajectory is reused across episodes."""

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

    def __post_init__(self):
        if not self.align:  # legacy: keep the old --align-monotone flag meaningful
            self.align = "mono" if self.monotone else "nn"
        self.align = str(self.align).lower()
        if self.align not in ("index", "nn", "mono", "window"):
            raise ValueError(f"align must be one of index|nn|mono|window, got {self.align!r}")
        self.gate = str(self.gate).lower()
        if self.gate not in ("hard", "soft"):
            raise ValueError(f"gate must be hard|soft, got {self.gate!r}")
        self.gripper_src = str(self.gripper_src).lower()
        if self.gripper_src not in ("j", "tgt", "none"):
            raise ValueError(f"gripper_src must be j|tgt|none, got {self.gripper_src!r}")
        if self.window < 0:
            raise ValueError("window must be >= 0")
        if self.gate_sigma <= 0:
            raise ValueError("gate_sigma must be > 0")

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
        self.arclen: Optional[torch.Tensor] = None   # (K, T) cumulative path length
        self.traj_id = torch.zeros(n_envs, dtype=torch.long, device=device)
        self.j = torch.zeros(n_envs, dtype=torch.long, device=device)
        self.step_count = torch.zeros(n_envs, dtype=torch.long, device=device)

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

        self._rebuild_arclen()
        self.j = torch.zeros(self.n_envs, dtype=torch.long, device=self.device)
        self.step_count = torch.zeros(self.n_envs, dtype=torch.long, device=self.device)

    def _rebuild_arclen(self):
        """Cumulative arc length (K,T) of the alignment metric, used by the
        pure-pursuit lookahead so the target distance is in metres, not indices."""
        if self.tau is None:
            self.arclen = None
            return
        dd = min(int(self.cfg.dist_dims), self.tau.shape[-1])
        seg = torch.linalg.norm(self.tau[:, 1:, :dd] - self.tau[:, :-1, :dd], dim=-1)  # (K,T-1)
        zero = torch.zeros(seg.shape[0], 1, device=self.device, dtype=self.dtype)
        self.arclen = torch.cat([zero, torch.cumsum(seg, dim=1)], dim=1).contiguous()  # (K,T)

    def nearest_index(self, state) -> torch.Tensor:
        """(N,dist_dims) -> (N,) nearest waypoint index. Used to re-anchor on reset."""
        assert self.tau is not None, "call set_trajectory() first"
        state = torch.as_tensor(state, device=self.device, dtype=self.dtype)
        n = state.shape[0]
        tau = self.tau[self.traj_id[:n]]
        dd = min(int(self.cfg.dist_dims), tau.shape[-1])
        d = torch.linalg.norm(tau[:, :, :dd] - state[:, None, :dd], dim=2)
        return torch.argmin(d, dim=1)

    def reset(self, mask: Optional[torch.Tensor] = None, state=None):
        """Reset the progress pointer.  ``mask`` (bool (N,)) selects which envs reset.

        ``state`` (optional) is the *current* tracking state; with
        ``cfg.reanchor_on_reset`` it snaps j to the nearest waypoint instead of 0,
        which matters when a trajectory does not literally start at the robot pose.
        """
        n = self.n_envs
        j0 = torch.zeros(n, dtype=torch.long, device=self.device)
        if state is not None and self.cfg.reanchor_on_reset and self.tau is not None:
            j0 = self.nearest_index(state)[:n].to(self.device).long()
        if mask is None:
            self.j = j0.clone()
            self.step_count = torch.zeros(n, dtype=torch.long, device=self.device)
        else:
            m = mask.to(self.device)
            self.j = torch.where(m, j0, self.j)
            self.step_count = torch.where(
                m, torch.zeros_like(self.step_count), self.step_count)

    # -- query -----------------------------------------------------------------
    @torch.no_grad()
    def action(self, state):
        """``state``: (N,7) base-frame TCP pose when mode='ee_pose', else (N,act_dim)
        joint positions when mode='joint'.

        Returns ``(action (N,A), mask (N,), dist (N,))``.  ``action`` is a raw env
        action; ``mask`` is the **per-sample KL weight** -- ``1[dist<eps]`` for
        ``gate="hard"`` (backwards compatible bool) and ``exp(-d^2/2 sigma^2)`` in
        ``(0,1]`` for ``gate="soft"``.  ``dist`` is the tracking distance [m] at the
        matched phase, so a caller can always recover the hard hit-rate itself.
        """
        assert self.tau is not None, "call set_trajectory() first"
        dev = self.device
        cfg = self.cfg
        state = torch.as_tensor(state, device=dev, dtype=self.dtype)
        n = state.shape[0]
        tau = self.tau[self.traj_id[:n]]           # (N, T, D)
        T = tau.shape[1]
        idx_n = torch.arange(n, device=dev)

        # nearest waypoint in the first ``dist_dims`` dims (xyz / first 3 joints)
        dd = min(int(cfg.dist_dims), tau.shape[-1])
        d = torch.linalg.norm(tau[:, :, :dd] - state[:, None, :dd], dim=2)  # (N,T)
        j_nn = torch.argmin(d, dim=1)

        # ---- [OURS A8] time alignment ------------------------------------- #
        if cfg.align == "index":
            j = torch.clamp(self.step_count[:n], 0, T - 1)
        elif cfg.align == "nn":
            j = j_nn
        elif cfg.align == "mono":
            j = torch.maximum(j_nn, self.j[:n])
        else:  # "window": monotone AND rate limited
            lo = self.j[:n].clamp(max=T - 1)
            hi = (lo + max(int(cfg.window), 0)).clamp(max=T - 1)
            ar = torch.arange(T, device=dev).unsqueeze(0)
            in_win = (ar >= lo.unsqueeze(1)) & (ar <= hi.unsqueeze(1))
            d_win = torch.where(in_win, d, torch.full_like(d, float("inf")))
            j = d_win.argmin(dim=1)
        j = torch.clamp(j, 0, T - 1)
        self.j[:n] = j

        dist = d[idx_n, j]

        # ---- [OURS A9] pure-pursuit target -------------------------------- #
        # integer lookahead (legacy) ...
        j_tgt = torch.clamp(j + max(int(cfg.lookahead), 0), 0, T - 1)
        # ... then push it out to a fixed ARC LENGTH so a densely sampled RRT*
        # trajectory still yields a meaningful (non-vanishing) target.
        if cfg.lookahead_dist > 0 and self.arclen is not None:
            al = self.arclen[self.traj_id[:n]].contiguous()
            s_t = al[idx_n, j] + float(cfg.lookahead_dist)
            j_pp = torch.searchsorted(al, s_t.unsqueeze(1)).squeeze(1)
            j_tgt = torch.maximum(j_tgt, torch.clamp(j_pp, 0, T - 1))
        j_tgt = torch.clamp(j_tgt, 0, T - 1)
        tgt = tau[idx_n, j_tgt]

        action = torch.zeros(n, self.act_dim, device=dev, dtype=self.dtype)

        if cfg.mode == "ee_pose":
            action[:, :6] = pose_delta_action(
                state, tgt, cfg.pos_scale, cfg.rot_scale, cfg.track_rot
            )
            if self.gripper is not None and cfg.gripper_src != "none":
                gj = j_tgt if cfg.gripper_src == "tgt" else j
                action[:, -1] = self.gripper[self.traj_id[:n]][idx_n, gj]
            if cfg.clip_action:
                action = _clip_like_controller(action)
        else:
            arm = min(cfg.arm_dim, self.act_dim)
            action[:, :arm] = torch.clip(
                (tgt[:, :arm] - state[:, :arm]) / max(cfg.joint_scale, 1e-8), -1, 1
            )
            if tgt.shape[-1] > arm and cfg.gripper_src != "none":
                if cfg.gripper_src == "tgt":
                    action[:, arm:] = tgt[:, arm:]
                else:  # "j"
                    action[:, arm:] = tau[idx_n, j][:, arm:]
            if cfg.clip_action:
                action = torch.clip(action, -1, 1)

        # ---- [OURS A10] gate ---------------------------------------------- #
        if cfg.gate == "soft":
            mask = torch.exp(-0.5 * (dist / float(cfg.gate_sigma)) ** 2)
        else:
            mask = (dist < cfg.eps).to(self.dtype)

        self.step_count[:n] += 1
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

    # =================================================================== #
    # [OURS A8..A11] alignment regression tests
    # =================================================================== #
    import torch as _t

    def _mk(dense):
        """straight +x path, `dense` mm spacing, T=60."""
        step = dense / 1000.0
        pts = _t.zeros(60, 7)
        pts[:, 0] = _t.arange(60) * step
        pts[:, 3] = 1.0
        return pts

    # ---- (1) pure pursuit: a DENSE trajectory must still give a real target ----
    dense = _mk(6)                                    # 6 mm spacing
    cfg = AlignConfig(align="window", lookahead=1, lookahead_dist=0.05,
                      gate="hard", eps=1e-6)          # eps~0 => only exact hit
    tt = TrajectoryTeacher(cfg, n_envs=1, act_dim=7)
    tt.set_trajectory(dense, gripper=_t.zeros(60))
    tt.reset(state=_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    a_dense, _, _ = tt.action(_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    # OLD behaviour (lookahead=1 on 6 mm spacing) would ask for 0.06.
    # Pure pursuit must ask for ~0.05 m / 0.1 = 0.5.
    assert a_dense[0, 0] > 0.4, f"pure-pursuit target too weak: {float(a_dense[0,0])}"
    print(f"pure-pursuit on 6mm spacing: a_x={float(a_dense[0,0]):.3f} (lookahead=1 alone would be 0.06)")

    # and the legacy path is untouched when lookahead_dist=0
    c0 = AlignConfig(align="window", lookahead=1, lookahead_dist=0.0,
                     gate="hard", eps=1e-6)
    t0 = TrajectoryTeacher(c0, n_envs=1, act_dim=7)
    t0.set_trajectory(dense, gripper=_t.zeros(60))
    t0.reset(state=_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    a0, _, _ = t0.action(_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    assert abs(float(a0[0, 0]) - 0.06) < 1e-4, float(a0[0, 0])
    print(f"lookahead_dist=0 fallback preserved: a_x={float(a0[0,0]):.3f}")

    # ---- (2) window mode: monotone AND rate limited ----
    cfgw = AlignConfig(align="window", window=3, lookahead=1, lookahead_dist=0.0,
                       gate="hard", eps=1e9)
    tw = TrajectoryTeacher(cfgw, n_envs=1, act_dim=7)
    tw.set_trajectory(dense, gripper=_t.zeros(60))
    tw.reset(state=_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    js = []
    for k in range(10):
        # teleport the "student" to waypoint 40k mm ahead -- an illegal jump
        st = _t.tensor([[0.040 * k, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]])
        tw.action(st)
        js.append(int(tw.j[0]))
    assert js[0] <= 3, js          # first call cannot reach index 40/6=6.67
    jumps = np.diff(js)
    assert (jumps >= 0).all(), js  # monotone
    assert (jumps <= cfgw.window).all(), js   # rate limited
    print(f"window monotone+rate-limited: j={js} (window={cfgw.window})")

    # ---- (3) soft gate is never identically zero (the cold-start fix) ----
    cfgs = AlignConfig(align="window", gate="soft", gate_sigma=0.05, eps=0.001)
    ts = TrajectoryTeacher(cfgs, n_envs=1, act_dim=7)
    ts.set_trajectory(dense, gripper=_t.zeros(60))
    ts.reset(state=_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    far = _t.tensor([[0.30, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]])   # 30 cm away
    _, w_far, d_far = ts.action(far)
    assert float(w_far[0]) > 0.0, "soft gate collapsed to 0 => KL would be a no-op"
    ts.reset(state=_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    _, w_near, _ = ts.action(_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    assert float(w_near[0]) > 0.99, float(w_near[0])
    # NB: d_far is < 0.30 because the window clamps the match to j+window; that is
    # the point of the rate limit, so the assertion is relative, not absolute.
    assert float(w_far[0]) < float(w_near[0]) * 1e-4, (float(w_far[0]), float(w_near[0]))
    print(f"soft gate: w(on-path)={float(w_near[0]):.4f}  w(far, d={float(d_far[0]):.3f}m)="
          f"{float(w_far[0]):.2e}  -- never exactly 0, so Eq.(7) always has a gradient")

    # ---- (4) gripper decoupling ----
    g = _t.zeros(60)
    g[30:] = -1.0                                     # closes at waypoint 30
    cgn = AlignConfig(align="window", gate="hard", eps=1e9, gripper_src="none")
    tg = TrajectoryTeacher(cgn, n_envs=1, act_dim=7)
    tg.set_trajectory(dense, gripper=g)
    tg.reset(state=_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    ag, _, _ = tg.action(_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    assert float(ag[0, -1]) == 0.0, float(ag[0, -1])
    print("gripper_src='none' emits exactly 0 on the gripper dim")

    # ---- (5) window mode: a BACKWARD excursion must not rewind j ----
    cw2 = AlignConfig(align="window", window=5, lookahead=1, lookahead_dist=0.0,
                      gate="hard", eps=1e9)
    tw2 = TrajectoryTeacher(cw2, n_envs=1, act_dim=7)
    tw2.set_trajectory(dense, gripper=_t.zeros(60))
    tw2.reset(state=_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    for x in (0.0, 0.02, 0.04, 0.06):
        pass
    # walk forward, then jump backwards to the origin
    for x in (0.0, 0.01, 0.02, 0.03, 0.04):
        tw2.action(_t.tensor([[x, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    j_before = int(tw2.j[0])
    tw2.action(_t.tensor([[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    assert int(tw2.j[0]) >= j_before, (j_before, int(tw2.j[0]))
    print(f"backward excursion: j {j_before} -> {int(tw2.j[0])} (no phase collapse)")

    # ---- (6) reset re-anchoring ----
    cr = AlignConfig(align="window", reanchor_on_reset=True)
    tr = TrajectoryTeacher(cr, n_envs=1, act_dim=7)
    tr.set_trajectory(dense)
    tr.reset(state=_t.tensor([[0.30, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]))
    assert int(tr.j[0]) == 50, int(tr.j[0])           # 0.30 / 0.006 = 50
    print(f"reanchor_on_reset: j={int(tr.j[0])} (nearest to a 0.30 m start)")

    print("\n*** ALL alignment regression tests PASSED ***")
