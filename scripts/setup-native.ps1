$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $root
& uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw 'Python environment setup failed' }
if (-not (Test-Path -LiteralPath '.env')) {
    & uv run python scripts/init-local.py
    if ($LASTEXITCODE -ne 0) { throw 'Local configuration setup failed' }
}
$wslPath = '/mnt/' + $root.Substring(0,1).ToLower() + $root.Substring(2).Replace('\','/')
& wsl.exe -d Ubuntu -u root -- bash "$wslPath/scripts/setup-native-services.sh"
if ($LASTEXITCODE -ne 0) { throw 'Native service setup failed' }
New-Item -ItemType Directory -Force -Path 'instance','output' | Out-Null
$pidFile = Join-Path $root 'instance\native-supervisor.pid'
$alive = $false
if (Test-Path -LiteralPath $pidFile) {
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId = $([int](Get-Content $pidFile))"
    $alive = $existing -and $existing.CommandLine -like '*run-native-services.sh*'
}
if (-not $alive) {
    $p = Start-Process -FilePath wsl.exe -ArgumentList @('-d','Ubuntu','-u','root','--','bash',"$wslPath/scripts/run-native-services.sh") -WindowStyle Hidden -PassThru
    $p.Id | Set-Content -LiteralPath $pidFile
}
& uv run python scripts/setup-native-database.py
if ($LASTEXITCODE -ne 0) { throw 'Native database setup failed' }
& uv run flask --app wsgi db upgrade
if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
if (-not (Test-Path -LiteralPath 'instance\tools\mailpit.exe')) {
    & uv run python scripts/install-mailpit.py
    if ($LASTEXITCODE -ne 0) { throw 'Local mail setup failed' }
}
& npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed' }
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
& (Join-Path $PSScriptRoot 'start-native.ps1')
