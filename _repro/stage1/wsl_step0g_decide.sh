#!/usr/bin/env bash
# PCK-RL stage1.3/2 - WSL step0(g): DECISIVE test whether SAPIEN can run CPU-only in WSL
#
# Findings so far:
#  - official ManiSkill table: WSL -> CPU Sim OK, GPU Sim NO, Rendering NO
#  - sapien/_vulkan_tricks.py forces VK_ICD_FILENAMES to a bundled nvidia_icd.json
#    (points at libGLX_nvidia.so.0 which does NOT exist in WSL) whenever nvidia-smi succeeds
#  - so our earlier hard failure may be an artifact, not a real blocker
#
# This script:
#  A. enumerates lavapipe's real device extensions with a C program (does it have
#     VK_KHR_external_semaphore_fd ?)  <- definitive
#  B. retries sapien Scene with VK_ICD_FILENAMES=lvp and CUDA/nvidia hidden
#  C. retries sapien Scene with VK_ICD_FILENAMES=lvp and nvidia visible (baseline)
# ASCII only - WSL locale is not UTF-8 and Chinese would mojibake.

set -u
W=/tmp/pckrl_step0g
mkdir -p "$W"
PY="$HOME/pckrl-wsl/venv/bin/python"

echo "=== 0. where is nvidia-smi / is libGLX_nvidia present ==="
command -v nvidia-smi || echo "  nvidia-smi NOT on PATH"
ldconfig -p 2>/dev/null | grep -c libGLX_nvidia || true
echo "  sapien bundled vulkan_library:"
ls -1 "$HOME/pckrl-wsl/venv/lib/python3.12/site-packages/sapien/vulkan_library/" 2>/dev/null

echo ""
echo "=== A. lavapipe real device extensions (C program) ==="
cat > "$W/enum.c" <<'EOF'
#include <stdio.h>
#include <string.h>
#include <vulkan/vulkan.h>
int main(void){
  VkApplicationInfo ai={0}; ai.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO;
  ai.apiVersion=VK_API_VERSION_1_1;
  VkInstanceCreateInfo ici={0}; ici.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
  ici.pApplicationInfo=&ai;
  VkInstance inst;
  if(vkCreateInstance(&ici,NULL,&inst)!=VK_SUCCESS){printf("vkCreateInstance FAILED\n");return 1;}
  uint32_t n=0; vkEnumeratePhysicalDevices(inst,&n,NULL);
  printf("physical devices: %u\n",n);
  VkPhysicalDevice pd[8];
  if(n>8)n=8;
  vkEnumeratePhysicalDevices(inst,&n,pd);
  for(uint32_t i=0;i<n;i++){
    VkPhysicalDeviceProperties p; vkGetPhysicalDeviceProperties(pd[i],&p);
    printf("\n[device %u] %s  (api %u.%u.%u, vulkan %d.%d.%d)\n",i,p.deviceName,
      VK_VERSION_MAJOR(p.apiVersion),VK_VERSION_MINOR(p.apiVersion),VK_VERSION_PATCH(p.apiVersion),
      VK_VERSION_MAJOR(p.driverVersion),VK_VERSION_MINOR(p.driverVersion),VK_VERSION_PATCH(p.driverVersion));
    uint32_t ec=0; vkEnumerateDeviceExtensionProperties(pd[i],NULL,&ec,NULL);
    VkExtensionProperties *ep=malloc(ec*sizeof(VkExtensionProperties));
    vkEnumerateDeviceExtensionProperties(pd[i],NULL,&ec,ep);
    int has_sem_fd=0,has_mem_fd=0,has_fence_fd=0;
    for(uint32_t j=0;j<ec;j++){
      if(!strcmp(ep[j].extensionName,"VK_KHR_external_semaphore_fd"))has_sem_fd=1;
      if(!strcmp(ep[j].extensionName,"VK_KHR_external_memory_fd"))has_mem_fd=1;
      if(!strcmp(ep[j].extensionName,"VK_KHR_external_fence_fd"))has_fence_fd=1;
    }
    printf("  total device extensions: %u\n",ec);
    printf("  VK_KHR_external_semaphore_fd = %s   <== SAPIEN DEMANDS THIS\n",has_sem_fd?"YES":"NO");
    printf("  VK_KHR_external_memory_fd    = %s\n",has_mem_fd?"YES":"NO");
    printf("  VK_KHR_external_fence_fd     = %s\n",has_fence_fd?"YES":"NO");
    free(ep);
  }
  vkDestroyInstance(inst,NULL);
  return 0;
}
EOF
gcc -o "$W/enum" "$W/enum.c" -lvulkan 2>&1 | head -10 && echo "  (compiled)"
echo "--- run with lvp only ---"
VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json "$W/enum" 2>&1 | head -25
echo "--- run with default icd.d (all drivers) ---"
VK_ICD_FILENAMES= "$W/enum" 2>&1 | head -25

echo ""
echo "=== B. sapien Scene, lvp + nvidia hidden (PATH without /usr/lib/wsl/lib) ==="
env -u SAPIEN_VULKAN_LIBRARY_PATH -u __EGL_VENDOR_LIBRARY_FILENAMES \
  VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json \
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  "$PY" - <<'PYEOF' 2>&1 | tail -20
import os, traceback
print("nvidia-smi on PATH:", os.system("nvidia-smi > /dev/null 2>&1") == 0)
try:
    import sapien
    print("sapien", sapien.__version__)
    from sapien.core import Scene
    s = Scene()
    print(">>> Scene() OK  <== CPU-ONLY SAPIEN WORKS IN WSL")
except Exception as e:
    print(">>> Scene() FAILED:", type(e).__name__, e)
PYEOF

echo ""
echo "=== C. sapien Scene, lvp + nvidia VISIBLE (baseline / expected fail) ==="
env -u SAPIEN_VULKAN_LIBRARY_PATH -u __EGL_VENDOR_LIBRARY_FILENAMES \
  VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json \
  "$PY" - <<'PYEOF' 2>&1 | tail -20
import os, traceback
print("nvidia-smi on PATH:", os.system("nvidia-smi > /dev/null 2>&1") == 0)
try:
    import sapien
    s = sapien.Scene()
    print(">>> Scene() OK")
except Exception as e:
    print(">>> Scene() FAILED:", type(e).__name__, e)
PYEOF

echo ""
echo "=== STEP0g done ==="
