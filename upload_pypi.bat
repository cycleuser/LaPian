@echo off
chcp 65001 >nul
echo === LaPian PyPI Upload Script ===

REM Clean previous build artifacts
echo [1/4] Cleaning old build artifacts...
if exist dist rd /s /q dist
if exist build rd /s /q build
for /d %%i in (*.egg-info) do rd /s /q "%%i"

REM Install/upgrade build tools
echo [2/4] Installing/upgrading build tools...
pip install --upgrade build twine
if errorlevel 1 goto :error

REM Build the package
echo [3/4] Building package...
python -m build
if errorlevel 1 goto :error

REM Upload to PyPI
echo [4/4] Uploading to PyPI...
python -m twine upload dist\*
if errorlevel 1 goto :error

echo === Done! ===
goto :eof

:error
echo === Upload failed! ===
exit /b 1
