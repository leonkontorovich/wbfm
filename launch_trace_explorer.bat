@echo off
SETLOCAL
REM Launch the trace explorer GUI for whole-brain recording visualization
REM Usage: launch_trace_explorer.bat [project_config_path]
REM   With no argument, prompts for a path; ENTER uses WBFM_DEFAULT_PROJECT
REM   (set it in launcher_settings.local.bat).

CALL "%~dp0launcher_settings.bat"
CALL "%WBFM_MAMBA%" activate %WBFM_ENV%
SET "SCRIPT=%WBFM_ROOT%\wbfm\gui\trace_explorer.py"

IF "%~1"=="" (
    echo.
    IF DEFINED WBFM_DEFAULT_PROJECT echo Default: %WBFM_DEFAULT_PROJECT%
    set "PROJECT_PATH="
    set /p "PROJECT_PATH=Drag and drop project folder here [or press ENTER for default]: "
) ELSE (
    SET PROJECT_PATH=%~1
)

IF "%PROJECT_PATH%"=="" SET "PROJECT_PATH=%WBFM_DEFAULT_PROJECT%"
IF "%PROJECT_PATH%"=="" (
    echo ERROR: No project path given and WBFM_DEFAULT_PROJECT is not set.
    pause
    exit /b 1
)

REM Strip surrounding quotes in case the user dragged and dropped
SET PROJECT_PATH=%PROJECT_PATH:"=%

echo Starting trace explorer for: %PROJECT_PATH%
echo This may take several minutes to load...

python -X utf8 "%SCRIPT%" --project_path "%PROJECT_PATH%" --force_tracklets_to_be_sparse --load_tracklets --DEBUG True

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: The trace explorer exited with an error. See output above.
    pause
)
