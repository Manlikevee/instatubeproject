from rest_framework import serializers

from video_viewer.models import CollectionRefreshJob, ProfileCollection, VideoPost


class VideoPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoPost
        fields = ("shortcode", "username", "caption", "posted_at", "thumbnail_url", "video_url", "instagram_url", "media_type", "fetched_at")


class CollectionSerializer(serializers.ModelSerializer):
    video_count = serializers.SerializerMethodField()

    def get_video_count(self, collection):
        if hasattr(collection, "videos__count"):
            return collection.videos__count
        return collection.videos.count()

    class Meta:
        model = ProfileCollection
        fields = ("id", "username", "created_at", "last_refreshed_at", "refresh_status", "last_error", "video_count")


class JobSerializer(serializers.ModelSerializer):
    collection_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CollectionRefreshJob
        fields = ("id", "collection_id", "status", "created_at", "started_at", "completed_at", "posts_found", "error")
