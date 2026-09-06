@echo off
echo =========================================================
echo [RUX] Launching Rux Landing Page (Vite Dev Server)
echo =========================================================
cd /d "%~dp0"

echo Installing dependencies if needed...
call npm install

echo Starting dev server on http://localhost:5173...
start http://localhost:5173
call npm run dev
pause
