@echo off
REM Daily sync for coming-soon games: adds new coming_soon titles, marks
REM launched ones, and backfills Steam store tags for anything still
REM missing them. Registered as a Windows Task Scheduler job — see
REM setup_daily_task.ps1 in this folder.

cd /d "%~dp0"
python -u scrape_upcoming_releases.py >> logs\upcoming_sync.log 2>&1
