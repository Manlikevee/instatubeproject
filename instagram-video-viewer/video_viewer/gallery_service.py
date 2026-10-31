"""Read-only Instagram metadata lookup using gallery-dl's Python API."""
import io
import logging
import os
import re
from urllib.parse import urlparse

try:
    from gallery_dl import config
    from gallery_dl.job import DataJob
except ImportError:  # Keep the original page usable until requirements are installed.
    config = None
    DataJob = None

logger = logging.getLogger(__name__)
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
VIDEO_EXTENSIONS = {"mp4", "m4v", "mov", "webm"}


class GalleryLookupError(Exception):
    pass


def _instagram_url(value):
    value = value.strip()
    if USERNAME_RE.fullmatch(value.lstrip("@")):
        return f"https://www.instagram.com/{value.lstrip('@')}/reels/"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"instagram.com", "www.instagram.com"}:
        raise GalleryLookupError("Enter an Instagram username or a link from instagram.com.")
    profile_path = re.fullmatch(r"/([A-Za-z0-9._]+)/?", parsed.path)
    if profile_path:
        return f"{parsed.scheme}://{parsed.netloc}/{profile_path.group(1)}/reels/"
    if re.fullmatch(r"/[A-Za-z0-9._]+/reels?/?", parsed.path):
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/"
    if not re.fullmatch(r"/(?:reel|reels|p|tv)/[A-Za-z0-9_-]+/?", parsed.path):
        raise GalleryLookupError("Use an Instagram profile or post/Reel link.")
    return value


def fetch_gallery_dl_videos(source, limit=24):
    """Extract metadata for accessible videos; DataJob does not download media."""
    if DataJob is None:
        raise GalleryLookupError("Install the alternate extractor with `pip install -r requirements.txt`, then restart Django.")
    url = _instagram_url(source)
    cookie_file = os.getenv("GALLERY_DL_INSTAGRAM_COOKIES", "").strip()

    # gallery-dl's DataJob returns metadata and media URLs without writing files.
    # Restrict profile scans and keep the extractor's normal request pacing.
    config.set(("extractor", "instagram"), "max-posts", limit)
    config.set(("extractor", "instagram"), "videos", True)
    config.set(("extractor", "instagram"), "include", "posts")
    if cookie_file:
        if not os.path.isfile(cookie_file):
            raise GalleryLookupError("The configured gallery-dl cookie file does not exist.")
        config.set(("extractor", "instagram"), "cookies", cookie_file)

    output = io.StringIO()
    try:
        job = DataJob(url, file=output, ensure_ascii=False)
        job.run()
        if job.exception:
            raise job.exception
    except Exception as exc:
        logger.exception("gallery-dl failed while extracting %s", url)
        detail = str(exc).lower()
        if any(token in detail for token in ("login", "cookie", "private", "authentication")):
            message = "Instagram requires an authorized session for this content. Configure GALLERY_DL_INSTAGRAM_COOKIES or try an accessible public profile."
        elif "429" in detail or "rate" in detail:
            message = "Instagram is rate limiting requests. Please wait before trying again."
        else:
            message = "gallery-dl could not retrieve this Instagram content. The post may be unavailable or Instagram may have changed its response."
        raise GalleryLookupError(message) from exc

    videos = []
    seen = set()
    for entry in getattr(job, "data", []) or []:
        if not isinstance(entry, (list, tuple)) or len(entry) < 3:
            continue
        media_url, metadata = entry[1], entry[-1]
        if not isinstance(metadata, dict):
            continue
        extension = str(metadata.get("extension", "")).lower()
        video_url = metadata.get("video_url") or (media_url if extension in VIDEO_EXTENSIONS else "")
        if not video_url:
            continue
        shortcode = str(metadata.get("post_shortcode") or metadata.get("shortcode") or metadata.get("id") or "")
        if shortcode and shortcode in seen:
            continue
        if shortcode:
            seen.add(shortcode)
        username = str(metadata.get("username") or metadata.get("owner_username") or "")
        post_url = str(metadata.get("post_url") or (f"https://www.instagram.com/reel/{shortcode}/" if shortcode else url))
        videos.append({
            "shortcode": shortcode,
            "username": username,
            "caption": str(metadata.get("caption") or metadata.get("title") or metadata.get("description") or ""),
            "posted_at": metadata.get("date") or metadata.get("taken_at"),
            "thumbnail_url": str(metadata.get("preview_url") or metadata.get("thumbnail_url") or metadata.get("display_url") or media_url or ""),
            "video_url": str(video_url),
            "instagram_url": post_url,
            "media_type": "reel",
        })
        if len(videos) >= limit:
            break
    return videos
