rm -r -fo build
rm -r -fo dist
poetry run pyinstaller -F run.py
cp config_example.jsonc dist/config.jsonc
mv dist/run.exe dist/tts.exe
cd dist
7z a -tzip ../build/$(poetry version -s).zip *
gh release create $(poetry version -s) -t $(poetry version -s) -F build/$(poetry version -s).zip
