@echo off
REM Launcher for WBFM GUI with memory
echo Activating WBFM GUI environment...
CALL "C:\Users\Zim_Admin\Miniforge3\condabin\mamba.bat" activate gui_only

echo Launching WBFM Trace Explorer...
python -X utf8 "C:\GithubRepositories\wbfm\launch_gui.py" %*

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: The GUI exited with an error code %ERRORLEVEL%. See output above.
    pause
)
