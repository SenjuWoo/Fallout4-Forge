@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run Fallout 4 Forge from this folder. Paths may hold spaces, "!" and parentheses:
rem no parenthesised blocks, so %ERRORLEVEL% is read after the program ran.
set "F4FORGE_ROOT=%~dp0"
if not exist "%F4FORGE_ROOT%.venv\Scripts\python.exe" goto :nopython
"%F4FORGE_ROOT%.venv\Scripts\python.exe" -m f4forge %*
exit /b %ERRORLEVEL%
:nopython
set "PYTHONPATH=%F4FORGE_ROOT%src;%PYTHONPATH%"
python -m f4forge %*
exit /b %ERRORLEVEL%
