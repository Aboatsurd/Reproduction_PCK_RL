#!/usr/bin/env bash
# PCK-RL 阶段1.3/2 · WSL 第0步(d)：查清 SAPIEN 到底要哪个 Vulkan 设备扩展
# 手法：从 sapien 的 .so 里 strings 出所有 VK_* 名字，与 lavapipe 提供的对比
# 不需要 sudo，不需要渲染设备。

echo "=== STEP0d: Vulkan extension audit ==="
. "$HOME/pckrl-wsl/venv/bin/activate"

SAPDIR=$(python -c "import sapien,os;print(os.path.dirname(sapien.__file__))" 2>/dev/null)
echo "sapien dir: $SAPDIR"
echo "--- native libs ---"
ls -1 "$SAPDIR"/*.so 2>/dev/null

echo ""
echo "### A. VK_* extension identifiers referenced by SAPIEN"
find "$SAPDIR" -name '*.so' -print0 2>/dev/null | xargs -0 -I{} strings {} 2>/dev/null \
  | grep -oE 'VK_[A-Za-z_]+' | sort -u

echo ""
echo "### B. VK_* extension identifiers advertised by lavapipe (libvulkan_lvp.so)"
strings /usr/lib/x86_64-linux-gnu/libvulkan_lvp.so 2>/dev/null \
  | grep -oE 'VK_[A-Za-z_]+' | sort -u

echo ""
echo "### C. loader-side debug run (VK_LOADER_DEBUG) --- looking for the missing extension"
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json
export VK_LOADER_DEBUG=error,warn
python - <<'PYEOF' 2>&1 | tail -40
try:
    from sapien.render import RenderSystem
    rs = RenderSystem()
    print("RenderSystem() created OK")
except Exception as e:
    print("RenderSystem() FAILED:", type(e).__name__, e)
PYEOF

echo ""
echo "### D. mesa / loader package versions"
dpkg -l 2>/dev/null | grep -iE 'mesa-vulkan|libvulkan|mesa-common|libglx-mesa' | awk '{print $2, $3}'
echo ""
echo "=== STEP0d done ==="
