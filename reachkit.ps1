$ErrorActionPreference = 'Stop'
$taskPython = $env:REACHKIT_PYTHON
if (-not $taskPython) {
    $taskLocalPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $taskBundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $taskLocalPython) {
        $taskPython = $taskLocalPython
    } else {
        $taskCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($taskCommand) { $taskPython = $taskCommand.Source }
        elseif (Test-Path -LiteralPath $taskBundledPython) { $taskPython = $taskBundledPython }
    }
}
if (-not $taskPython) { throw 'Install Python 3.10+ or set REACHKIT_PYTHON to python.exe.' }
Push-Location $PSScriptRoot
try {
    & $taskPython -X utf8 -c 'import requests, feedparser, dotenv, loguru, yaml, rich, yt_dlp' 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw '联网找资料助手 dependencies are missing. Run .\setup.ps1, or install this project with the selected Python.'
    }
    & $taskPython -X utf8 -m reachkit @args
    $taskExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $taskExitCode
