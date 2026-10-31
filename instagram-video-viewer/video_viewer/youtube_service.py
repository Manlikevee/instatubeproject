"""OAuth and resumable YouTube uploads for explicitly authorized videos."""
import json
import os
import tempfile
import time
from urllib.parse import urljoin, urlparse

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
ALLOWED_PRIVACY = {"private", "unlisted", "public"}


class YouTubeSetupError(Exception):
    pass


class YouTubeUploadError(Exception):
    pass


def oauth_flow(redirect_uri, state=None, code_verifier=None):
    client_id = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise YouTubeSetupError("Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env, enable the YouTube Data API v3, and configure the OAuth redirect URI.")
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return Flow.from_client_config(
        client_config, scopes=[YOUTUBE_UPLOAD_SCOPE], state=state,
        redirect_uri=redirect_uri, code_verifier=code_verifier,
        autogenerate_code_verifier=code_verifier is None,
    )


def _allowed_media_host(host):
    host = (host or "").lower().rstrip(".")
    return host == "instagram.com" or host.endswith(".cdninstagram.com") or host == "cdninstagram.com" or host.endswith(".fbcdn.net")


def _download_authorized_media(url, path):
    current = url
    with requests.Session() as session:
        for _ in range(5):
            parsed = urlparse(current)
            if parsed.scheme != "https" or not _allowed_media_host(parsed.hostname) or parsed.username or parsed.password:
                raise YouTubeUploadError("The video source is not a recognized Instagram media URL.")
            response = session.get(current, stream=True, timeout=(10, 45), allow_redirects=False)
            if response.is_redirect or response.is_permanent_redirect:
                next_url = response.headers.get("Location")
                response.close()
                if not next_url:
                    raise YouTubeUploadError("Instagram returned an invalid media redirect.")
                current = urljoin(current, next_url)
                continue
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].lower()
            if not (content_type.startswith("video/") or content_type == "application/octet-stream"):
                response.close()
                raise YouTubeUploadError("Instagram did not return a video file for this post.")
            declared_size = int(response.headers.get("Content-Length") or 0)
            if declared_size > MAX_UPLOAD_BYTES:
                response.close()
                raise YouTubeUploadError("This MVP supports video files up to 512 MB.")
            total = 0
            try:
                with open(path, "wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > MAX_UPLOAD_BYTES:
                            raise YouTubeUploadError("This MVP supports video files up to 512 MB.")
                        output.write(chunk)
            finally:
                response.close()
            if total == 0:
                raise YouTubeUploadError("Instagram returned an empty video file.")
            return content_type if content_type.startswith("video/") else "video/mp4"
    raise YouTubeUploadError("Instagram redirected the video too many times.")


def upload_to_youtube(session, video_url, title, description, privacy_status):
    if privacy_status not in ALLOWED_PRIVACY:
        raise YouTubeUploadError("Choose Private, Unlisted, or Public visibility.")
    serialized = session.get("youtube_credentials")
    if not serialized:
        raise YouTubeSetupError("Connect your YouTube channel before publishing.")
    try:
        credentials = Credentials.from_authorized_user_info(json.loads(serialized), [YOUTUBE_UPLOAD_SCOPE])
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            session["youtube_credentials"] = credentials.to_json()
        if not credentials.valid:
            raise YouTubeSetupError("Your YouTube authorization expired. Reconnect your channel.")
        youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    except YouTubeSetupError:
        raise
    except Exception as exc:
        raise YouTubeSetupError("Your YouTube authorization is no longer valid. Reconnect your channel.") from exc

    with tempfile.TemporaryDirectory(prefix="instaview-youtube-") as temp_dir:
        video_path = os.path.join(temp_dir, "instagram-video.mp4")
        mime_type = _download_authorized_media(video_url, video_path)
        description = description.strip()[:5000]
        body = {
            "snippet": {
                "title": title.strip()[:100] or "Instagram video",
                "description": description,
                "categoryId": "22",
            },
            "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
        }
        request = youtube.videos().insert(
            part="snippet,status", body=body,
            media_body=MediaFileUpload(video_path, mimetype=mime_type, chunksize=8 * 1024 * 1024, resumable=True),
        )
        attempts = 0
        response = None
        while response is None:
            try:
                _, response = request.next_chunk()
            except HttpError as exc:
                if exc.resp.status not in {500, 502, 503, 504} or attempts >= 4:
                    raise YouTubeUploadError("YouTube rejected the upload. Check your channel, title, and API setup, then try again.") from exc
                attempts += 1
                time.sleep(2 ** attempts)
            except (OSError, TimeoutError) as exc:
                if attempts >= 4:
                    raise YouTubeUploadError("The upload connection failed. Please try again.") from exc
                attempts += 1
                time.sleep(2 ** attempts)
    video_id = (response or {}).get("id")
    if not video_id:
        raise YouTubeUploadError("YouTube did not return an uploaded video ID.")
    session.modified = True
    return video_id
