@echo off
setlocal
set NODE="C:\Program Files\nodejs\node.exe"
set GSUTIL="C:\Users\Matth\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gsutil"
set LOG=C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND\build-deploy5.log
set FRONTDIR=C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND

echo START %DATE% %TIME% > %LOG%
cd /d %FRONTDIR%

echo === Running tsc >> %LOG%
%NODE% node_modules\typescript\bin\tsc >> %LOG% 2>&1
echo tsc exit: %ERRORLEVEL% >> %LOG%
if %ERRORLEVEL% neq 0 goto :fail_tsc

echo === Running vite build >> %LOG%
%NODE% node_modules\vite\bin\vite.js build >> %LOG% 2>&1
echo vite exit: %ERRORLEVEL% >> %LOG%
if %ERRORLEVEL% neq 0 goto :fail_vite

echo === gsutil rsync >> %LOG%
%GSUTIL% -m rsync -r -d dist/ gs://nfl-frontend-nfl-model-471509/ >> %LOG% 2>&1
echo gsutil exit: %ERRORLEVEL% >> %LOG%
if %ERRORLEVEL% neq 0 goto :fail_gsutil

echo === cache headers >> %LOG%
%GSUTIL% setmeta -h "Cache-Control:no-cache, no-store, must-revalidate" gs://nfl-frontend-nfl-model-471509/index.html >> %LOG% 2>&1
%GSUTIL% -m setmeta -h "Cache-Control:public, max-age=31536000, immutable" "gs://nfl-frontend-nfl-model-471509/assets/**" >> %LOG% 2>&1

echo === DEPLOY COMPLETE %DATE% %TIME% >> %LOG%
exit /b 0

:fail_tsc
echo FAILED AT TSC >> %LOG%
exit /b 1

:fail_vite
echo FAILED AT VITE BUILD >> %LOG%
exit /b 1

:fail_gsutil
echo FAILED AT GSUTIL >> %LOG%
exit /b 1
