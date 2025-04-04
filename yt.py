import re

# Replace with your actual API key from Google Cloud Console

def get_live_video_id(youtube, channel_id):
    """
    Checks if the channel is currently live, and returns the live video ID.
    """
    response = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        eventType="live",
        type="video",
        maxResults=1
    ).execute()

    items = response.get("items", [])
    if items:
        for item in items:
            print(f"Found live video: {item['snippet']['title']} (ID: {item['id']['videoId']})")
        return items[0]["id"]["videoId"]
    return None

def get_live_chat_id(youtube, video_id):
    response = youtube.videos().list(
        part="liveStreamingDetails",
        id=video_id
    ).execute()

    items = response.get("items", [])
    if items and "liveStreamingDetails" in items[0]:
        return items[0]["liveStreamingDetails"].get("activeLiveChatId")
    return None

def resolve_channel_id(youtube, user_input):
    if user_input.startswith("@"):
        # Search by handle name
        query = user_input[1:]
        response = youtube.search().list(
            q=query,
            type="channel",
            part="snippet",
            maxResults=1
        ).execute()
        items = response.get("items", [])
        if items:
            return items[0]["snippet"]["channelId"]
    elif "youtube.com" in user_input:
        match = re.search(r"(?:/channel/|/user/|/c/)?([^/?&]+)", user_input.split("youtube.com/")[-1])
        if match:
            query = match.group(1)
            # Same as handle search
            response = youtube.search().list(
                q=query,
                type="channel",
                part="snippet",
                maxResults=1
            ).execute()
            items = response.get("items", [])
            if items:
                for item in items:
                    print(f"Found channel: {item['snippet']['title']} (ID: {item['id']['channelId']})")
                return items[0]["snippet"]["channelId"]
    else:
        return user_input  # Assume it's already a channel ID
    return None
