@echo off
REM ============================================================
REM  build_mplib.bat -- build mplib under the MSVC toolchain.
REM  NOTE: keep this file ASCII-only. cmd.exe decodes a .bat as
REM        GBK on this machine, so UTF-8 Chinese comments get
REM        shredded into bogus commands.
REM  mplib ships only an sdist on PyPI (no Windows wheel); the
REM  only missing piece here is cmake, which pip provides.
REM ============================================================
setlocal
set PY=E:\Users\bobxu\PycharmProjects\PCK-RL\_repro\venv\Scripts\python.exe
set VCVARS=C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat

echo === [1/4] load MSVC environment ===
call "%VCVARS%"
if errorlevel 1 ( echo VCVARS_FAILED & exit /b 1 )

echo === [2/4] toolchain visibility ===
where cl
where cmake

echo === [3/4] pip install cmake ===
"%PY%" -m pip install cmake
if errorlevel 1 ( echo CMAKE_INSTALL_FAILED & exit /b 1 )

echo === [4/4] pip install mplib ===
"%PY%" -m pip install mplib
if errorlevel 1 ( echo MPLIB_BUILD_FAILED & exit /b 1 )

echo === import self-check ===
"%PY%" -c "import mplib; print('mplib OK')"
exit /b %errorlevel%
