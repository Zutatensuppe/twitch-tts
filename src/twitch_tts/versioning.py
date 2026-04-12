from importlib import metadata

from ._build_version import BUILD_VERSION


def get_version():
    if BUILD_VERSION:
        return BUILD_VERSION

    try:
        return metadata.version("twitch-tts")
    except metadata.PackageNotFoundError:
        return "unknown"
