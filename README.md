# twitch-tts

## Usage (Release)

1. Download the zip from the [latest release](https://github.com/Zutatensuppe/twitch-tts/releases/latest)
2. Unzip the zip and adjust the `config.jsonc` file.
3. Launch `tts.exe`

## Usage (Development)

1. Install prerequisites

    - [python3](https://www.python.org/downloads/)
    - [uv](https://docs.astral.sh/uv/)

2. Install dependencies

    ```shell
    uv sync --locked
    ```

3. Copy `config_example.jsonc` to `config.jsonc` and adjust it where needed.

    Required places are marked with `PLEASE_CONFIGURE`. The rest can be changed
    as needed.

4. Run the bot

    ```shell
    uv run python -m twitch_tts.run
    ```

## How to get the `Trans_OAUTH` required in the config.jsonc

1. In the browser login to twitch.tv with your account. Right click in
    the browser and click 'Inspect'
    ![1](docs/1.png)

2. Click the 'Network' tab
    ![2](docs/2.png)

3. There should be a 'Filter' input box, type gql in there
    ![3](docs/3.png)

4. Click one of the remaining rows, if there is no row, hit F5 once,
    and then click one of the rows
    ![4](docs/4.png)

5. More details and tabs for the row will appear. Click the Headers tab.
    ![5](docs/5.png)

6. Scroll down to find 'Authorization: OAuth BLABLABLABLABLA' in the
    Request Headers section. 'BLABLABLABLABLA' (blurred out
    in the screenshot) is what you have to use
    ![6](docs/6.png)

## Troubleshooting

Problem: I get an error "Invalid or unauthorized Access Token passed."

Answer: Please update the `Trans_OAUTH` value in the `config.jsonc`. Please refer to the [previous section](https://github.com/Zutatensuppe/twitch-tts?tab=readme-ov-file#how-to-get-the-trans_oauth-required-in-the-configjsonc) on how to get the current token.

## Thanks

- [twitchTransFreeNext](https://github.com/sayonari/twitchTransFreeNext) by sayonari
- [google_trans_new](https://github.com/lushan88a/google_trans_new) by lushan88a
