@echo off
rem Run vortex-cli straight from source, without installing the package.
rem Uses whatever Python is on PATH (falls back to the "py" launcher).
setlocal
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

where python >nul 2>nul
if not errorlevel 1 (
	python -m vortex_cli %*
	exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if not errorlevel 1 (
	py -3 -m vortex_cli %*
	exit /b %ERRORLEVEL%
)

echo vortex-cli: no Python found on PATH. Install Python 3.10+ from python.org. 1>&2
exit /b 1
