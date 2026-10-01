#!/usr/bin/env bash
# PCK-RL 阶段1.3/2 · WSL 第0步：最小风险验证
# 目的：只装 sapien + numpy，证明 WSL 能建 SAPIEN 场景（唯一真实未知数 = 无 NVIDIA Vulkan）
# 失败即止损：阶段 1.3/2 改去 4090

echo "=== STEP0: WSL minimal SAPIEN validation ==="
echo "--- identity ---"
id
echo "--- python ---"
python3 --version
which python3
echo "--- venv module? ---"
python3 -c "import venv; print('venv module OK')" || echo "!!! venv module MISSING (need python3-venv)"
echo ""
echo "--- create venv at ~/pckrl-wsl/venv ---"
mkdir -p "$HOME/pckrl-wsl"
if [ -x "$HOME/pckrl-wsl/venv/bin/python" ]; then
  echo "venv already exists, reusing"
else
  python3 -m venv "$HOME/pckrl-wsl/venv" || { echo "!!! VENV CREATE FAILED"; exit 1; }
fi
. "$HOME/pckrl-wsl/venv/bin/activate"
echo "python: $(python -V 2>&1)"
echo "pip:    $(pip -V 2>&1)"
echo ""
echo "--- install sapien==3.0.0b1 + numpy<2 (tsinghua mirror) ---"
pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple "sapien==3.0.0b1" "numpy<2"
echo "pip exit=$?"
echo ""
echo "--- venv size so far ---"
du -sh "$HOME/pckrl-wsl" 2>/dev/null
echo ""
echo "--- verify: import + Scene() ---"
python - <<'PYEOF'
import sys
try:
    import sapien
    print("sapien version:", getattr(sapien, "__version__", "?"))
except Exception as e:
    print("!!! IMPORT sapien FAILED:", type(e).__name__, e)
    sys.exit(1)

try:
    import sapien.core as sapien_core
except Exception as e:
    print("!!! IMPORT sapien.core FAILED:", type(e).__name__, e)
    sys.exit(1)

# Scene() with default (no renderer) - the real question is whether SAPIEN
# can initialise at all without an NVIDIA Vulkan device
try:
    sc = sapien_core.Scene()
    print("Scene() created OK  ->", type(sc).__name__)
except Exception as e:
    print("!!! Scene() FAILED:", type(e).__name__, e)
    sys.exit(2)

# Now the harder one: force a render system (this is what tabletop tasks need for cameras)
try:
    from sapien.render import RenderSystem
    rs = RenderSystem()
    print("RenderSystem() created OK")
except Exception as e:
    print("!!! RenderSystem() FAILED:", type(e).__name__, e)
    print("    -> this is the lavapipe question; see plan section 5 step 0 verification B")
    sys.exit(3)

print("STEP0 OK")
PYEOF
rc=$?
echo ""
echo "=== STEP0 finished, verify exit=$rc ==="
exit $rc
