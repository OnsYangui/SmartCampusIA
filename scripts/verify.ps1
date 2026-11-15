# SmartCampus AI - safe local verification. Development data is never migrated or seeded.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/verify.ps1

param([switch]$InitializeRoles)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "apps\backend"
$Frontend = Join-Path $Root "apps\frontend"
$ComposeFile = Join-Path $Root "infra\docker-compose.yml"
$InfraEnv = Join-Path $Root "infra\.env"
$BackendEnv = Join-Path $Root "apps\backend\.env"
$MigrationEnv = Join-Path $Root "apps\backend\migrations\.env"

if (-not (Test-Path -LiteralPath $InfraEnv)) {
    # Replaying roles with template placeholders would overwrite the real role passwords.
    if ($InitializeRoles) { throw "-InitializeRoles requires infra/.env (copy infra/.env.example first)." }
    $InfraEnv = Join-Path $Root "infra\.env.example"
}
if (-not (Test-Path -LiteralPath $BackendEnv)) {
    $BackendEnv = Join-Path $Root "apps\backend\.env.example"
}
if (-not (Test-Path -LiteralPath $MigrationEnv)) {
    $MigrationEnv = Join-Path $Root "apps\backend\migrations\.env.example"
}

function Import-EnvDefaults([string]$Path) {
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { continue }
        $name = $Matches[1]
        if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
            [Environment]::SetEnvironmentVariable($name, $Matches[2].Trim(), "Process")
        }
    }
}

function Invoke-Native([string]$Directory, [string]$Executable, [string[]]$CommandArgs) {
    Push-Location $Directory
    try {
        & $Executable @CommandArgs
        if ($LASTEXITCODE -ne 0) {
            throw "$Executable exited with code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

Import-EnvDefaults $BackendEnv
Import-EnvDefaults $MigrationEnv
$ComposeArgs = @("compose", "--env-file", $InfraEnv, "-f", $ComposeFile)

Write-Host "[1/5] Docker Compose and PostgreSQL" -ForegroundColor Cyan
Invoke-Native $Root "docker" ($ComposeArgs + @("config", "--quiet"))
if ($InitializeRoles) {
    Invoke-Native $Root "docker" ($ComposeArgs + @("up", "-d", "db"))
    Invoke-Native $Root "docker" ($ComposeArgs + @(
        "exec", "-T", "db", "sh", "/docker-entrypoint-initdb.d/10-roles.sh"
    ))
} else {
    $RunningServices = (& docker @ComposeArgs ps --status running --services | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or ($RunningServices -split '\s+') -notcontains "db") {
        throw "PostgreSQL is not running. Start it explicitly, or rerun with -InitializeRoles."
    }
    Write-Host "Role initialization skipped (use -InitializeRoles to authorize it)." -ForegroundColor DarkGray
}

Write-Host "[2/5] Backend lint and tests (isolated test database)" -ForegroundColor Cyan
Invoke-Native $Backend "uv" @("run", "ruff", "check", ".")
Invoke-Native $Backend "uv" @("run", "ruff", "format", "--check", ".")
Invoke-Native $Backend "uv" @("run", "pytest", "-q")

Write-Host "[3/5] Alembic revision and PostgreSQL least privilege" -ForegroundColor Cyan
$PostgresUser = (& docker @ComposeArgs exec -T db printenv POSTGRES_USER | Out-String).Trim()
$PostgresDatabase = (& docker @ComposeArgs exec -T db printenv POSTGRES_DB | Out-String).Trim()
$TestDatabase = $PostgresDatabase + "_test"
$Revision = (& docker @ComposeArgs exec -T db psql -U $PostgresUser -d $TestDatabase `
    -tAc "SELECT version_num FROM alembic_version" | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $Revision -ne "0007") {
    throw "Expected Alembic revision 0007 in the test database, got '$Revision'"
}

$PermissionSql = "SELECT has_schema_privilege('smartcampus_owner', 'public', 'CREATE')" +
    " AND NOT has_schema_privilege('smartcampus_app', 'public', 'CREATE')" +
    " AND NOT has_table_privilege('smartcampus_app', 'documents', 'DELETE')" +
    " AND has_table_privilege('smartcampus_readonly', 'institutions', 'SELECT')" +
    " AND NOT has_table_privilege('smartcampus_readonly', 'institutions', 'INSERT')"
$Permissions = (& docker @ComposeArgs exec -T db psql -U $PostgresUser -d $TestDatabase `
    -tAc $PermissionSql | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $Permissions -ne "t") {
    throw "PostgreSQL role verification failed"
}

Write-Host "[4/5] Frontend lint and type checking" -ForegroundColor Cyan
Invoke-Native $Frontend "npm.cmd" @("run", "lint")
Invoke-Native $Frontend "npm.cmd" @("run", "typecheck")

Write-Host "[5/5] Frontend production build" -ForegroundColor Cyan
Invoke-Native $Frontend "npm.cmd" @("run", "build")

Write-Host "All checks passed. Development data was not modified." -ForegroundColor Green
