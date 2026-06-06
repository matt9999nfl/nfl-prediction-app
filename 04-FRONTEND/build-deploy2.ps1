# Explicitly set PATH to include Node.js and Google Cloud SDK
$env:PATH = "C:\Program Files\nodejs;C:\Users\Matth\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin;" + $env:PATH
$logFile = "C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND\build-deploy2.log"
"" | Out-File $logFile
function Log($msg) { 
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "$ts $msg"
    Write-Host $line
    $line | Out-File $logFile -Append
}
Log "PATH set. npm location: $(Get-Command npm -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)"
Log "gsutil location: $(Get-Command gsutil -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)"
Set-Location "C:\Users\Matth\Desktop\nfl-prediction-app\04-FRONTEND"
Log "=== Building ==="
$buildOut = & npm run build 2>&1
$buildOut | ForEach-Object { Log $_ }
Log "Build exit code: $LASTEXITCODE"
if ($LASTEXITCODE -ne 0) { Log "BUILD FAILED"; exit 1 }
Log "=== Syncing to GCS ==="
$syncOut = & gsutil -m rsync -r -d dist/ gs://nfl-frontend-nfl-model-471509/ 2>&1
$syncOut | ForEach-Object { Log $_ }
Log "Sync exit code: $LASTEXITCODE"
if ($LASTEXITCODE -ne 0) { Log "SYNC FAILED"; exit 1 }
Log "=== Setting cache headers ==="
& gsutil setmeta -h "Cache-Control:no-cache, no-store, must-revalidate" gs://nfl-frontend-nfl-model-471509/index.html 2>&1 | ForEach-Object { Log $_ }
& gsutil -m setmeta -h "Cache-Control:public, max-age=31536000, immutable" "gs://nfl-frontend-nfl-model-471509/assets/**" 2>&1 | ForEach-Object { Log $_ }
Log "=== DEPLOY COMPLETE ==="
