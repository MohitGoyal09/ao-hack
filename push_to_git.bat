@echo off
echo =========================================================
echo [RUX] Syncing Assets and Pushing to MohitGoyal09/ao-hack
echo =========================================================

echo [1/5] Copying logo assets from D:\landing...
if exist "D:\landing\logo.png" (
    copy /Y "D:\landing\logo.png" "D:\ao-hack-work\landing_page\logo.png" >nul
    copy /Y "D:\landing\logo.png" "D:\ao-hack-work\landing_page\public\logo.png" >nul
    echo      Logo assets copied to landing_page.
)

echo [2/5] Entering repository directory D:\ao-hack-work...
cd /d "D:\ao-hack-work"

echo [3/5] Pulling latest changes from MohitGoyal09/ao-hack...
git pull --rebase origin main

echo [4/5] Staging all changes...
git add .
git commit -m "feat(landing): complete design overhaul with 2x logo, green borders, and interactive workflow console"

echo [5/5] Pushing to MohitGoyal09/ao-hack on branch main...
git push origin main

echo =========================================================
echo Done! Check https://github.com/MohitGoyal09/ao-hack/commits/main/
echo =========================================================
pause
