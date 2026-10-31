from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .collection_jobs import enqueue_refresh
from .models import CollectionRefreshJob, ProfileCollection, ProfileSearch, VideoPost


def home(request):
    if request.method == "POST" and request.POST.get("q", "").strip():
        try:
            collection, job = enqueue_refresh(request.POST["q"])
        except ValueError as exc:
            return render(request, "video_viewer/home.html", {"message": str(exc), "history": ProfileSearch.objects.all()[:8]})
        return redirect("collection_detail", collection_id=collection.pk)
    history = ProfileSearch.objects.all()[:8]
    history_items = []
    for item in history:
        collection = ProfileCollection.objects.filter(username=item.username.lower()).first()
        history_items.append((item, reverse("collection_detail", kwargs={"collection_id": collection.pk}) if collection else reverse("collection_list")))
    return render(request, "video_viewer/home.html", {
        "history": history,
        "history_items": history_items,
        "collections": ProfileCollection.objects.all()[:6],
        "youtube_connected": bool(request.session.get("youtube_credentials")),
        "youtube_flash": request.session.pop("youtube_flash", ""),
    })


def collection_list(request):
    return render(request, "video_viewer/collections.html", {"collections": ProfileCollection.objects.all()})


def collection_detail(request, collection_id):
    collection = get_object_or_404(ProfileCollection, pk=collection_id)
    if request.method == "POST":
        collection, job = enqueue_refresh(collection.username)
        return redirect("collection_detail", collection_id=collection.pk)
    videos = collection.videos.all()
    page_obj = Paginator(videos, 24).get_page(request.GET.get("page"))
    active_job = collection.jobs.filter(status__in=("queued", "running")).first()
    return render(request, "video_viewer/collection_detail.html", {
        "collection": collection,
        "page_obj": page_obj,
        "active_job": active_job,
        "youtube_connected": bool(request.session.get("youtube_credentials")),
        "youtube_flash": request.session.pop("youtube_flash", ""),
    })


def refresh_job_status(request, job_id):
    job = get_object_or_404(CollectionRefreshJob.objects.select_related("collection"), pk=job_id)
    age_seconds = max(0, int((timezone.now() - job.created_at).total_seconds()))
    return JsonResponse({"id": str(job.pk), "collection_id": str(job.collection_id), "username": job.collection.username,
                         "status": job.status, "posts_found": job.posts_found, "error": job.error,
                         "waiting_for_worker": job.status == "queued" and age_seconds >= 30,
                         "age_seconds": age_seconds,
                         "created_at": job.created_at.isoformat(),
                         "completed_at": job.completed_at.isoformat() if job.completed_at else None})
