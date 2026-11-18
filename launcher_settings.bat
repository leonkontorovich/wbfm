@echo off
REM Shared settings for the WBFM Windows launchers (go.bat, wbsegmentation.bat,
REM launch_wbfm_gui.bat, launch_trace_explorer.bat). The defaults assume Miniforge
REM in the user profile and a conda env named gui_only.
REM To override them on one machine, create launcher_settings.local.bat next to this
REM file (it is gitignored) and SET any of the variables below, for example:
REM   SET "WBFM_CONDA_ROOT=D:\Miniforge3"
REM   SET "WBFM_DEFAULT_PROJECT=Z:\path\to\project_config.yaml"
REM Optional, read by the recording dashboard (launch_gui.py): ';'-separated parts of
REM folder names or paths that mark annotated reference recordings to compare against:
REM   SET "WBFM_REFERENCE_PATTERNS=reference_set;Z:\path\to\reference_recordings"
REM Optional, read by go.bat / wbsegmentation.bat without a folder argument: where to look for the newest recording
REM (default Z:\neurobiology\zimmer\LeonK\raw):
REM   SET "WBFM_RAW_ROOT=Z:\neurobiology\zimmer\LeonK\raw_incoming"

SET "WBFM_ROOT=%~dp0"
IF "%WBFM_ROOT:~-1%"=="\" SET "WBFM_ROOT=%WBFM_ROOT:~0,-1%"
SET "WBFM_CONDA_ROOT=%USERPROFILE%\Miniforge3"
SET "WBFM_ENV=gui_only"
SET "WBFM_DEFAULT_PROJECT="
SET "WBFM_PYTHON="
SET "WBFM_MAMBA="

IF EXIST "%~dp0launcher_settings.local.bat" CALL "%~dp0launcher_settings.local.bat"

REM Derived paths, unless launcher_settings.local.bat set them directly
IF NOT DEFINED WBFM_PYTHON SET "WBFM_PYTHON=%WBFM_CONDA_ROOT%\envs\%WBFM_ENV%\python.exe"
IF NOT DEFINED WBFM_MAMBA SET "WBFM_MAMBA=%WBFM_CONDA_ROOT%\condabin\mamba.bat"
