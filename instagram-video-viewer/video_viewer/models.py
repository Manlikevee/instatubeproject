import uuid

from django.db import models


class ProfileCollection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=30, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    refresh_status = models.CharField(max_length=20, default="idle")
    last_error = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-last_refreshed_at", "username"]

    def __str__(self):
        return f"@{self.username}"


class CollectionRefreshJob(models.Model):
    STATUS_CHOICES = [(s, s.title()) for s in ("queued", "running", "succeeded", "failed")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(ProfileCollection, related_name="jobs", on_delete=models.CASCADE)
    source_url = models.URLField(max_length=1000, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    posts_found = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ProfileSearch(models.Model):
    username = models.CharField(max_length=30, db_index=True)
    searched_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=24, default="pending")
    message = models.CharField(max_length=240, blank=True)
    posts_found = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-searched_at"]

    def __str__(self):
        return f"@{self.username} — {self.searched_at:%Y-%m-%d %H:%M}"


class VideoPost(models.Model):
    collection = models.ForeignKey(ProfileCollection, related_name="videos", null=True, blank=True, on_delete=models.CASCADE)
    shortcode = models.CharField(max_length=32, unique=True)
    username = models.CharField(max_length=30, db_index=True)
    caption = models.TextField(blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    thumbnail_url = models.URLField(max_length=2000, blank=True)
    video_url = models.URLField(max_length=2000, blank=True)
    instagram_url = models.URLField(max_length=500)
    media_type = models.CharField(max_length=20, default="video")
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-posted_at", "-id"]

    def __str__(self):
        return f"@{self.username} / {self.shortcode}"
