# this is a very simple powershell script to create a release
If (Test-Path "build") { rm -r -fo build }
If (Test-Path "dist") { rm -r -fo dist }
$buildVersionFile = Join-Path $PSScriptRoot "src/twitch_tts/_build_version.py"
$defaultBuildVersionFile = @"
# Auto-generated during release builds.
BUILD_VERSION = None
"@

function Get-BuildVersion {
    if ($env:GITHUB_REF_TYPE -eq "tag" -and $env:GITHUB_REF_NAME) {
        return $env:GITHUB_REF_NAME.Trim()
    }

    $exactTag = git describe --tags --exact-match 2>$null
    if ($LASTEXITCODE -eq 0 -and $exactTag) {
        return $exactTag.Trim()
    }

    $describedVersion = git describe --tags --always --dirty 2>$null
    if ($LASTEXITCODE -eq 0 -and $describedVersion) {
        return $describedVersion.Trim()
    }

    return (uv run python -c "from twitch_tts.versioning import get_version; print(get_version())").Trim()
}

$buildVersion = Get-BuildVersion
$buildVersionLiteral = $buildVersion | ConvertTo-Json -Compress

Set-Content -Path $buildVersionFile -Value @"
# Auto-generated during release builds.
BUILD_VERSION = $buildVersionLiteral
"@

try {
    uv run pyinstaller run.spec
    uv run pyinstaller gui.spec
    cp config_example.jsonc dist/config.jsonc

    Push-Location dist
    mv run.exe tts.exe
    7z a -tzip ../build/twitch-tts-$buildVersion.zip *
    Pop-Location
}
finally {
    Set-Content -Path $buildVersionFile -Value $defaultBuildVersionFile
}
