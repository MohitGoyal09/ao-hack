@echo off
echo =========================================================
echo [RUX] Syncing Assets and Pushing to MohitGoyal09/ao-hack
echo =========================================================

echo [1/5] Syncing complete landing directory to repository landing_page...
if exist "D:\landing\src" (
    xcopy /E /I /Y "D:\landing\src" "D:\ao-hack-work\landing_page\src" >nul 2>&1
    xcopy /E /I /Y "D:\landing\public" "D:\ao-hack-work\landing_page\public" >nul 2>&1
    copy /Y "D:\landing\preview.html" "D:\ao-hack-work\landing_page\preview.html" >nul 2>&1
    copy /Y "D:\landing\package.json" "D:\ao-hack-work\landing_page\package.json" >nul 2>&1
    copy /Y "D:\landing\vercel.json" "D:\ao-hack-work\landing_page\vercel.json" >nul 2>&1
    copy /Y "D:\landing\vite.config.js" "D:\ao-hack-work\landing_page\vite.config.js" >nul 2>&1
    copy /Y "D:\landing\index.html" "D:\ao-hack-work\landing_page\index.html" >nul 2>&1
    copy /Y "D:\landing\logo.png" "D:\landing\public\logo.png" >nul 2>&1
    copy /Y "D:\landing\logo.png" "D:\ao-hack-work\landing_page\logo.png" >nul 2>&1
    copy /Y "D:\landing\logo.png" "D:\ao-hack-work\landing_page\public\logo.png" >nul 2>&1
    echo      Complete landing page codebase, assets, and Vercel configs synchronized!
)

echo [2/5] Entering repository directory D:\ao-hack-work...
cd /d "D:\ao-hack-work"

echo [3/5] Pulling latest changes from MohitGoyal09/ao-hack...
git pull --rebase origin main

echo [4/5] Staging and committing all files...
git add -A
git commit -m "feat(landing): complete production landing page with Dark Cluster 3D shards, enhanced build status & Vercel deployment config"

echo [5/5] Pushing to MohitGoyal09/ao-hack on branch main...
git push origin main

echo =========================================================
echo Done! Check https://github.com/MohitGoyal09/ao-hack/commits/main/
echo =========================================================
pause
