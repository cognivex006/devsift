$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$base = 'https://github.com/orchex006/devsift/releases/latest/download'
$devsiftTemp = Join-Path ([IO.Path]::GetTempPath()) ('devsift-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $devsiftTemp | Out-Null
try {
    $python = $null
    foreach ($candidate in @('python', 'python3', 'py')) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            try {
                # Windows PowerShell 5.1 strips embedded double quotes in native
                # arguments. Keep the Python expression free of string literals.
                $probe = & $candidate -I -B -c 'import sys; sys.exit(1) if sys.version_info < (3,12) else print(sys.executable)' 2>$null
            } catch {
                # A broken PATH candidate must not prevent trying python3/py.
                continue
            }
            if ($LASTEXITCODE -eq 0 -and $probe) { $python = $probe.Trim(); break }
        }
    }
    if (-not $python) { throw 'Install Python 3.12 or later, then run this installer again.' }
    $archive = Join-Path $devsiftTemp 'devsift-install.zip'
    Invoke-WebRequest "$base/devsift-install.zip" -OutFile $archive -UseBasicParsing
    $checksum = (Invoke-WebRequest "$base/devsift-install.zip.sha256" -UseBasicParsing).Content
    if ($checksum -is [byte[]]) { $checksum = [Text.Encoding]::UTF8.GetString($checksum) }
    if ($checksum -notmatch '^([a-f0-9]{64})  devsift-install\.zip\s*$') { throw 'Invalid release checksum file.' }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Matches[1]) {
        throw 'Release checksum mismatch. Existing installation was not changed.'
    }
    $bundle = Join-Path $devsiftTemp 'bundle'
    Expand-Archive -LiteralPath $archive -DestinationPath $bundle
    & $python -I -B (Join-Path $bundle 'install.py')
    if ($LASTEXITCODE -ne 0) { throw 'DevSift installation failed.' }
    $bin = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.local\bin'
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($bin -notin ($userPath -split ';')) {
        [Environment]::SetEnvironmentVariable('Path', "$bin;$userPath", 'User')
    }
    if ($bin -notin ($env:Path -split ';')) { $env:Path = "$bin;$env:Path" }
    Write-Host 'Ready. Open a new terminal and run: devsift --help'
} finally {
    # The target was created above using a unique name under the OS temp directory.
    $resolvedTemp = [IO.Path]::GetFullPath($devsiftTemp)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if ($resolvedTemp.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
}
