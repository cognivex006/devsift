$ErrorActionPreference = 'Stop'
$previousProgressPreference = $ProgressPreference
$ProgressPreference = 'SilentlyContinue'
$base = 'https://github.com/orchex006/devsift/releases/latest/download'
$devsiftTemp = Join-Path ([IO.Path]::GetTempPath()) ('devsift-' + [guid]::NewGuid())
$setupStage = 'Checking Python 3.12+'
$showSetupProgress = -not [Console]::IsErrorRedirected
function Show-DevSiftProgress([int] $Percent, [string] $Stage) {
    $script:setupStage = $Stage
    if ($showSetupProgress) {
        $ProgressPreference = 'Continue'
        Write-Progress -Id 71 -Activity 'DevSift setup' -Status "$Percent% setup | $Stage" -PercentComplete $Percent
    }
}
function Receive-DevSiftFile([string] $Url, [string] $Destination, [int] $Start, [int] $End, [string] $Label) {
    Show-DevSiftProgress $Start "$Label (connecting)"
    $request = [Net.HttpWebRequest]::Create($Url)
    $request.UserAgent = 'DevSift setup'
    $request.Timeout = 60000
    $response = $null; $inputStream = $null; $outputStream = $null
    try {
        $response = $request.GetResponse()
        $inputStream = $response.GetResponseStream()
        $outputStream = [IO.File]::Create($Destination)
        $buffer = New-Object byte[] 32768
        [long] $received = 0
        [long] $total = $response.ContentLength
        if ($total -gt 0) { Show-DevSiftProgress $Start "$Label | 0% (0 / $total bytes)" }
        while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $outputStream.Write($buffer, 0, $count)
            $received += $count
            if ($total -gt 0) {
                $transferPercent = [Math]::Min(100, [Math]::Floor(100 * $received / $total))
                $overall = $Start + [int](($End - $Start) * $transferPercent / 100)
                Show-DevSiftProgress $overall "$Label | $transferPercent% ($received / $total bytes)"
            } else {
                Show-DevSiftProgress $Start "$Label | size unknown ($received bytes received)"
            }
        }
        if ($total -ge 0 -and $received -ne $total) { throw 'Download ended before all declared bytes arrived.' }
        Show-DevSiftProgress $End "$Label complete ($received bytes)"
    } finally {
        if ($outputStream) { $outputStream.Dispose() }
        if ($inputStream) { $inputStream.Dispose() }
        if ($response) { $response.Dispose() }
    }
}
New-Item -ItemType Directory -Path $devsiftTemp | Out-Null
try {
    Show-DevSiftProgress 0 $setupStage
    $python = $null
    foreach ($candidate in @('python', 'python3', 'py')) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            try {
                # No quoted string literals: Windows PowerShell 5.1 strips them.
                $probe = & $candidate -I -B -c 'import sys; sys.exit(1) if sys.version_info < (3,12) else print(sys.executable)' 2>$null
            } catch { continue }
            if ($LASTEXITCODE -eq 0 -and $probe) { $python = $probe.Trim(); break }
        }
    }
    if (-not $python) { throw 'Install Python 3.12 or later, then run this installer again.' }
    Show-DevSiftProgress 8 'Python ready'
    $archive = Join-Path $devsiftTemp 'devsift-install.zip'
    Receive-DevSiftFile "$base/devsift-install.zip" $archive 8 40 'Downloading DevSift'
    $checksumPath = Join-Path $devsiftTemp 'devsift-install.zip.sha256'
    Receive-DevSiftFile "$base/devsift-install.zip.sha256" $checksumPath 40 44 'Downloading checksum'
    Show-DevSiftProgress 45 'Verifying SHA256'
    $checksum = [IO.File]::ReadAllText($checksumPath)
    if ($checksum -notmatch '^([a-f0-9]{64})  devsift-install\.zip\s*$') { throw 'Invalid release checksum file.' }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Matches[1]) {
        throw 'Release checksum mismatch. Existing installation was not changed.'
    }
    Show-DevSiftProgress 50 'Extracting verified bundle'
    $bundle = Join-Path $devsiftTemp 'bundle'
    Expand-Archive -LiteralPath $archive -DestinationPath $bundle
    Show-DevSiftProgress 55 'Starting installation'
    $process = New-Object Diagnostics.Process
    $processStarted = $false
    try {
        $process.StartInfo.FileName = $python
        $process.StartInfo.Arguments = '-I -B "' + (Join-Path $bundle 'install.py') + '" --progress json'
        $process.StartInfo.UseShellExecute = $false
        $process.StartInfo.CreateNoWindow = $true
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        $processStarted = $process.Start()
        $errors = $process.StandardError.ReadToEndAsync()
        $installState = $null
        while ($null -ne ($line = $process.StandardOutput.ReadLine())) {
            try { $event = $line | ConvertFrom-Json } catch { throw 'Installer returned an invalid status message.' }
            if ($event.type -eq 'progress') {
                Show-DevSiftProgress (55 + [int](39 * [Math]::Min(100, [Math]::Max(0, $event.percent)) / 100)) "$($event.stage) | $($event.elapsed)s"
            } elseif ($event.type -eq 'complete') {
                $installState = $event.state
            } elseif ($event.type -eq 'error') {
                throw "$($event.stage): $($event.message)"
            } else { throw 'Installer returned an unknown status message.' }
        }
        $process.WaitForExit()
        $null = $errors.Result
        if ($process.ExitCode -ne 0 -or -not $installState) { throw 'DevSift installation did not complete.' }
    } finally {
        if ($processStarted -and -not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
        $process.Dispose()
    }
    Show-DevSiftProgress 96 'Configuring command PATH'
    $bin = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.local\bin'
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($bin -notin ($userPath -split ';')) {
        [Environment]::SetEnvironmentVariable('Path', "$bin;$userPath", 'User')
    }
    if ($bin -notin ($env:Path -split ';')) { $env:Path = "$bin;$env:Path" }
    Show-DevSiftProgress 100 'Ready'
    Write-Host "DevSift $($installState.version) ready."
    Write-Host "CLI: $bin"
    Write-Host "Skills: $($installState.hosts -join ', ')"
    Write-Host 'Next: open a new terminal and agent session, then run devsift --help.'
} catch {
    Write-Host "DevSift setup failed during: $setupStage" -ForegroundColor Red
    throw
} finally {
    if ($showSetupProgress) {
        $ProgressPreference = 'Continue'
        Write-Progress -Id 71 -Activity 'DevSift setup' -Completed
    }
    $ProgressPreference = $previousProgressPreference
    $resolvedTemp = [IO.Path]::GetFullPath($devsiftTemp)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if ($resolvedTemp.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
}
