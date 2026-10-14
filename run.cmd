@echo off
setlocal
pushd "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -X utf8 -B -m lumalock %*
) else (
    python -X utf8 -B -m lumalock %*
)
set "lumalock_exit=%errorlevel%"
popd
exit /b %lumalock_exit%
