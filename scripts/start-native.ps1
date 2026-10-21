$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $root
New-Item -ItemType Directory -Force -Path (Join-Path $root 'instance'),(Join-Path $root 'output') | Out-Null

function Start-TrackedProcess($name, $exe, $arguments) {
    $pidPath = Join-Path $root "instance\$name.pid"
    if (Test-Path -LiteralPath $pidPath) {
        $old = Get-Process -Id ([int](Get-Content -LiteralPath $pidPath)) -ErrorAction SilentlyContinue
        if ($old -and $old.Path -eq $exe) { Write-Output "$name already running"; return }
    }
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root "output\$name.log") -RedirectStandardError (Join-Path $root "output\$name.error.log")
    $process.Id | Set-Content -LiteralPath $pidPath
    Write-Output "$name started (PID $($process.Id))"
}

$wslPath = '/mnt/' + $root.Substring(0,1).ToLower() + $root.Substring(2).Replace('\','/')
Start-TrackedProcess 'native-supervisor' "$env:SystemRoot\System32\wsl.exe" @('-d','Ubuntu','-u','root','--','bash',"$wslPath/scripts/run-native-services.sh")
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run uv sync --frozen first' }
& $python -m flask --app wsgi check-services --wait 30
if ($LASTEXITCODE -ne 0) { throw 'Native infrastructure is not ready; run setup steps in README' }
$mailpit = Join-Path $root 'instance\tools\mailpit.exe'
if (-not (Test-Path -LiteralPath $mailpit)) { throw 'Run uv run python scripts/install-mailpit.py first' }
Start-TrackedProcess 'native-mailpit' $mailpit @('--listen','127.0.0.1:8026','--smtp','127.0.0.1:1026','--disable-version-check','--quiet')
Start-TrackedProcess 'native-web' $python @('-m','flask','--app','wsgi','run','--host','127.0.0.1','--port','8000','--no-debugger','--no-reload')
Start-TrackedProcess 'native-worker' $python @('-m','app.worker')
Write-Output 'App: http://127.0.0.1:8000 | Local mail: http://127.0.0.1:8026'
