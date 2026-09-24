# Foreground-only launcher. Nothing starts unless a server is explicitly selected.
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'backend', 'frontend')]
    [string]$Server = 'help',
    [switch]$Reload
)

$ErrorActionPreference = 'Stop'
if ($Server -eq 'help') {
    Write-Output 'Nothing started. Choose one server in each terminal:'
    Write-Output '  .\start-local.ps1 backend'
    Write-Output '  .\start-local.ps1 frontend'
    Write-Output 'Optional backend code watching: .\start-local.ps1 backend -Reload'
    Write-Output 'Press Ctrl+C in that same terminal to stop its server.'
    return
}
if ($Reload -and $Server -ne 'backend') {
    throw '-Reload applies only to the backend. Vite already watches frontend code while running.'
}

$projectPath = $PSScriptRoot
$port = if ($Server -eq 'backend') { 8000 } else { 5173 }
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $port is occupied. Stop the existing server in its own terminal first. No process was stopped or replaced."
}

Push-Location -LiteralPath $projectPath
try {
    if ($Server -eq 'backend') {
        $pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
        if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Backend dependencies are missing. Follow the one-time setup in README.md.' }
        $apiArgs = @('-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000')
        if (Test-Path -LiteralPath (Join-Path $projectPath '.env')) { $apiArgs += @('--env-file', '.env') }
        if ($Reload) { $apiArgs += @('--reload', '--reload-dir', (Join-Path $projectPath 'backend')) }
        Write-Output 'Backend runs in THIS terminal. Ctrl+C stops it. API: http://127.0.0.1:8000/docs'
        & $pythonPath @apiArgs
    } else {
        $vitePath = Join-Path $projectPath 'frontend\node_modules\vite\bin\vite.js'
        if (!(Test-Path -LiteralPath $vitePath)) { throw 'Frontend dependencies are missing. Run npm.cmd ci in the frontend folder.' }
        $nodePath = (Get-Command node.exe -ErrorAction Stop).Source
        Set-Location -LiteralPath (Join-Path $projectPath 'frontend')
        Write-Output 'Frontend runs in THIS terminal. Ctrl+C stops it. Website: http://127.0.0.1:5173'
        & $nodePath $vitePath --host 127.0.0.1 --port 5173 --strictPort
    }
} finally {
    Pop-Location
}
