$ErrorActionPreference = 'Stop'
$logFile = "C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND\build-deploy.log"
function Log($msg) { $ts = Get-Date -Format "HH:mm:ss"; "$ts $msg" | Tee-Object -FilePath $logFile -Append }

Log "=== NFL Frontend Build + Deploy ==="
Set-Location "C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND"

Log "Running npm run build..."
& "C:\Program Files\nodejs\npm.cmd" run build 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) { Log "BUILD FAILED exit=$LASTEXITCODE"; exit $LASTEXITCODE }
Log "Build succeeded."

Log "Syncing dist/ to GCS bucket..."
$gsutil = "C:\Users\Matth\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gsutil.cmd"
& $gsutil -m rsync -r -d dist/ gs://nfl-frontend-nfl-model-471509/ 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) { Log "GCS SYNC FAILED exit=$LASTEXITCODE"; exit $LASTEXITCODE }
Log "GCS sync complete."

Log "Invalidating CDN cache..."
$gcloud = "C:\Users\Matth\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
& $gcloud compute url-maps invalidate-cdn-cache nfl-frontend-url-map --path="/*" --global --project=nfl-model-471509 2>&1 | ForEach-Object { Log $_ }
Log "CDN invalidation requested."
Log "=== Deploy complete ==="
