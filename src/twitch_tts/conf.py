from . import constants
import commentjson
import os
import re
from dataclasses import dataclass


@dataclass(init=True)
class Conf:
    Trans_Username: any
    Twitch_Channel: any
    Trans_OAUTH: any

    YoutubeChannelUrl: any
    YoutubeApiKey: any

    Ignore_Lang: list[str]
    Ignore_Users: list[str]
    Ignore_Line: list[str]
    Delete_Words: list[str]
    Delete_Links: any
    Ignore_Links: bool
    Ignore_Emojis: bool
    Ignore_Mentions: bool
    Mentions_Allow_Channel: bool
    Delete_Mention_Names: bool
    AssignRandomLangToUser: any
    url_suffix: any
    Debug: any
    Translator: any
    UserToLangMap: any
    lang_SkipDetect: any
    lang_Default: any
    TMP_DIR: str
    lang_TransToHome: any
    Bot_SendWhisper: any
    Bot_StartupMessage: str
    lang_HomeToOther: any
    TTS_IN: any
    TTS_OUT: any
    Send_Translation_To_Chat: bool
    ReadOnlyTheseLang: any
    TargetLangs: list[str]
    deepl_lang_dict: object


def load_config():
    try:
      with open(f"{os.getcwd()}/config.jsonc", encoding="utf-8") as file:
        config = commentjson.load(file)
    except Exception as e:
        print(e)
        print("Please make [config.jsonc] and put it next to run")
        input()  # stop for error!!

    ###################################
    # fix some config errors ##########
    # lowercase channel and username ------

    _Twitch_Channel = config['Twitch_Channel'].strip().lower()
    _Trans_Username = config['Trans_Username'].strip().lower()

    # remove "#" mark ------
    if _Twitch_Channel.startswith("#"):
        # print("Find # mark at channel name! I remove '#' from 'config:Twitch_Channel'")
        _Twitch_Channel = _Twitch_Channel[1:]

    # remove "oauth:" mark ------
    _Trans_OAUTH = config['Trans_OAUTH']
    if _Trans_OAUTH.startswith("oauth:"):
        # print("Find 'oauth:' at OAUTH text! I remove 'oauth:' from 'config:Trans_OAUTH'")
        _Trans_OAUTH = _Trans_OAUTH[6:]

    _Ignore_Lang = [x.strip() for x in config['Ignore_Lang']]
    _Ignore_Users = [str.lower(x.strip()) for x in config['Ignore_Users']]
    _Ignore_Line = [x.strip() for x in config['Ignore_Line']]
    _Delete_Words = [x.strip() for x in config['Delete_Words']]
    _Delete_Links = config['Delete_Links'] if 'Delete_Links' in config else ''
    _Ignore_Links = config.get('Ignore_Links', False)
    _Ignore_Emojis = config.get('Ignore_Emojis', False)
    _Ignore_Mentions = config.get('Ignore_Mentions', False)
    _Mentions_Allow_Channel = config.get('Mentions_Allow_Channel', True)
    _Delete_Mention_Names = config.get('Delete_Mention_Names', True)

    if config['AssignRandomLangToUser'] == True:
        _AssignRandomLangToUser = [key for key in constants.LANGUAGES.keys()]
    else:
        _AssignRandomLangToUser = config['AssignRandomLangToUser']

    if config['GoogleTranslate_suffix'] not in constants.SERVICE_URL_SUFFIXES:
        _url_suffix = "co.jp"
    else:
        _url_suffix = config['GoogleTranslate_suffix']

    return Conf(
        Trans_Username=_Trans_Username,
        Twitch_Channel=_Twitch_Channel,
        Trans_OAUTH=_Trans_OAUTH,
        YoutubeChannelUrl = config['YoutubeChannelUrl'],
        YoutubeApiKey = config['YoutubeApiKey'],
        Ignore_Lang=_Ignore_Lang,
        Ignore_Users=_Ignore_Users,
        Ignore_Line=_Ignore_Line,
        Delete_Words=_Delete_Words,
        Delete_Links=_Delete_Links,
        Ignore_Links=_Ignore_Links,
        Ignore_Emojis=_Ignore_Emojis,
        Ignore_Mentions=_Ignore_Mentions,
        Mentions_Allow_Channel=_Mentions_Allow_Channel,
        Delete_Mention_Names=_Delete_Mention_Names,
        AssignRandomLangToUser=_AssignRandomLangToUser,
        url_suffix=_url_suffix,
        Debug=config['Debug'],
        Translator=config['Translator'],
        UserToLangMap={k.lower(): v for k, v in config['UserToLangMap'].items()},
        lang_SkipDetect=config['lang_SkipDetect'],
        lang_Default=config['lang_Default'],
        TMP_DIR="./tmp",
        lang_TransToHome=config['lang_TransToHome'],
        Bot_SendWhisper=config['Bot_SendWhisper'],
        Bot_StartupMessage=config.get('Bot_StartupMessage', '/me has landed!'),
        lang_HomeToOther=config['lang_HomeToOther'],
        TTS_IN=config['TTS_IN'],
        TTS_OUT=config['TTS_OUT'],
        Send_Translation_To_Chat=config.get('Send_Translation_To_Chat', False),
        ReadOnlyTheseLang=config['ReadOnlyTheseLang'],
        TargetLangs=[key for key in constants.LANGUAGES.keys()],
        deepl_lang_dict=constants.DEEPL_LANG_DICT,
    )
