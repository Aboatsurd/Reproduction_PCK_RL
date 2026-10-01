#!/usr/bin/env bash
# PCK-RL · WSL 第0步(f)：读 SAPIEN 源码，看能否无渲染设备跑（决定阶段 1.3/2 能否留在 WSL）
# 关键问题：SAPIEN 建 Scene 时是否"无条件"创建 RenderSystem？有没有环境变量可跳过？
set -u

V="$HOME/pckrl-wsl/venv/lib/python3.12/site-packages/sapien"

echo "=== 1. sapien 包内文件 ==="
ls -1 "$V"

echo ""
echo "=== 2. _vulkan_tricks.py 全文 ==="
cat -n "$V/_vulkan_tricks.py" 2>/dev/null

echo ""
echo "=== 3. sapien 自认的环境变量 ==="
grep -rhoE 'SAPIEN_[A-Z_]+' "$V" --include=*.py 2>/dev/null | sort -u
echo "--- os.environ 用法 ---"
grep -rn 'environ' "$V" --include=*.py 2>/dev/null | head -20

echo ""
echo "=== 4. sapien_core 扩展里的 vulkan 相关环境变量名 ==="
SO=$(ls "$V"/../sapien_core*.so 2>/dev/null | head -1)
echo "  so = $SO"
if [ -n "$SO" ]; then
  strings "$SO" | grep -oE '\b(VK_[A-Z_]+|SAPIEN_[A-Z_]+|VULKAN_[A-Z_]+)\b' \
    | sort -u | grep -vE '^VK_(OBJECT_TYPE|STRUCTURE_TYPE|RESULT|MAX_)' | head -60
fi

echo ""
echo "=== 5. lavapipe 是否支持 external_semaphore_fd（权威判定：枚举设备扩展） ==="
echo "  gcc: $(command -v gcc || echo MISSING)"
echo "  python3: $(command -v python3)"
echo "  (loader 验证结果已由 VK_LOADER_DEBUG 给出，此处不重复)"

echo ""
echo "=== 6. 有没有 SAPIEN_DISABLE / headless 开关的线索 ==="
if [ -n "$SO" ]; then
  strings "$SO" | grep -iE 'disable_(vulkan|render)|headless|no_render' | sort -u | head -20
fi

echo ""
echo "=== STEP0f done ==="
