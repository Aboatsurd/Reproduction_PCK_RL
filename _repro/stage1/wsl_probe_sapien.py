import os, sys, traceback

mode = sys.argv[1] if len(sys.argv) > 1 else "?"
print("[%s] nvidia-smi reachable = %s" % (mode, os.system("nvidia-smi > /dev/null 2>&1") == 0))
print("[%s] VK_ICD_FILENAMES(before import) = %r" % (mode, os.environ.get("VK_ICD_FILENAMES")))

try:
    import sapien
except Exception as e:
    print("[%s] import sapien FAILED: %s: %s" % (mode, type(e).__name__, e))
    sys.exit(0)

print("[%s] sapien version = %s" % (mode, sapien.__version__))
print("[%s] VK_ICD_FILENAMES(after import)  = %r" % (mode, os.environ.get("VK_ICD_FILENAMES")))

ctors = []
try:
    import sapien.core as s_core
    ctors.append(("sapien.core.Scene", s_core.Scene))
except Exception as e:
    print("[%s] import sapien.core FAILED: %s: %s" % (mode, type(e).__name__, e))
ctors.append(("sapien.Scene", sapien.Scene))

for ctor_name, ctor in ctors:
    try:
        s = ctor()
        print("[%s] >>> %s() OK" % (mode, ctor_name))
        try:
            s.step()
            print("[%s] >>> %s().step() OK" % (mode, ctor_name))
        except Exception as e:
            print("[%s] >>> %s().step() FAILED: %s: %s" % (mode, ctor_name, type(e).__name__, e))
    except Exception as e:
        print("[%s] >>> %s() FAILED: %s: %s" % (mode, ctor_name, type(e).__name__, e))
