#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# PCK-RL reproduction -- Linux environment setup (native Linux only).
#
# Author: reproduction work, not the paper authors.
# Target: lab RTX 4090/5090 box, or a rented GPU (AutoDL etc.).
#
# ASCII ONLY. Do not put non-ASCII characters in this file: WSL / minimal
# server locales are not UTF-8 and the script turns to mojibake.
#
# Usage:
#   bash _repro/linux/setup.sh                 # full install
#   SKIP_TORCH=1 bash _repro/linux/setup.sh    # if torch is already present
#
# This script is IDEMPOTENT-ish: re-running it only reinstalls what is missing.
# ---------------------------------------------------------------------------
set -euo pipefail

VENV="${VENV:-$HOME/pckrl-venv}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$VENV/bin/python"
PIP_INDEX="${PIP_INDEX:-}"          # e.g. https://pypi.tuna.tsinghua.edu.cn/simple

say() { printf '\n=== %s ===\n' "$*"; }

say "L1.1 GPU visible"
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
else
    echo "FATAL: nvidia-smi not found. This machine has no usable NVIDIA driver."
    exit 1
fi

say "L1.2 VULKAN GATE (hard blocker -- SAPIEN will not start without this)"
if ! command -v vulkaninfo >/dev/null 2>&1; then
    echo "vulkaninfo not found. Try: sudo apt-get install -y vulkan-tools"
fi
if command -v vulkaninfo >/dev/null 2>&1; then
    # --summary prints the devices the Vulkan loader can actually see.
    if vulkaninfo --summary 2>&1 | grep -q 'PHYSICAL_DEVICE_TYPE_DISCRETE_GPU'; then
        echo "OK: a discrete GPU is exposed through Vulkan."
        vulkaninfo --summary 2>&1 | grep -E 'deviceName|driverInfo|deviceType' | head -20
    else
        echo "WARNING: no discrete GPU visible through Vulkan."
        vulkaninfo --summary 2>&1 | grep -E 'deviceName|deviceType' | head -20
        echo
        echo "SAPIEN 3 REQUIRES the device extension VK_KHR_external_semaphore_fd."
        echo "Software rasterisers (llvmpipe / lavapipe) do NOT implement it, so"
        echo "sapien.core.Scene() fails with ErrorExtensionNotPresent."
        echo
        echo "Fix A (rented cloud GPU, no desktop -- this is the AutoDL recipe):"
        echo "  sudo mkdir -p /etc/vulkan/icd.d"
        echo "  sudo tee /etc/vulkan/icd.d/my_nvidia_icd.json >/dev/null <<'JSON'"
        echo '{ "file_format_version" : "1.0.0",'
        echo '  "ICD": { "library_path": "/lib/x86_64-linux-gnu/libEGL_nvidia.so.0",'
        echo '           "api_version" : "1.3.277" } }'
        echo "JSON"
        echo "  export VK_ICD_FILENAMES=/etc/vulkan/icd.d/my_nvidia_icd.json"
        echo "  NOTE: library_path must be libEGL_nvidia, NOT libGLX_nvidia --"
        echo "        a headless server has no X/GLX."
        echo
        echo "Fix B (physical box): make sure the driver ships"
        echo "  /usr/share/vulkan/icd.d/nvidia_icd.json  (it points at libGLX_nvidia.so.0)"
        echo "  then re-run:  vulkaninfo --summary"
        echo
        echo "STOP HERE until L1.2 passes. Installing first wastes an hour."
    fi
fi

say "L1.3 python"
python3 --version
python3 -c 'import sys; assert sys.version_info >= (3, 9), "need >= 3.9"; print("python OK")'

say "L1.4 disk"
df -h "$HOME" | tail -1 || true

say "L2.1 virtualenv"
if [ ! -x "$PY" ]; then
    python3 -m venv "$VENV"
fi
"$PY" -m pip install -U pip >/dev/null
# setuptools >= 81 removes pkg_resources, which sapien/__init__.py:2 imports.
# This bites on EVERY fresh venv. Do not remove this line.
"$PY" -m pip install "setuptools<81"
PIPX=()
if [ -n "$PIP_INDEX" ]; then PIPX=(-i "$PIP_INDEX"); fi
"$PY" -m pip install "${PIPX[@]}" wheel

say "L2.2 mani_skill 3.0.0b14 -- we install the UPSTREAM wheel for its DEPS only"
# Why: this repo is a source fork with no pyproject.toml/setup.py, so it cannot
# be pip-installed. Instead we install the upstream release to pull in
# sapien / fast_kinematics / mplib / toppra / gymnasium, and then let the fork's
# own mani_skill/ directory SHADOW it at runtime (see L2.4).
# fast_kinematics and mplib are Linux-only: this is the whole reason stage 1.3/2
# and stage 4 cannot be finished on Windows.
"$PY" -m pip install "${PIPX[@]}" "mani_skill==3.0.0b14"

if [ "${SKIP_TORCH:-0}" != "1" ]; then
    say "L2.3 torch (pick the wheel matching this machine's driver)"
    echo "Installing default (cu12x). If the driver is older, change the index URL."
    "$PY" -m pip install "${PIPX[@]}" torch --index-url https://download.pytorch.org/whl/cu124 || {
        echo "cu124 install failed -- falling back to plain PyPI torch"
        "$PY" -m pip install "${PIPX[@]}" torch
    }
fi

say "L2.4 make the FORK shadow site-packages/mani_skill"
echo "repo root : $REPO_ROOT"
if [ -f "$REPO_ROOT/mani_skill/envs/tasks/tabletop/peg_onlyPick_fhz.py" ]; then
    echo "OK: fork contains the authors' task file peg_onlyPick_fhz.py"
else
    echo "FATAL: $REPO_ROOT does not look like the PCK-RL fork."
    exit 1
fi
# _repro/stage3/ppo_kl.py already does sys.path.insert(0, repo_root) itself, so
# scripts under _repro/ need nothing. For ad-hoc python, export this:
cat > "$HOME/pckrl-env.sh" <<EOF
export PCKRL_ROOT="$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT\${PYTHONPATH:+:\$PYTHONPATH}"
export MS_ASSET_DIR="$REPO_ROOT/_assets"
EOF
echo "wrote $HOME/pckrl-env.sh  -- source it for ad-hoc python sessions"

say "L2.5 import check (this is the real end-to-end gate, not a dependency list)"
"$PY" - <<'PYEOF'
import sys, os
sys.path.insert(0, os.environ.get("PCKRL_ROOT", os.getcwd()))
import sapien
print("sapien", sapien.__version__)
import sapien.core
s = sapien.core.Scene()          # <-- the line that fails without Vulkan
print("sapien.core.Scene() OK")
import mani_skill
print("mani_skill from", mani_skill.__file__)   # must be the FORK, not site-packages
from mani_skill.envs.tasks.tabletop.peg_onlyPick_fhz import PegInsertionSideEnv
print("authors' PegInsertionSideEnv OK")
PYEOF

say "DONE"
echo "Next: bash _repro/linux/smoke_gpu.sh   (the GPU-sim gate)"
