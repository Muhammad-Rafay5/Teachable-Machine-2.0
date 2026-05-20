@echo off
title Restore Antigravity Chat History
echo ===================================================
echo   Restoring Antigravity Chat History...
echo ===================================================
echo.
echo Please make sure the Antigravity IDE is completely closed before proceeding.
echo.
pause

set "SRC_BACKUP=C:\Users\SJ Computers\.gemini\antigravity-backup"
set "SRC_IDE=C:\Users\SJ Computers\.gemini\antigravity-ide"
set "DEST=C:\Users\SJ Computers\.gemini\antigravity"

echo Checking source directories...

if exist "%SRC_BACKUP%" (
    echo Found backup history in antigravity-backup. Restoring from there...
    
    echo Copying conversations...
    xcopy "%SRC_BACKUP%\conversations" "%DEST%\conversations" /E /I /Y /H /R
    
    echo Copying brain transcripts and logs...
    xcopy "%SRC_BACKUP%\brain" "%DEST%\brain" /E /I /Y /H /R
    
    echo Copying HTML artifacts...
    xcopy "%SRC_BACKUP%\html_artifacts" "%DEST%\html_artifacts" /E /I /Y /H /R
    
    echo Copying other settings and tracker info...
    if exist "%SRC_BACKUP%\mcp_config.json" copy "%SRC_BACKUP%\mcp_config.json" "%DEST%\" /Y
    if exist "%SRC_BACKUP%\user_settings.pb" copy "%SRC_BACKUP%\user_settings.pb" "%DEST%\" /Y
    if exist "%SRC_BACKUP%\installation_id" copy "%SRC_BACKUP%\installation_id" "%DEST%\" /Y
    xcopy "%SRC_BACKUP%\code_tracker" "%DEST%\code_tracker" /E /I /Y /H /R
    xcopy "%SRC_BACKUP%\context_state" "%DEST%\context_state" /E /I /Y /H /R
    xcopy "%SRC_BACKUP%\knowledge" "%DEST%\knowledge" /E /I /Y /H /R
    xcopy "%SRC_BACKUP%\playground" "%DEST%\playground" /E /I /Y /H /R
    xcopy "%SRC_BACKUP%\browser_recordings" "%DEST%\browser_recordings" /E /I /Y /H /R
    xcopy "%SRC_BACKUP%\implicit" "%DEST%\implicit" /E /I /Y /H /R
) else if exist "%SRC_IDE%" (
    echo Found backup history in antigravity-ide. Restoring from there...
    
    echo Copying conversations...
    xcopy "%SRC_IDE%\conversations" "%DEST%\conversations" /E /I /Y /H /R
    
    echo Copying brain transcripts and logs...
    xcopy "%SRC_IDE%\brain" "%DEST%\brain" /E /I /Y /H /R
    
    echo Copying HTML artifacts...
    xcopy "%SRC_IDE%\html_artifacts" "%DEST%\html_artifacts" /E /I /Y /H /R
    
    echo Copying other settings and tracker info...
    if exist "%SRC_IDE%\mcp_config.json" copy "%SRC_IDE%\mcp_config.json" "%DEST%\" /Y
    if exist "%SRC_IDE%\user_settings.pb" copy "%SRC_IDE%\user_settings.pb" "%DEST%\" /Y
    if exist "%SRC_IDE%\installation_id" copy "%SRC_IDE%\installation_id" "%DEST%\" /Y
    xcopy "%SRC_IDE%\code_tracker" "%DEST%\code_tracker" /E /I /Y /H /R
    xcopy "%SRC_IDE%\context_state" "%DEST%\context_state" /E /I /Y /H /R
    xcopy "%SRC_IDE%\knowledge" "%DEST%\knowledge" /E /I /Y /H /R
    xcopy "%SRC_IDE%\playground" "%DEST%\playground" /E /I /Y /H /R
    xcopy "%SRC_IDE%\browser_recordings" "%DEST%\browser_recordings" /E /I /Y /H /R
    xcopy "%SRC_IDE%\implicit" "%DEST%\implicit" /E /I /Y /H /R
) else (
    echo ERROR: Could not find any backup source directory!
    echo Checked:
    echo 1. %SRC_BACKUP%
    echo 2. %SRC_IDE%
    pause
    exit /b 1
)

echo.
echo ===================================================
echo   History restoration completed successfully!
echo   You can now reopen your Antigravity IDE.
echo ===================================================
echo.
pause
