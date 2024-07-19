rm -r -fo build
rm -r -fo dist
poetry run pyinstaller -F run.py
cp config_example.jsonc dist/config.jsonc
cd dist
mv run.exe tts.exe
7z a -tzip ../build/$(poetry version -s).zip *
cd ..
gh release create $(poetry version -s) -t $(poetry version -s) --generate-notes
gh release upload $(poetry version -s) build/$(poetry version -s).zip
