"""Small, bounded read-only adapter around Instaloader's public Python API."""
import os
import re
from datetime import timezone as datetime_timezone

import instaloader
from django.utils import timezone
from instaloader.exceptions import (
    ConnectionException,
    InstaloaderException,
    LoginRequiredException,
    ProfileNotExistsException,
    QueryReturnedNotFoundException,
    TooManyRequestsException,
)


class ProfileLookupError(Exception):
    def __init__(self, message, code="unavailable"):
        super().__init__(message)
        self.code = code


def _aware_utc(value):
    """Instaloader returns naive UTC datetimes; Django expects aware values."""
    if value and timezone.is_naive(value):
        return timezone.make_aware(value, datetime_timezone.utc)
    return value


def fetch_video_posts(username, limit=24, scan_limit=60):
    """Return recent video/Reel metadata, without downloading media files."""
    username = username.strip().lstrip("@").lower()
    loader = instaloader.Instaloader(
        download_pictures=False, download_videos=False, download_video_thumbnails=False,
        download_geotags=False, download_comments=False, save_metadata=False,
        compress_json=False, quiet=True,
    )
    # Optional owner-provided session credentials. Never attempt to log in or
    # bypass restrictions implicitly; a configured session only grants its own access.
    session_file = os.getenv("INSTALOADER_SESSIONFILE")
    session_user = os.getenv("INSTAGRAM_SESSION_USERNAME")
    if session_file and session_user and os.path.isfile(session_file):
        try:
            loader.load_session_from_file(session_user, session_file)
        except (FileNotFoundError, InstaloaderException):
            pass
    try:
        profile = instaloader.Profile.from_username(loader.context, username)
        if profile.is_private and not loader.context.is_logged_in:
            raise ProfileLookupError("This account is private. Sign in with an account that can access it.", "private")
        result = []
        for scanned, post in enumerate(profile.get_posts(), start=1):
            if scanned > scan_limit:
                break
            if post.is_video:
                result.append({
                    "shortcode": post.shortcode,
                    "username": username,
                    "caption": post.caption or "",
                    "posted_at": _aware_utc(post.date_utc),
                    "thumbnail_url": post.url,
                    "video_url": post.video_url or "",
                    "instagram_url": f"https://www.instagram.com/p/{post.shortcode}/",
                    "media_type": "reel" if getattr(post, "typename", "") == "XDTGraphVideo" else "video",
                })
            if len(result) >= limit:
                break
        return result
    except ProfileLookupError:
        raise
    except (ProfileNotExistsException, QueryReturnedNotFoundException) as exc:
        raise ProfileLookupError("We couldn't find that Instagram profile.", "not_found") from exc
    except LoginRequiredException as exc:
        raise ProfileLookupError("Instagram requires login to access this profile. Try a public profile or configure an authorized session.", "login_required") from exc
    except TooManyRequestsException as exc:
        raise ProfileLookupError("Instagram is rate limiting requests. Please wait a while before trying again.", "rate_limited") from exc
    except ConnectionException as exc:
        raise ProfileLookupError("Instagram could not be reached. Please try again later.", "connection") from exc
    except InstaloaderException as exc:
        raise ProfileLookupError("Instagram did not provide this profile's posts. It may be temporarily unavailable.", "instagram_error") from exc


def fetch_reel_and_profile_videos(reel_url, limit=24):
    """Resolve a shared Instagram post URL, then return it with recent profile videos."""
    match = re.fullmatch(
        r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)/?",
        reel_url.strip().split("?", 1)[0],
    )
    if not match:
        raise ProfileLookupError("Paste a valid Instagram Reel or post link.", "invalid_link")
    shortcode = match.group(1)
    loader = instaloader.Instaloader(
        download_pictures=False, download_videos=False, download_video_thumbnails=False,
        download_geotags=False, download_comments=False, save_metadata=False,
        compress_json=False, quiet=True,
    )
    session_file = os.getenv("INSTALOADER_SESSIONFILE")
    session_user = os.getenv("INSTAGRAM_SESSION_USERNAME")
    if session_file and session_user and os.path.isfile(session_file):
        try:
            loader.load_session_from_file(session_user, session_file)
        except (FileNotFoundError, InstaloaderException):
            pass
    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        if not post.is_video:
            raise ProfileLookupError("That Instagram link is not a video post or Reel.", "not_video")
        username = post.owner_username
        selected = {
            "shortcode": post.shortcode,
            "username": username,
            "caption": post.caption or "",
            "posted_at": _aware_utc(post.date_utc),
            "thumbnail_url": post.url,
            "video_url": post.video_url or "",
            "instagram_url": f"https://www.instagram.com/reel/{post.shortcode}/",
            "media_type": "reel",
        }
        videos = fetch_video_posts(username, limit=limit)
        deduped = {item["shortcode"]: item for item in videos}
        deduped[shortcode] = selected
        return username, list(deduped.values())[:limit + 1]
    except ProfileLookupError:
        raise
    except LoginRequiredException as exc:
        raise ProfileLookupError("Instagram requires login to open that Reel. Try a publicly accessible link or configure an authorized session.", "login_required") from exc
    except TooManyRequestsException as exc:
        raise ProfileLookupError("Instagram is rate limiting requests. Please wait a while before trying again.", "rate_limited") from exc
    except (ProfileNotExistsException, QueryReturnedNotFoundException) as exc:
        raise ProfileLookupError("We couldn't access that Reel. The link may be invalid or the post unavailable.", "not_found") from exc
    except ConnectionException as exc:
        raise ProfileLookupError("Instagram could not be reached. Please try again later.", "connection") from exc
    except InstaloaderException as exc:
        raise ProfileLookupError("Instagram did not provide that Reel. It may be temporarily unavailable.", "instagram_error") from exc
