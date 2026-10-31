from django.urls import path

from .views import CollectionDetailView, CollectionListCreateView, CollectionRefreshView, CollectionVideosView, JobStatusView

urlpatterns = [
    path("collections/", CollectionListCreateView.as_view(), name="api_collections"),
    path("collections/<uuid:collection_id>/", CollectionDetailView.as_view(), name="api_collection_detail"),
    path("collections/<uuid:collection_id>/videos/", CollectionVideosView.as_view(), name="api_collection_videos"),
    path("collections/<uuid:collection_id>/refresh/", CollectionRefreshView.as_view(), name="api_collection_refresh"),
    path("jobs/<uuid:job_id>/", JobStatusView.as_view(), name="api_job_status"),
]
