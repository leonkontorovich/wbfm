@echo off
SETLOCAL
TITLE WBFM Dashboard
REM Launcher for the WBFM recording dashboard / trace explorer (launch_gui.py).
REM Desktop shortcut: may start this window minimized; failures pop up a message box.
CALL "%~dp0launcher_settings.bat"

IF NOT EXIST "%WBFM_PYTHON%" (
    echo ERROR: Python not found at "%WBFM_PYTHON%"
    echo Set WBFM_CONDA_ROOT / WBFM_ENV in launcher_settings.local.bat
    SET "WBFM_MSG=Python not found at %WBFM_PYTHON%. Set WBFM_CONDA_ROOT / WBFM_ENV in launcher_settings.local.bat"
    CALL :show_error
    pause
    EXIT /B 1
)

REM Skip "mamba activate" (several seconds of startup): put the env's DLL/script dirs on PATH instead
SET "WBFM_ENV_DIR=%WBFM_CONDA_ROOT%\envs\%WBFM_ENV%"
SET "PATH=%WBFM_ENV_DIR%;%WBFM_ENV_DIR%\Library\mingw-w64\bin;%WBFM_ENV_DIR%\Library\usr\bin;%WBFM_ENV_DIR%\Library\bin;%WBFM_ENV_DIR%\Scripts;%PATH%"

echo Launching WBFM Dashboard...
"%WBFM_PYTHON%" -X utf8 "%WBFM_ROOT%\launch_gui.py" %*
SET "WBFM_RC=%ERRORLEVEL%"

IF NOT "%WBFM_RC%"=="0" (
    echo.
    echo ERROR: The GUI exited with error code %WBFM_RC%. See output above.
    SET "WBFM_MSG=The WBFM Dashboard exited with error code %WBFM_RC%. Details are in the WBFM Dashboard console window on the taskbar."
    CALL :show_error
    pause
)
EXIT /B %WBFM_RC%

:show_error
REM Message box, so an error is not missed when this console is minimized. The text is passed in WBFM_MSG (an
REM environment variable), so quotes, apostrophes or percent signs in paths cannot break the PowerShell command
powershell.exe -NoProfile -WindowStyle Hidden -Command "Add-Type -AssemblyName PresentationFramework; [void][System.Windows.MessageBox]::Show($env:WBFM_MSG, 'WBFM Dashboard', 'OK', 'Error')" >NUL 2>&1
EXIT /B 0
