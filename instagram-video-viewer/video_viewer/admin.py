from django.contrib import admin
from .models import ProfileSearch, VideoPost


@admin.register(ProfileSearch)
class ProfileSearchAdmin(admin.ModelAdmin):
    list_display = ("username", "searched_at", "status", "posts_found")
    list_filter = ("status",)
    search_fields = ("username",)


@admin.register(VideoPost)
class VideoPostAdmin(admin.ModelAdmin):
    list_display = ("username", "shortcode", "media_type", "posted_at")
    search_fields = ("username", "shortcode", "caption")
