from django.apps import AppConfig


class VideoViewerApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "video_viewer.api"
    label = "video_viewer_api"
    verbose_name = "Video Viewer REST API"
