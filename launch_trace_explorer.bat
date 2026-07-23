@echo off
REM Launch the trace explorer GUI for whole-brain recording visualization
REM Usage: launch_trace_explorer.bat [project_config_path]
REM   Default path: Z:\neurobiology\zimmer\LeonK\25_degrees_npr-1_vs_rde4\AX10059worm1-2026-04-10\project_config.yaml

CALL "C:\Users\Zim_Admin\Miniforge3\condabin\mamba.bat" activate gui_only
SET SCRIPT=C:\GithubRepositories\wbfm\wbfm\gui\trace_explorer.py

IF "%~1"=="" (
    echo.
    set /p PROJECT_PATH="Please drag and drop your project folder here, then press ENTER: "
) ELSE (
    SET PROJECT_PATH=%~1
)

REM Strip surrounding quotes in case the user dragged and dropped
SET PROJECT_PATH=%PROJECT_PATH:"=%

echo Starting trace explorer for: %PROJECT_PATH%
echo This may take several minutes to load...

python "%SCRIPT%" --project_path "%PROJECT_PATH%" --force_tracklets_to_be_sparse --load_tracklets --DEBUG True

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: The trace explorer exited with an error. See output above.
    pause
)
