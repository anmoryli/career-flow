param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Run inside the CareerFlow repository' }
Set-Location -LiteralPath $root
$commit = (& git rev-parse 'careerflow-native-foundation^{commit}').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Native foundation checkpoint tag is missing' }
$dirty = & git status --porcelain
if ($dirty) { throw 'Preserve uncommitted changes before rollback' }
if (-not $Apply) {
    Write-Output "Rollback checkpoint: $commit"
    Write-Output 'Use -Apply to create a reversing Git commit. Database, .env and local data are retained.'
    exit 0
}
& git -c user.name='CareerFlow' -c user.email='dev@careerflow.local' revert --no-edit $commit
if ($LASTEXITCODE -ne 0) { throw 'Rollback did not finish; inspect Git status' }
Write-Output 'Source rollback completed. Application database and local configuration were retained.'
