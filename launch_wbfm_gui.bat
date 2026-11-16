@echo off
SETLOCAL
REM Launcher for WBFM GUI with memory
CALL "%~dp0launcher_settings.bat"

IF NOT EXIST "%WBFM_PYTHON%" (
    echo ERROR: Python not found at "%WBFM_PYTHON%"
    echo Set WBFM_CONDA_ROOT / WBFM_ENV in launcher_settings.local.bat
    pause
    EXIT /B 1
)

REM Skip "mamba activate" (several seconds of startup): put the env's DLL/script dirs on PATH instead
SET "WBFM_ENV_DIR=%WBFM_CONDA_ROOT%\envs\%WBFM_ENV%"
SET "PATH=%WBFM_ENV_DIR%;%WBFM_ENV_DIR%\Library\mingw-w64\bin;%WBFM_ENV_DIR%\Library\usr\bin;%WBFM_ENV_DIR%\Library\bin;%WBFM_ENV_DIR%\Scripts;%PATH%"

echo Launching WBFM Trace Explorer...
"%WBFM_PYTHON%" -X utf8 "%WBFM_ROOT%\launch_gui.py" %*

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: The GUI exited with an error code %ERRORLEVEL%. See output above.
    pause
)
