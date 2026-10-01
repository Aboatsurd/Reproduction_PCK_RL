#!/usr/bin/env bash
# probe_mplib_wsl.sh
# Question: can WSL Ubuntu-24.04 serve as the Stage-1.3/2 (mplib motion planning)
# host on this laptop, given that mplib ships ONLY manylinux_x86_64 wheels?
set -u

echo "=== [1] platform ==="
uname -srm
python3 -c "import platform;print('python', platform.python_version(), platform.machine())"

echo
echo "=== [2] pip ==="
python3 -m pip --version 2>&1 | head -2

echo
echo "=== [3] Vulkan ICDs -- decides whether pointcloud rendering can work here ==="
if [ -d /usr/share/vulkan/icd.d ]; then
  ls -1 /usr/share/vulkan/icd.d/
else
  echo "  (no /usr/share/vulkan/icd.d)"
fi
echo "  --- vulkan loader present? ---"
ls -1 /usr/lib/x86_64-linux-gnu/libvulkan.so* 2>/dev/null || echo "  libvulkan not installed"

echo
echo "=== [4] can pip fetch the mplib manylinux wheel? ==="
rm -rf /tmp/mplib_probe
python3 -m pip download --no-deps --only-binary :all: mplib -d /tmp/mplib_probe 2>&1 | tail -8
echo "  --- downloaded ---"
ls -la /tmp/mplib_probe 2>/dev/null | tail -5

echo
echo "=== [5] existing work dirs ==="
ls -d "$HOME"/repro/* 2>/dev/null || echo "  (no ~/repro)"
echo "  ~/.maniskill:  $(du -sh "$HOME/.maniskill" 2>/dev/null | cut -f1 || echo none)"
