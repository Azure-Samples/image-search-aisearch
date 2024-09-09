Write-Host 'Creating python virtual environment "backend/backend_env"'
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
  # fallback to python3 if python not found
  $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}
Start-Process -FilePath ($pythonCmd).Source -ArgumentList "-m venv ./backend/backend_env" -Wait -NoNewWindow

Write-Host ""
Write-Host "Restoring backend python packages"
Write-Host ""

$venvPythonPath = "./venv/scripts/python.exe"
if (Test-Path -Path "/usr") {
  # fallback to Linux venv path
  $venvPythonPath = "./venv/bin/python"
}

Start-Process -FilePath $venvPythonPath -ArgumentList "-m pip install -r app/backend/requirements.txt" -Wait -NoNewWindow
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to restore backend python packages"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Restoring frontend npm packages"
Write-Host ""
Set-Location ../frontend
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to restore frontend npm packages"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Building frontend"
Write-Host ""
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to build frontend"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Starting backend"
Write-Host ""
Set-Location ../backend

$port = 50505
$hostname = "localhost"
Start-Process -FilePath $venvPythonPath -ArgumentList "-m quart --app main:app run --port $port --host $hostname --reload" -Wait -NoNewWindow

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to start backend"
    exit $LASTEXITCODE
}
