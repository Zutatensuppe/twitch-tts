######################################################
# PLEASE CHANGE FOLLOWING CONFIGS ####################
Twitch_Channel = "PLEASE_CONFIGURE"
Trans_Username = "PLEASE_CONFIGURE"

# you can refer to https://github.com/Zutatensuppe/twitch-emote-unlock#how-to-get-the-oauth_token-required-in-the-configtoml to see how to get this value
Trans_OAUTH = "PLEASE_CONFIGURE"

#######################################################
# OPTIONAL CONFIGS ####################################
Trans_TextColor = "Firebrick"
# Blue, Coral, DodgerBlue, SpringGreen, YellowGreen, Green, OrangeRed, Red, GoldenRod, HotPink, CadetBlue, SeaGreen, Chocolate, BlueViolet, and Firebrick

lang_TransToHome = "ru"
lang_HomeToOther = "ru"

# default language that is used when no language could or should be detected
# it is also the default language that text is read in if a detected language
# is not supported for reading
lang_Default = "ru"

# if True, then the lang_Default will be used for all texts, no detection of
# the language will happen
lang_SkipDetect = False

Show_ByName = True
Show_ByLang = True

Ignore_Lang = []
Ignore_Users = ["Nightbot", "Robyottoko"]
Ignore_Line = []
Delete_Words = []

# if there are entries in this array, users get assigned one of those
# entries as their language. the user messages will then always be
# interpreted as that language until the bot is restarted
# Use True instead of an array if all supported languages should be chosen from
# Note: LangToUserMap entries will have precedence over this
AssignRandomLangToUser = []  # ["haw", "it", "ja"]

# if a user is assigned a language in this map, the user
# messages will always be interpreted as that language
# Note: username must be all lowercase
UserToLangMap = {
    # "username": "language"
    # "nc_para_": "sv",
}

# Any emvironment, set it to `True`, then text will be read by TTS voice!
# TTS_IN:User Input Text, TTS_OUT:Bot Output Text
TTS_IN = True
TTS_OUT = False

# if you make TTS for only few lang, please add langID in the list
# for example, ['ja'] means Japanese only, ['ko','en'] means Korean and English are TTS!
ReadOnlyTheseLang = []

# Select the translate engine ('deepl' or 'google')
Translator = "google"

Bot_SendWhisper = False

# If you meet any bugs, You can check some error message using Debug mode (Debug = True)
Debug = False

# Enter the suffix of the Google Translate URL you normally use.
# Example: translate.google.co.jp -> 'co.jp'
#          translate.google.com   -> 'com'
GoogleTranslate_suffix = "co.jp"
