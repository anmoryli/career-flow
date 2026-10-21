$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
foreach ($name in @('native-web','native-worker','native-mailpit','native-supervisor')) {
    $pidPath = Join-Path $root "instance\$name.pid"
    if (-not (Test-Path -LiteralPath $pidPath)) { continue }
    $processId = [int](Get-Content -LiteralPath $pidPath)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
    if (-not $process) { continue }
    $expected = switch ($name) {
        'native-web' { 'flask' }
        'native-worker' { 'app.worker' }
        'native-mailpit' { 'mailpit' }
        'native-supervisor' { 'run-native-services.sh' }
    }
    if ($process.CommandLine -notlike "*$expected*") { throw "PID $processId no longer belongs to $name" }
    & taskkill.exe /PID $processId /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Stopping $name failed" }
    Write-Output "$name stopped"
}
# Stop only the dedicated Redis instance, leaving unrelated local Redis services untouched.
& wsl.exe -d Ubuntu -u root -- systemctl stop redis-careerflow
