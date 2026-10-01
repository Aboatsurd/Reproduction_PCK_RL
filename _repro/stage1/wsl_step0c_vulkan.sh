#!/usr/bin/env bash
# PCK-RL 阶段1.3/2 · WSL 第0步(c)：让 SAPIEN 找到 lavapipe 这个软件 Vulkan 设备
# 背景：/usr/share/vulkan/icd.d/ 里有 lvp_icd.json（lavapipe），但 SAPIEN 的
#       _vulkan_tricks.py 只去找 NVIDIA 的 ICD，于是报 failed to find a rendering device。

echo "=== STEP0c: point SAPIEN at lavapipe ==="

echo "--- lavapipe loader present? ---"
ls -l /usr/lib/x86_64-linux-gnu/libvulkan_lvp.so* 2>/dev/null || echo "  libvulkan_lvp.so NOT FOUND  <-- need: sudo apt install mesa-vulkan-drivers"
echo "--- loader present? ---"
ls -l /usr/lib/x86_64-linux-gnu/libvulkan.so* 2>/dev/null | head -5 || echo "  libvulkan.so NOT FOUND"
echo "--- lvp_icd.json content ---"
cat /usr/share/vulkan/icd.d/lvp_icd.json 2>/dev/null
echo "--- glvnd vendor dir ---"
ls -1 /usr/share/glvnd/egl_vendor.d/ 2>/dev/null || echo "  (none)"
echo "--- vulkaninfo available? ---"
which vulkaninfo || echo "  no vulkaninfo (vulkan-tools not installed)"
echo "--- passwordless sudo? ---"
sudo -n true 2>/dev/null && echo "  SUDO_NOPASSWD=yes" || echo "  SUDO_NOPASSWD=no"

echo ""
echo "--- VERIFY 3 with VK_ICD_FILENAMES=lvp ---"
. "$HOME/pckrl-wsl/venv/bin/activate"
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json
export VK_DRIVER_FILES=/usr/share/vulkan/icd.d/lvp_icd.json
python - <<'PYEOF'
import os
print("  VK_ICD_FILENAMES =", os.environ.get("VK_ICD_FILENAMES"))
try:
    from sapien.render import RenderSystem
    rs = RenderSystem()
    print("  RenderSystem() created OK   <<< LAVAPIPE WORKS")
except Exception as e:
    print("  RenderSystem() FAILED:", type(e).__name__, e)
PYEOF
echo "  verify3 exit=$?"

echo ""
echo "--- VERIFY 2 with same env ---"
python - <<'PYEOF'
try:
    import sapien.core as sapien_core
    sc = sapien_core.Scene()
    print("  Scene() created OK ->", type(sc).__name__)
except Exception as e:
    print("  Scene() FAILED:", type(e).__name__, e)
PYEOF
echo "  verify2 exit=$?"

echo ""
echo "=== STEP0c done ==="
