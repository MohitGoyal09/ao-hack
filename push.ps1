Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "[RUX] Syncing Assets and Pushing Landing Page to Git" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

# 1. Copy logo
if (Test-Path "D:\landing\logo.png") {
    Copy-Item -Path "D:\landing\logo.png" -Destination "D:\ao-hack-work\landing_page\logo.png" -Force
    Copy-Item -Path "D:\landing\logo.png" -Destination "D:\ao-hack-work\landing_page\public\logo.png" -Force
    Write-Host "[1/4] Logo assets copied." -ForegroundColor Green
}

# 2. Change directory
Set-Location -Path "D:\ao-hack-work"

# 3. Add and commit
Write-Host "[2/4] Staging files..." -ForegroundColor Yellow
git add .
Write-Host "[3/4] Committing..." -ForegroundColor Yellow
git commit -m "feat(landing): complete design overhaul with 2x logo, green borders, tactile hover, and interactive workflow console"

# 4. Push
Write-Host "[4/4] Pushing to origin..." -ForegroundColor Yellow
git push origin HEAD

Write-Host "===================================================" -ForegroundColor Green
Write-Host "Push complete!" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Green
