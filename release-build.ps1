# this is a very simple powershell script to create a release
rm -r -fo build
rm -r -fo dist
poetry run pyinstaller -F run.py
cp config_example.jsonc dist/config.jsonc
cd dist
mv run.exe tts.exe
$version = (poetry version -s)
7z a -tzip ../build/twitch-tts-$version.zip *
cd ..
