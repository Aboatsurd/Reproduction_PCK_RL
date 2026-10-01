#!/usr/bin/env bash
# PCK-RL 阶段1.3/2 · WSL 第0步(b)：修 pkg_resources + 重跑 SAPIEN 验证
# 注意：本文件由 Windows 侧 write 工具生成，会带 UTF-8 BOM；
#       调用方在 PowerShell 里已用 ([char]0xFEFF) 剥掉，再经 stdin 喂给 bash -s。

echo "=== STEP0b: fix pkg_resources, then re-verify SAPIEN ==="
. "$HOME/pckrl-wsl/venv/bin/activate"
echo "python: $(python -V 2>&1)"

echo "--- install setuptools<81 (sapien imports pkg_resources; py3.12 venv ships without it) ---"
python -m pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple "setuptools<81"
echo "pip exit=$?"
echo "setuptools version: $(python -c 'import setuptools; print(setuptools.__version__)' 2>&1)"
echo "pkg_resources: $(python -c 'import pkg_resources; print(\"import OK\")' 2>&1)"

echo ""
echo "--- venv size ---"
du -sh "$HOME/pckrl-wsl" 2>/dev/null

echo ""
echo "--- VERIFY 1: import sapien ---"
python - <<'PYEOF'
import sys
ok = True
try:
    import sapien
    print("  sapien version:", getattr(sapien, "__version__", "?"))
except Exception as e:
    print("  !!! import sapien FAILED:", type(e).__name__, e); ok = False

if not ok:
    sys.exit(1)
PYEOF
echo "  verify1 exit=$?"

echo ""
echo "--- VERIFY 2: Scene()  (core sim, no renderer) ---"
python - <<'PYEOF'
import sys
try:
    import sapien.core as sapien_core
except Exception as e:
    print("  !!! import sapien.core FAILED:", type(e).__name__, e); sys.exit(1)
try:
    sc = sapien_core.Scene()
    print("  Scene() created OK ->", type(sc).__name__)
except Exception as e:
    print("  !!! Scene() FAILED:", type(e).__name__, e); sys.exit(2)
PYEOF
echo "  verify2 exit=$?"

echo ""
echo "--- VERIFY 3: RenderSystem()  <-- THE lavapipe QUESTION ---"
python - <<'PYEOF'
import sys
try:
    from sapien.render import RenderSystem
except Exception as e:
    print("  !!! import sapien.render FAILED:", type(e).__name__, e); sys.exit(1)
try:
    rs = RenderSystem()
    print("  RenderSystem() created OK")
except Exception as e:
    print("  !!! RenderSystem() FAILED:", type(e).__name__, e)
    print("      -> WSL cannot create a SAPIEN render device. Plan step 0 verification B.")
    sys.exit(2)
PYEOF
echo "  verify3 exit=$?"

echo ""
echo "--- vulkan info ---"
ls -1 /usr/share/vulkan/icd.d/ 2>/dev/null
echo "VK_ICD_FILENAMES=${VK_ICD_FILENAMES:-(unset)}"
echo ""
echo "=== STEP0b done ==="
