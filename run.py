from google_translate import google_translator
import constants
import conf

import deepl
import logging
import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
import pygame
import queue
import random
import shutil
import signal
import sys
import threading
import time

from datetime import datetime
from gtts import gTTS
from twitchio import Client

version = "1.0.0"

pygame.mixer.init()

_user_to_language_map = {}

_conf = conf.load_config()

_tts_queue = queue.Queue()


def queue_tts(text: str, lang: str):
    global _tts_queue
    _tts_queue.put([text, lang])


def tts_thread_fn():
    global _tts_queue

    while True:
        q = _tts_queue.get()
        if q is None:
            time.sleep(1)
            continue

        text = q[0]
        tl = q[1]
        synthesize(text, tl)


def tts_thread():
    if _conf.TTS_IN or _conf.TTS_OUT:
        thread = threading.Thread(target=tts_thread_fn)
        thread.start()


def create_tmp_dir(tmp_dir: str):
    if os.path.exists(tmp_dir):
        du = shutil.rmtree(tmp_dir)
        time.sleep(0.3)

    os.mkdir(tmp_dir)
    log.debug("made tmp dir.")


##########################################
##########################################

logging.basicConfig()
log = logging.getLogger(__name__)
if _conf.Debug:
    log.setLevel(logging.DEBUG)


##########################################
##########################################
# Simple echo bot.
log.debug("XXX: simple echo bot")
bot = Client(
    token="oauth:" + _conf.Trans_OAUTH,
    initial_channels=[_conf.Twitch_Channel],
)
_translator = google_translator(url_suffix=_conf.url_suffix)


def replace_delete_words(message: str):
    for w in _conf.Delete_Words:
        message = message.replace(w, "")
    return message


def replace_emotes(message: str, ctx):
    if not ctx.tags or not ctx.tags["emotes"]:
        return message

    emote_list = []
    emotes_split = ctx.tags["emotes"].split("/")
    for emote in emotes_split:
        log.debug(emote)
        emote_id, emote_pos = emote.split(":")

        # 同一エモートが複数使われてたら，その数分，情報が入ってくる
        # （例：1110537:4-14,16-26）
        log.debug(f"e_pos:{emote_pos}")
        if "," in emote_pos:
            ed_pos = emote_pos.split(",")
            for e in ed_pos:
                log.debug(f"{e}")
                log.debug(e.split("-"))
                e_s, e_e = e.split("-")
                log.debug(ctx.content[int(e_s) : int(e_e) + 1])

                emote_list.append(ctx.content[int(e_s) : int(e_e) + 1])
        else:
            e = emote_pos
            e_s, e_e = e.split("-")
            log.debug(ctx.content[int(e_s) : int(e_e) + 1])

            emote_list.append(ctx.content[int(e_s) : int(e_e) + 1])

    log.debug(f"message with emote:{message}")
    for w in sorted(emote_list, key=len, reverse=True):
        log.debug(w)
        message = message.replace(w, "")

    log.debug(f"message without emote:{message}")
    return message


def determine_lang_detect(text: str, user: str) -> str:
    if user in _conf.UserToLangMap:
        return _conf.UserToLangMap[user]

    if _conf.AssignRandomLangToUser:
        if user not in _user_to_language_map:
            _user_to_language_map[user] = random.choice(_conf.AssignRandomLangToUser)
        return _user_to_language_map[user]

    if _conf.lang_SkipDetect:
        return _conf.lang_Default

    # use google translator ---
    try:
        detect_result = _translator.detect(text)
        log.debug(f"detect_result: {detect_result}")
        return detect_result[0]
    except Exception as e:
        log.debug(f"detect_exception: {e}")
        return ""


def determine_lang_dest(lang_detect: str) -> str:
    if lang_detect != _conf.lang_TransToHome:
        return _conf.lang_TransToHome
    return _conf.lang_HomeToOther


def translate_text_deepl(text: str, lang_detect: str, lang_dest: str) -> str:
    try:
        if (
            lang_detect in _conf.deepl_lang_dict.keys()
            and lang_dest in _conf.deepl_lang_dict.keys()
        ):
            log.debug(
                f"[DeepL Translate]({_conf.deepl_lang_dict[lang_detect]} > {_conf.deepl_lang_dict[lang_dest]})"
            )
            return deepl.translate(
                source_language=_conf.deepl_lang_dict[lang_detect],
                target_language=_conf.deepl_lang_dict[lang_dest],
                text=text,
            )

        return translate_text_google(text, lang_dest)
    except Exception as e:
        log.debug(e)
        return ""


def translate_text_google(text: str, lang_dest: str) -> str:
    try:
        log.debug("[Google Translate]")
        return _translator.translate(text, lang_dest)
    except Exception as e:
        log.debug(e)
        return ""


def translate_text(text: str, lang_detect: str, lang_dest: str) -> str:
    # use deepl --------------
    # (try to use deepl, but if the language is not supported, text will be translated by google!)
    if _conf.Translator == "deepl":
        return translate_text_deepl(text, lang_detect, lang_dest)

    # NOT use deepl ----------
    if _conf.Translator == "google":
        return translate_text_google(text, lang_dest)

    print(f"ERROR: config TRANSLATOR is set the wrong value with [{_conf.Translator}]")
    return ""


# 起動時 ####################
@bot.event()
async def event_ready():
    "Called once when the bot goes online."
    print(f"{_conf.Trans_Username} is online!")
    if not _conf.Bot_SendWhisper:
        return

    for c in bot.connected_channels:
        if c.name == _conf.Twitch_Channel:
            log.debug(f"sending whisper")
            await c.whisper(f"/color {_conf.Trans_TextColor}")
            await c.whisper(f"/me has landed!")


