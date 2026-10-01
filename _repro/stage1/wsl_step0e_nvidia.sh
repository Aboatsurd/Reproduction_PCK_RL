#!/usr/bin/env bash
# PCK-RL 阶段1.3/2 · WSL 第0步(e)：查 NVIDIA GPU 直通与 Vulkan ICD
# 若 WSL 里能拿到 nvidia_icd.json（真 GPU 的 Vulkan 驱动），SAPIEN 就有的救；
# 否则 lavapipe 缺 VK_KHR_external_semaphore_fd 是死结 → 阶段1.3/2 必须去 4090。
# 注意：输出必须小，别再倒 Vulkan 枚举表。

echo "=== STEP0e: NVIDIA passthrough / Vulkan ICD audit ==="

echo "--- 1. nvidia-smi in WSL? ---"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv 2>&1 | head -5
else
  echo "  nvidia-smi NOT on PATH"
fi

echo ""
echo "--- 2. WSL GPU libs (/usr/lib/wsl/lib) ---"
ls -1 /usr/lib/wsl/lib 2>/dev/null | head -20 || echo "  /usr/lib/wsl/lib missing"

echo ""
echo "--- 3. any nvidia ICD anywhere? ---"
find /usr/share/vulkan /etc/vulkan /usr/lib -maxdepth 4 -iname '*nvidia*' 2>/dev/null | head -20
echo "  (ls of icd.d, names only)"
ls -1 /usr/share/vulkan/icd.d/ 2>/dev/null

echo ""
echo "--- 4. /dev/dxg present? (WSL GPU paravirt device) ---"
ls -l /dev/dxg 2>/dev/null || echo "  /dev/dxg MISSING  -> no GPU paravirtualization"

echo ""
echo "--- 5. is there a WSL d3d12 mesa driver (dzn, uses the Windows GPU)? ---"
find /usr/lib/x86_64-linux-gnu -maxdepth 1 -iname '*dzn*' 2>/dev/null
find /usr/share/vulkan -iname '*dzn*' 2>/dev/null
echo "  (mesa d3d12 support check)"
dpkg -L mesa-vulkan-drivers 2>/dev/null | grep -iE 'dzn|d3d12' | head -5 || echo "  no dzn files in mesa-vulkan-drivers"

echo ""
echo "--- 6. lvp device extensions (small, filtered) ---"
# Only show the external_* ones - these are what SAPIEN demands
strings /usr/lib/x86_64-linux-gnu/libvulkan_lvp.so 2>/dev/null \
  | grep -oE 'VK_KHR_external_[a-z_]+' | sort -u | head -20
echo "  ^ lavapipe's external_* extensions (SAPIEN needs VK_KHR_external_semaphore_fd)"

echo ""
echo "=== STEP0e done ==="
