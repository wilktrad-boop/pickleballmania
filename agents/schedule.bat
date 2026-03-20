@echo off
REM Pickleball Mania - Agent scheduler
REM Usage: schedule.bat [cycle|content|design]

cd /d "C:\Users\wilk7\Agents agents\pickleballmania"

if "%1"=="cycle" (
    echo [%date% %time%] Lancement du cycle complet >> agents\schedule.log
    python -m agents.orchestrator --cycle >> agents\schedule.log 2>&1
    echo [%date% %time%] Lancement agent design >> agents\schedule.log
    python -m agents.orchestrator --agent design >> agents\schedule.log 2>&1
) else if "%1"=="content" (
    echo [%date% %time%] Lancement agent content >> agents\schedule.log
    python -m agents.orchestrator --agent content >> agents\schedule.log 2>&1
) else if "%1"=="design" (
    echo [%date% %time%] Lancement agent design >> agents\schedule.log
    python -m agents.orchestrator --agent design >> agents\schedule.log 2>&1
) else (
    echo Usage: schedule.bat [cycle^|content^|design]
    exit /b 1
)

echo [%date% %time%] Termine >> agents\schedule.log
