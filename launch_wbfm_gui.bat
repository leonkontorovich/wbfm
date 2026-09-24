@echo off
SETLOCAL
REM Launcher for WBFM GUI with memory
CALL "%~dp0launcher_settings.bat"
echo Activating WBFM GUI environment...
CALL "%WBFM_MAMBA%" activate %WBFM_ENV%

echo Launching WBFM Trace Explorer...
python -X utf8 "%WBFM_ROOT%\launch_gui.py" %*

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: The GUI exited with an error code %ERRORLEVEL%. See output above.
    pause
)
