@echo off
title Pushing changes to MohitGoyal09/ao-hack...
cd /d D:\demo\ao-hack
echo ========================================================
echo Staging and pushing changes to GitHub...
echo ========================================================

echo [1/3] Staging all files...
git add .

echo [2/3] Creating commit...
git commit -m "docs: add logo & Mermaid architecture diagram to README, fix frontend hydration & dev overlay"

echo [3/3] Pushing to origin main...
git push origin main

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo SUCCESS! Changes pushed to:
    echo https://github.com/MohitGoyal09/ao-hack
    echo ========================================================
) else (
    echo.
    echo Push failed. If needed, pull first with: git pull --rebase origin main
)
pause
