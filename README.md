# twitch-tts

## Usage (Release)

1. Download the zip from the [latest release](https://github.com/Zutatensuppe/twitch-tts/releases/latest)
2. Unzip the zip and adjust the `config.jsonc` file.
3. Launch `tts.exe`

## Usage (Development)

1. Install prerequisites

    - [python3](https://www.python.org/downloads/)
    - [poetry](https://python-poetry.org/docs/)

2. Install dependencies

    ```shell
    poetry install
    ```

3. Copy `config_example.jsonc` to `config.jsonc` and adjust it where needed.

    Required places are marked with `PLEASE_CONFIGURE`. The rest can be changed
    as needed.

4. Run the bot

    ```shell
    poetry run python run.py
    ```

## Thanks

- [twitchTransFreeNext](https://github.com/sayonari/twitchTransFreeNext) by sayonari
- [google_trans_new](https://github.com/lushan88a/google_trans_new) by lushan88a