@bot.event()
async def event_message(ctx):
    "Runs every time a message is sent in chat."

    if not ctx.channel or not ctx.author:
        # this is probably a whisper/private message, dont handle it!
        return

    if ctx.content.startswith("!"):
        return

    user = ctx.author.name.lower()

    log.debug(f"echo: {ctx.echo}, {ctx.content}")
    if ctx.echo:
        return

    in_text = ctx.content
    if user in _conf.Ignore_Users:
        log.debug(f"{user} is in _Ignore_Users")
        return

    for w in _conf.Ignore_Line:
        if w in in_text:
            log.debug(f"{w} is in _Ignore_Line")
            return

    in_text = replace_delete_words(in_text)
    in_text = replace_emotes(in_text, ctx)
    in_text = " ".join(in_text.split())

    if not in_text:
        log.debug(f"message is empty after cleanup")
        return

    log.debug(f"--- Detect Language ---")
    lang_detect = determine_lang_detect(in_text, user)
    log.debug(f"lang_detect: {lang_detect}")
    log.debug(f"--- Select Destinate Language ---")
    lang_dest = determine_lang_dest(lang_detect)
    log.debug(f"lang_dest: {lang_dest}")

    m = in_text.split(":")
    if len(m) >= 2:
        if m[0] in _conf.TargetLangs:
            lang_dest = m[0]
            in_text = ":".join(m[1:])
    else:
        if lang_detect in _conf.Ignore_Lang:
            log.debug(f"lang_detect ({lang_detect}) is ignored, returning...")
            return

    log.debug(f"lang_dest: {lang_dest} in_text: {in_text}")

    ret = {
        "user": user,
        "reactions": [],
    }

    ret["reactions"].append(
        {
            "type": "detected",
            "sound": _conf.TTS_IN,
            "lang": lang_detect,
            "text": in_text,
        }
    )

    if lang_detect != lang_dest:
        log.debug(f"--- Translation ---")
        ret["reactions"].append(
            {
                "type": "translated",
                "sound": _conf.TTS_OUT,
                "lang": lang_dest,
                "text": translate_text(in_text, lang_detect, lang_dest),
            }
        )

    react(ret)


def react(ret):
    print_infos = []
    for r in ret["reactions"]:
        if r["sound"]:
            queue_tts(r["text"], r["lang"])
        label = f"{r['type']:<11}: {constants.LANGUAGES.get(r['lang'], 'unknown')}"
        print_infos.append((label, r["text"], r["sound"]))

    longest = 0
    for (label, value, sound) in print_infos:
        if not longest or longest < len(label):
            longest = len(label)

    print()
    print(f"👤 User       : {ret['user']}"),
    for (label, value, sound) in print_infos:
        icon = "🔈" if sound else "🔇"
        print(f"{icon} {label:<{longest}} : {value}")


def synth_create_file(file: str, text: str, lang: str):
    try:
        log.debug("generating sound file via gTTS")
        tts = gTTS(text, lang=lang)

        tts.save(file)
        log.debug(f"generated file: {file}")
    except Exception as e:
        print("gTTS error: TTS sound is not generated...")
        if e.args[0].startswith("Language not supported:"):
            # try to speak again with the default language
            if _conf.lang_Default and lang != _conf.lang_Default:
                queue_tts(text, _conf.lang_Default)
        log.debug(e.args)


def synth_play_file(file: str):
    try:
        log.debug("playing sound via pygame")
        pygame.mixer.music.load(file)
        pygame.mixer.music.play()
        # now wait until the song is over
        while pygame.mixer.music.get_busy():
            time.sleep(1)  # wait 1 second
        pygame.mixer.music.unload()
    except Exception as e:
        print("pygame.mixer.music error: unable to play the sound...")
        log.debug(e)
        log.debug(e.args)


def synth_remove_file(file: str):
    try:
        os.remove(file)
    except Exception as e:
        print(f"unable to remove the file: {file}")
        log.debug(e)
        log.debug(e.args)


def synthesize(text: str, lang: str):
    if _conf.ReadOnlyTheseLang and (lang not in _conf.ReadOnlyTheseLang):
        log.debug(f"language configured to be not read: {lang}")
        return

    log.debug(f"synthesizing in lang {lang}: {text}")

    tts_file = f"{_conf.TMP_DIR}/cnt_{datetime.now().microsecond}.mp3"
    synth_create_file(tts_file, text, lang)
    synth_play_file(tts_file)
    synth_remove_file(tts_file)


#####################################
# sig handler  -------------
def sig_handler(signum, frame) -> None:
    sys.exit(1)


# メイン処理 ###########################
def main():
    signal.signal(signal.SIGTERM, sig_handler)

    try:
        print(f"twitch-tts (Version: {version})")
        print(f"Connect to the channel : {_conf.Twitch_Channel}")
        print(f"Translator Username    : {_conf.Trans_Username}")
        print(f"Translator ENGINE      : {_conf.Translator}")
        print(f"Google Translate       : translate.google.{_conf.url_suffix}")

        log.debug("run, tmp dir...")
        create_tmp_dir(_conf.TMP_DIR)

        log.debug("run, tts thread...")
        tts_thread()

        log.debug("run, bot...")
        bot.run()

    except Exception as e:
        log.debug(e)
        input()  # stop for error!!

    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        print("!!!Clean up!!!")
        time.sleep(1)
        print("!!!Clean up Done!!!")
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)


if __name__ == "__main__":
    sys.exit(main())
