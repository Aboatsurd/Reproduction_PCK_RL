#!/usr/bin/env bash
# PCK-RL stage1.3/2 - WSL step0(h): retry the SAPIEN probe WITHOUT nested heredocs
# (the previous attempt failed because a heredoc inside a script piped to `bash -s`
#  steals the same stdin stream - the script body gets eaten).
# Probe file lives on the Windows side and is read via /mnt/e ; no heredocs anywhere.
# ASCII only.
set -u

PROBE=/mnt/e/Users/bobxu/PycharmProjects/PCK-RL/_repro/stage1/wsl_probe_sapien.py
PY="$HOME/pckrl-wsl/venv/bin/python"
LVP=/usr/share/vulkan/icd.d/lvp_icd.json
CLEAN_PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

echo "=== 0. sanity ==="
echo "  /mnt/e mounted: $(test -d /mnt/e && echo yes || echo NO)"
echo "  probe exists  : $(test -f "$PROBE" && echo yes || echo NO)"
echo "  python        : $PY  ($(test -x "$PY" && echo ok || echo MISSING))"
echo "  nvidia-smi    : $(command -v nvidia-smi || echo 'not on PATH')"

echo ""
echo "=== RUN 1: lvp forced, nvidia VISIBLE (the configuration that failed before) ==="
VK_ICD_FILENAMES=$LVP "$PY" "$PROBE" "visible+lvp" 2>&1 | grep -vE 'pkg_resources|import pkg_resources'

echo ""
echo "=== RUN 2: lvp forced, nvidia HIDDEN (PATH without /usr/lib/wsl/lib) ==="
env PATH=$CLEAN_PATH VK_ICD_FILENAMES=$LVP "$PY" "$PROBE" "hidden+lvp" 2>&1 | grep -vE 'pkg_resources|import pkg_resources'

echo ""
echo "=== RUN 3: nvidia HIDDEN, VK_ICD_FILENAMES unset (let the loader pick) ==="
env -u VK_ICD_FILENAMES PATH=$CLEAN_PATH "$PY" "$PROBE" "hidden+auto" 2>&1 | grep -vE 'pkg_resources|import pkg_resources'

echo ""
echo "=== RUN 4: like RUN 2, but with VK_LOADER_DEBUG to capture the demanded ext list ==="
env PATH=$CLEAN_PATH VK_ICD_FILENAMES=$LVP VK_LOADER_DEBUG=error "$PY" "$PROBE" "hidden+lvp+dbg" 2>&1 \
  | grep -viE 'pkg_resources|import pkg_resources' | grep -iE 'ERROR|extension|>>>|\[hidden' | head -25

echo ""
echo "=== STEP0h done ==="
