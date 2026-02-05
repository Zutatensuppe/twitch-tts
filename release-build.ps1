# this is a very simple powershell script to create a release
If (Test-Path "build") { rm -r -fo build }
If (Test-Path "dist") { rm -r -fo dist }
uv run pyinstaller -F run.py
cp config_example.jsonc dist/config.jsonc
cd dist
mv run.exe tts.exe
$version = (uv run poetry version -s)
7z a -tzip ../build/twitch-tts-$version.zip *
cd ..
