from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from video_viewer.collection_jobs import enqueue_refresh
from video_viewer.models import CollectionRefreshJob, ProfileCollection

from .serializers import CollectionSerializer, JobSerializer, VideoPostSerializer


class CollectionListCreateView(APIView):
    def get(self, request):
        collections = ProfileCollection.objects.annotate(video_count=Count("videos"))
        page = self.paginate_queryset(collections)
        serializer = CollectionSerializer(page if page is not None else collections, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def post(self, request):
        query = request.data.get("username") or request.data.get("url") or ""
        try:
            collection, job = enqueue_refresh(query)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = {"collection": CollectionSerializer(collection).data, "job": JobSerializer(job).data,
                   "status_url": request.build_absolute_uri(f"/api/v1/jobs/{job.pk}/")}
        return Response(payload, status=status.HTTP_202_ACCEPTED)

    def paginate_queryset(self, queryset):
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        paginator.page_size = 24
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        self._paginator = paginator
        return page

    def get_paginated_response(self, data):
        return self._paginator.get_paginated_response(data)


class CollectionDetailView(generics.RetrieveAPIView):
    queryset = ProfileCollection.objects.annotate(video_count=Count("videos"))
    serializer_class = CollectionSerializer
    lookup_field = "id"
    lookup_url_kwarg = "collection_id"


class CollectionVideosView(APIView):
    def get(self, request, collection_id):
        collection = get_object_or_404(ProfileCollection, pk=collection_id)
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        paginator.page_size = 24
        page = paginator.paginate_queryset(collection.videos.all(), request, view=self)
        return paginator.get_paginated_response(VideoPostSerializer(page, many=True).data)


class CollectionRefreshView(APIView):
    def post(self, request, collection_id):
        collection = get_object_or_404(ProfileCollection, pk=collection_id)
        collection, job = enqueue_refresh(collection.username)
        return Response({"job": JobSerializer(job).data,
                         "status_url": request.build_absolute_uri(f"/api/v1/jobs/{job.pk}/")}, status=status.HTTP_202_ACCEPTED)


class JobStatusView(generics.RetrieveAPIView):
    queryset = CollectionRefreshJob.objects.select_related("collection")
    serializer_class = JobSerializer
    lookup_field = "id"
    lookup_url_kwarg = "job_id"
