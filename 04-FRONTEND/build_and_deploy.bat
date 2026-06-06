@echo off
cd /d "C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND"
echo === Running npm build ===
call npm run build
if %ERRORLEVEL% NEQ 0 (
  echo BUILD FAILED with exit code %ERRORLEVEL%
  exit /b %ERRORLEVEL%
)
echo === Build succeeded ===
echo === Listing dist/assets ===
dir dist\assets\
echo === Syncing to GCS ===
gsutil -m rsync -r -d dist/ gs://nfl-frontend-nfl-model-471509/
if %ERRORLEVEL% NEQ 0 (
  echo GSUTIL SYNC FAILED
  exit /b %ERRORLEVEL%
)
echo === Setting cache headers ===
gsutil setmeta -h "Cache-Control:no-cache, no-store, must-revalidate" gs://nfl-frontend-nfl-model-471509/index.html
gsutil -m setmeta -h "Cache-Control:public, max-age=31536000, immutable" "gs://nfl-frontend-nfl-model-471509/assets/**"
echo === DEPLOY COMPLETE ===
