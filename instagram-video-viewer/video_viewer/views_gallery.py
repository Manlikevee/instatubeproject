from django.shortcuts import render

from .gallery_service import GalleryLookupError, fetch_gallery_dl_videos


def gallery_dl_page(request):
    source = request.GET.get("q", "").strip()
    videos = []
    message = ""
    if source:
        try:
            videos = fetch_gallery_dl_videos(source)
            if not videos:
                message = "No accessible video posts were found in the recent results returned by gallery-dl."
        except GalleryLookupError as exc:
            message = str(exc)
    return render(request, "video_viewer/gallery_dl.html", {
        "source": source, "videos": videos, "message": message,
        "youtube_connected": bool(request.session.get("youtube_credentials")),
        "youtube_flash": request.session.pop("youtube_flash", ""),
    })
