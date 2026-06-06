$env:PATH = "C:\Program Files\nodejs;C:\Users\Matth\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin;" + $env:PATH
$log = "C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND\build-deploy4.log"
Set-Content $log "START $(Get-Date)"
Set-Location "C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND"

Add-Content $log "=== Running tsc ==="
& "C:\Program Files\nodejs\node.exe" ".\node_modules\typescript\bin\tsc" *>> $log
$tscExit = $LASTEXITCODE
Add-Content $log "tsc_exit=$tscExit"
if ($tscExit -ne 0) { Add-Content $log "TSC FAILED"; exit 1 }

Add-Content $log "=== Running vite build ==="
& "C:\Program Files\nodejs\node.exe" ".\node_modules\vite\bin\vite.js" build *>> $log
$viteExit = $LASTEXITCODE
Add-Content $log "vite_exit=$viteExit"
if ($viteExit -ne 0) { Add-Content $log "VITE BUILD FAILED"; exit 1 }

Add-Content $log "=== gsutil rsync ==="
& "C:\Users\Matth\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gsutil" -m rsync -r -d dist/ gs://nfl-frontend-nfl-model-471509/ *>> $log
$gsExit = $LASTEXITCODE
Add-Content $log "gsutil_exit=$gsExit"
if ($gsExit -ne 0) { Add-Content $log "SYNC FAILED"; exit 1 }

Add-Content $log "=== cache: index.html no-cache ==="
& "C:\Users\Matth\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gsutil" setmeta -h "Cache-Control:no-cache, no-store, must-revalidate" gs://nfl-frontend-nfl-model-471509/index.html *>> $log

Add-Content $log "=== cache: assets immutable ==="
& "C:\Users\Matth\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gsutil" -m setmeta -h "Cache-Control:public, max-age=31536000, immutable" "gs://nfl-frontend-nfl-model-471509/assets/**" *>> $log

Add-Content $log "=== DEPLOY COMPLETE $(Get-Date) ==="
