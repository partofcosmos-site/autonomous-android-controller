@echo off
REM ==============================================================================
REM Autonomous Android Controller - Windows CLI Remote Execution Wrapper
REM ==============================================================================
python "%~dp0master_agent.py" %*
exit /b %errorlevel%
