@echo off
echo === NFL Frontend Build + Deploy ===
echo.
cd /d "C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND"
echo Building...
call npm run build
if %errorlevel% neq 0 (
    echo BUILD FAILED with exit code %errorlevel%
    exit /b %errorlevel%
)
echo.
echo Build succeeded.
echo.
echo Syncing to GCS...
gsutil -m rsync -r -d dist/ gs://nfl-frontend-nfl-model-471509/
if %errorlevel% neq 0 (
    echo GCS SYNC FAILED
    exit /b %errorlevel%
)
echo.
echo Invalidating CDN cache...
gcloud compute url-maps invalidate-cdn-cache --path="/*" --global nfl-frontend-url-map --project=nfl-model-471509
echo.
echo === Deploy complete ===
