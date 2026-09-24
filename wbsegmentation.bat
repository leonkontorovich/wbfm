@echo off
SETLOCAL
CALL "%~dp0launcher_settings.bat"
"%WBFM_PYTHON%" -X utf8 "%WBFM_ROOT%\wbsegmentation.py" %*
