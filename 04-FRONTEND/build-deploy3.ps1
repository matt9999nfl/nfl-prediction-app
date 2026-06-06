$env:PATH = "C:\Program Files\nodejs;C:\Users\Matth\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin;" + $env:PATH
$log = "C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND\build-deploy3.log"
Set-Content $log "START $(Get-Date)"

Set-Location "C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND"

Add-Content $log "=== npm run build ==="
npm run build *>> $log
Add-Content $log "npm_exit=$LASTEXITCODE"
if ($LASTEXITCODE -ne 0) { Add-Content $log "BUILD FAILED"; exit 1 }

Add-Content $log "=== gsutil rsync ==="
gsutil -m rsync -r -d dist/ gs://nfl-frontend-nfl-model-471509/ *>> $log
Add-Content $log "gsutil_exit=$LASTEXITCODE"
if ($LASTEXITCODE -ne 0) { Add-Content $log "SYNC FAILED"; exit 1 }

Add-Content $log "=== cache headers ==="
gsutil setmeta -h "Cache-Control:no-cache, no-store, must-revalidate" gs://nfl-frontend-nfl-model-471509/index.html *>> $log
gsutil -m setmeta -h "Cache-Control:public, max-age=31536000, immutable" "gs://nfl-frontend-nfl-model-471509/assets/**" *>> $log

Add-Content $log "=== DONE $(Get-Date) ==="
