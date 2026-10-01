# Stage 0.1b-fix + 0.2 smoke test  (ASCII-only on purpose: PS 5.1 GBK trap with non-ASCII .ps1)
$ErrorActionPreference = 'Continue'
$repo = 'E:\Users\bobxu\PycharmProjects\PCK-RL'
$py   = "$repo\_repro\venv\Scripts\python.exe"
$logd = "$repo\_repro\logs"

Write-Output "=== [1] fix setuptools (restore pkg_resources) ==="
$l1 = "$logd\01b_fix_setuptools.log"
& $py -m pip install "setuptools<81" *> $l1
Get-Content $l1 -Tail 4 | ForEach-Object { "    $_" }

Write-Output ""
Write-Output "=== [2] verify setuptools / pkg_resources ==="
& $py -c "import setuptools, pkg_resources; print('OK setuptools', setuptools.__version__)" 2>&1 | Select-Object -First 6

Write-Output ""
Write-Output "=== [3] verify import sapien ==="
& $py -c "import sapien; print('OK sapien', sapien.__version__)" 2>&1 | Select-Object -First 8

Write-Output ""
Write-Output "=== [4] which mani_skill is imported (must be the FORK) ==="
Push-Location $repo
& $py -c "import mani_skill; print('file   :', mani_skill.__file__); print('version:', mani_skill.__version__)" 2>&1 | Select-Object -First 6

Write-Output ""
Write-Output "=== [5] SMOKE: PokeCube-v1 ==="
$l5 = "$logd\02_smoke_pokecube.log"
& $py -c "import mani_skill.envs, gymnasium as gym; env=gym.make('PokeCube-v1'); obs,_=env.reset(); print('SMOKE_OK obs type:', type(obs).__name__); a=env.action_space.sample(); o,r,te,tr,info=env.step(a); print('STEP_OK reward:', r); env.close(); print('CLOSED_OK')" *> $l5
Get-Content $l5 | Select-Object -First 30
Pop-Location

Write-Output ""
Write-Output "=== [6] tail of smoke log (if empty above) ==="
Get-Content $l5 -Tail 20
