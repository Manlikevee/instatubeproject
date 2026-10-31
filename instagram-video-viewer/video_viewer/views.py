import os

from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .collection_jobs import claim_job, enqueue_refresh, process_job
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
        "vercel_deployment": os.environ.get("VERCEL") == "1",
        "youtube_connected": bool(request.session.get("youtube_credentials")),
        "youtube_flash": request.session.pop("youtube_flash", ""),
    })


def refresh_job_status(request, job_id):
    job = get_object_or_404(CollectionRefreshJob.objects.select_related("collection"), pk=job_id)
    age_seconds = max(0, int((timezone.now() - job.created_at).total_seconds()))
    if os.environ.get("VERCEL") == "1":
        # Vercel has no local shell worker. Let this serverless status request
        # claim and process only its own queued job, so the polling UI can still
        # complete without relying on an ephemeral background thread.
        if job.status == "queued":
            claimed_id = claim_job(job_id=job.pk)
            if claimed_id:
                process_job(claimed_id)
                job.refresh_from_db()
        elif job.status == "running" and job.started_at and (timezone.now() - job.started_at).total_seconds() > 330:
            timeout_message = "This refresh exceeded Vercel's function time limit. Please try refreshing again."
            with transaction.atomic():
                CollectionRefreshJob.objects.filter(pk=job.pk, status="running").update(
                    status="failed", error=timeout_message, completed_at=timezone.now(),
                )
                ProfileCollection.objects.filter(pk=job.collection_id).update(
                    refresh_status="failed", last_error=timeout_message,
                )
            job.refresh_from_db()
        age_seconds = max(0, int((timezone.now() - job.created_at).total_seconds()))
    return JsonResponse({"id": str(job.pk), "collection_id": str(job.collection_id), "username": job.collection.username,
                         "status": job.status, "posts_found": job.posts_found, "error": job.error,
                         "waiting_for_worker": job.status == "queued" and age_seconds >= 30,
                         "hosted_worker": os.environ.get("VERCEL") == "1",
                         "age_seconds": age_seconds,
                         "created_at": job.created_at.isoformat(),
                         "completed_at": job.completed_at.isoformat() if job.completed_at else None})
