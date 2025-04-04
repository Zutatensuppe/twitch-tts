import constants
import commentjson
import os
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
    Trans_TextColor: any
    lang_HomeToOther: any
    TTS_IN: any
    TTS_OUT: any
    ReadOnlyTheseLang: any
    TargetLangs: list[str]
    deepl_lang_dict: object


def load_config():
    try:
      with open(f"{os.getcwd()}/config.jsonc") as file:
        config = commentjson.load(file)
    except Exception as e:
        print(e)
        print("Please make [config.jsonc] and put it next to run")
        input()  # stop for error!!

    ###################################
    # fix some config errors ##########
    # lowercase channel and username ------

    _Twitch_Channel = config['Twitch_Channel'].lower()
    _Trans_Username = config['Trans_Username'].lower()

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
        AssignRandomLangToUser=_AssignRandomLangToUser,
        url_suffix=_url_suffix,
        Debug=config['Debug'],
        Translator=config['Translator'],
        UserToLangMap=config['UserToLangMap'],
        lang_SkipDetect=config['lang_SkipDetect'],
        lang_Default=config['lang_Default'],
        TMP_DIR="./tmp",
        lang_TransToHome=config['lang_TransToHome'],
        Bot_SendWhisper=config['Bot_SendWhisper'],
        Trans_TextColor=config['Trans_TextColor'],
        lang_HomeToOther=config['lang_HomeToOther'],
        TTS_IN=config['TTS_IN'],
        TTS_OUT=config['TTS_OUT'],
        ReadOnlyTheseLang=config['ReadOnlyTheseLang'],
        TargetLangs=[key for key in constants.LANGUAGES.keys()],
        deepl_lang_dict=constants.DEEPL_LANG_DICT,
    )
