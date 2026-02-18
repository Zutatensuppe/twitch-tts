from twitch_tts.google_translate import google_translator
from googleapiclient.discovery import build
from twitch_tts import constants
from twitch_tts import conf
from twitch_tts import yt
import pytchat

import deepl
import asyncio
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
import re

from datetime import datetime
from gtts import gTTS
from twitchio import Client
from importlib import metadata

try:
    version = metadata.version('twitch-tts')
except metadata.PackageNotFoundError:
    version = "unknown"

pygame.mixer.init()

_user_to_language_map = {}

_conf = conf.load_config()

_tts_queue = queue.Queue()

_stopped = False
_bot_loop = None


def start_tts():
    global _stopped
    _stopped = False


def stop_tts():
    global _stopped
    _stopped = True
    _tts_queue.empty()
    pygame.mixer.music.stop()
    if bot and bot.loop and bot.loop.is_running():
        asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)


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


def yt_on_message(item):
    "Runs every time a message is sent in chat."

    author = item.author.name
    message = item.message
    log.debug(f"{author}: {message}")

    if message.startswith("!"):
        if message == '!tts start':
            start_tts()
        elif message == '!tts stop':
            stop_tts()
        return

    if _stopped:
        return

    user = author.lower()

    in_text = message
    if user in _conf.Ignore_Users:
        log.debug(f"{user} is in _Ignore_Users")
        return

    for w in _conf.Ignore_Line:
        if w in in_text:
            log.debug(f"{w} is in _Ignore_Line")
            return

    in_text = replace_delete_words(in_text)
    in_text = replace_links(in_text)
    in_text = remove_emojis(in_text)
    # in_text = replace_emotes(in_text, ctx)
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


def yt_thread_fn():
    youtube = build("youtube", "v3", developerKey=_conf.YoutubeApiKey)
    channel_id = yt.resolve_channel_id(youtube, _conf.YoutubeChannelUrl)
    while True:
      log.debug(f"Checking if channel '{channel_id}' is live...")
      video_id = yt.get_live_video_id(youtube, channel_id)

      if not video_id:
          log.debug("Channel is not live right now. Will check again in 60 seconds.")
          time.sleep(60)
          continue

      log.debug(f"Live video found: {video_id}, start reading chat...")
      chat = pytchat.create(video_id=video_id, interruptable=False)

      while chat.is_alive():
          for item in chat.get().sync_items():
              yt_on_message(item)


def yt_thread():
    if _conf.YoutubeChannelUrl and _conf.YoutubeApiKey:
        thread = threading.Thread(target=yt_thread_fn)
        thread.start()
    else:
        log.debug("Youtube channel and API key not configured, skipping Youtube chat.")


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
bot = None
_translator = google_translator(url_suffix=_conf.url_suffix)


def reload_config():
    """Reload config from disk and update runtime settings."""
    global _conf, _translator, _user_to_language_map
    _conf = conf.load_config()
    _translator = google_translator(url_suffix=_conf.url_suffix)
    _user_to_language_map = {}
    if _conf.Debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)


def _create_bot():
    """Create bot instance - must be called from the thread with the event loop"""
    global bot
    bot = Client(
        token="oauth:" + _conf.Trans_OAUTH,
        initial_channels=[_conf.Twitch_Channel],
        loop=asyncio.get_event_loop(),
    )
    _register_bot_events()


replace_links_regex = re.compile(r'https?://\S+')
def replace_links(message: str):
    # If Ignore_Links is enabled, always remove links
    if _conf.Ignore_Links:
        message = replace_links_regex.sub('', message)
        return message
    
    if _conf.Delete_Links == False:
        return message

    message = replace_links_regex.sub(_conf.Delete_Links, message)
    return message


# Regex to match most emoji characters
emoji_regex = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"  # enclosed characters
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
    "\U00002600-\U000026FF"  # misc symbols
    "\U0001F700-\U0001F77F"  # alchemical symbols
    "]+", 
    flags=re.UNICODE
)

def remove_emojis(message: str):
    if _conf.Ignore_Emojis:
        message = emoji_regex.sub('', message)
    return message


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


def _register_bot_events():
    """Register event handlers on the bot instance"""
    
    @bot.event()
    async def event_ready():
        "Called once when the bot goes online."
        print(f"{_conf.Trans_Username} is online!")

    @bot.event()
    async def event_join(channel, user):
        "Called when a user joins a channel."
        if user.name.lower() != _conf.Trans_Username.lower():
            return
        if not _conf.Bot_SendWhisper:
            return
        if channel.name != _conf.Twitch_Channel:
            return

        log.debug(f"sending /color {_conf.Trans_TextColor}")
        await channel.send(f"/color {_conf.Trans_TextColor}")
        log.debug(f"sending startup message: {_conf.Bot_StartupMessage}")
        await channel.send(_conf.Bot_StartupMessage)

    @bot.event()
    async def event_message(ctx):
        "Runs every time a message is sent in chat."

        if not ctx.channel or not ctx.author:
            # this is probably a whisper/private message, dont handle it!
            return

        if ctx.content.startswith("!"):
            if ctx.content == '!tts start':
                start_tts()
            elif ctx.content == '!tts stop':
                stop_tts()
            return

        if _stopped:
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
        in_text = replace_links(in_text)
        in_text = remove_emojis(in_text)
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


def sig_handler(signum, frame) -> None:
    sys.exit(1)


def run_bot_core():
    """Core bot functionality without signal handlers - safe for threading"""
    global _bot_loop, bot
    try:
        reload_config()
        print(f"twitch-tts (Version: {version})")
        print(f"Connect to the channel : {_conf.Twitch_Channel}")
        print(f"Translator Username    : {_conf.Trans_Username}")
        print(f"Translator ENGINE      : {_conf.Translator}")
        print(f"Google Translate       : translate.google.{_conf.url_suffix}")

        log.debug("run, tmp dir...")
        create_tmp_dir(_conf.TMP_DIR)

        log.debug("run, tts thread...")
        tts_thread()

        log.debug("run, yt thread...")
        yt_thread()

        log.debug("run, creating bot...")
        _create_bot()

        log.debug("run, twitch bot...")
        _bot_loop = bot.loop
        bot.run()

    except RuntimeError as e:
        # Ignore "Event loop stopped" error during shutdown
        if "Event loop stopped" not in str(e):
            log.debug(e)
            raise
    except Exception as e:
        log.debug(e)
        raise  # Re-raise for GUI to handle
    finally:
        _bot_loop = None
        bot = None


def main():
    signal.signal(signal.SIGTERM, sig_handler)

    try:
        run_bot_core()
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
