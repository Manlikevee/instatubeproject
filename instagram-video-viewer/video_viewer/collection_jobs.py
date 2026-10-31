"""Database-backed refresh queue, processed by the run_collection_worker command."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from django.db import OperationalError, close_old_connections, transaction
from django.utils import timezone

from .models import CollectionRefreshJob, ProfileCollection, ProfileSearch, VideoPost
from .services import ProfileLookupError, fetch_reel_and_profile_videos, fetch_video_posts

logger = logging.getLogger(__name__)
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def enqueue_refresh(query):

    query = (query or "").strip()
    source_url = ""
    match = re.fullmatch(r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p|tv)/[A-Za-z0-9_-]+/?(?:\?.*)?", query, re.I)
    if match:
        source_url = query
        username = "reel-" + re.search(r"/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)", query, re.I).group(1).lower()
        # The resolver replaces this temporary collection with the owning profile.
    else:
        username = query.lstrip("@").lower()
        if not USERNAME_RE.fullmatch(username):
            raise ValueError("Enter a valid Instagram username or paste a Reel link.")
    collection, _ = ProfileCollection.objects.get_or_create(username=username)
    active = collection.jobs.filter(status__in=("queued", "running")).first()
    if active:
        return collection, active
    job = CollectionRefreshJob.objects.create(collection=collection, source_url=source_url)
    collection.refresh_status = "queued"
    collection.last_error = ""
    collection.save(update_fields=("refresh_status", "last_error"))
    ProfileSearch.objects.create(username=username, status="queued", message=f"Refresh job {job.id}")
    return collection, job


def claim_job():
    close_old_connections()
    try:
        with transaction.atomic():
            pending = CollectionRefreshJob.objects.filter(status="queued").order_by("created_at").values_list("pk", flat=True).first()
            if not pending:
                return None
            # The conditional update also makes claiming safe on SQLite, where
            # select_for_update is not supported.
            claimed = CollectionRefreshJob.objects.filter(pk=pending, status="queued").update(
                status="running", started_at=timezone.now(),
            )
            if not claimed:
                return None
            job = CollectionRefreshJob.objects.get(pk=pending)
            job.collection.refresh_status = "running"
            job.collection.save(update_fields=("refresh_status",))
            return job.id
    except OperationalError:
        # A competing SQLite worker may win the write lock while claiming.
        return None


def process_job(job_id):
    close_old_connections()
    job = CollectionRefreshJob.objects.select_related("collection").get(pk=job_id)
    collection = job.collection
    try:
        if job.source_url:
            username, posts = fetch_reel_and_profile_videos(job.source_url, limit=24)
            if username.lower() != collection.username:
                collection, _ = ProfileCollection.objects.get_or_create(username=username.lower())
                job.collection = collection
                job.save(update_fields=("collection",))
                old = ProfileCollection.objects.filter(username__startswith="reel-").filter(jobs__pk=job.pk).exclude(pk=collection.pk).first()
                if old and not old.videos.exists() and not old.jobs.exclude(pk=job.pk).exists():
                    old.delete()
        else:
            username = collection.username
            posts = fetch_video_posts(username, limit=24)
        for item in posts:
            VideoPost.objects.update_or_create(shortcode=item["shortcode"], defaults={**item, "collection": collection})
        job.status = "succeeded"
        job.posts_found = len(posts)
        job.error = ""
        collection.refresh_status = "idle"
        collection.last_refreshed_at = timezone.now()
        collection.last_error = ""
        ProfileSearch.objects.create(username=collection.username, status="success", posts_found=len(posts))
    except ProfileLookupError as exc:
        job.status = "failed"
        job.error = str(exc)[:240]
        collection.refresh_status = "failed"
        collection.last_error = str(exc)[:240]
        ProfileSearch.objects.create(username=collection.username, status=exc.code, message=str(exc)[:240])
    except Exception as exc:
        logger.exception("Collection refresh job %s failed", job_id)
        job.status = "failed"
        job.error = "Instagram request failed. Please try again later."
        collection.refresh_status = "failed"
        collection.last_error = job.error
        ProfileSearch.objects.create(username=collection.username, status="error", message=job.error)
    finally:
        job.completed_at = timezone.now()
        job.save(update_fields=("status", "posts_found", "error", "completed_at", "collection"))
        collection.save(update_fields=("refresh_status", "last_refreshed_at", "last_error"))
        close_old_connections()


def worker_loop(stop_event: Event, workers=2, poll_interval=1.0):
    """Run bounded concurrent database queue workers until asked to stop."""
    def consume():
        while not stop_event.is_set():
            job_id = claim_job()
            if job_id:
                process_job(job_id)
            else:
                stop_event.wait(poll_interval)

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="collection-refresh") as pool:
        futures = [pool.submit(consume) for _ in range(workers)]
        for future in futures:
            future.result()
