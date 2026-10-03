$ErrorActionPreference = 'Stop'
$taskPython = $env:REACHKIT_PYTHON
if (-not $taskPython) {
    $taskCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($taskCommand) { $taskPython = $taskCommand.Source }
    else {
        $taskCandidate = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $taskCandidate) { $taskPython = $taskCandidate }
    }
}
if (-not $taskPython) { throw 'Install Python 3.10+ or set REACHKIT_PYTHON to python.exe.' }
$taskVenv = Join-Path $PSScriptRoot '.venv'
if (-not (Test-Path -LiteralPath (Join-Path $taskVenv 'Scripts\python.exe'))) {
    & $taskPython -X utf8 -m venv $taskVenv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the project virtual environment.' }
}
$taskVenvPython = Join-Path $taskVenv 'Scripts\python.exe'
& $taskVenvPython -X utf8 -m pip install $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed. Check the network and package index.' }
Write-Host 'Installed 联网找资料助手 in the project .venv. Run .\找资料.ps1 doctor or .\找资料.ps1 skill --install.'
