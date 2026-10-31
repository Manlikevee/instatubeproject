import signal
from threading import Event

from django.core.management.base import BaseCommand

from video_viewer.collection_jobs import worker_loop


class Command(BaseCommand):
    help = "Process queued Instagram collection refresh jobs using a bounded thread pool."

    def add_arguments(self, parser):
        parser.add_argument("--workers", type=int, default=2)
        parser.add_argument("--poll-interval", type=float, default=1.0)

    def handle(self, *args, **options):
        stop = Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        workers = max(1, min(options["workers"], 8))
        self.stdout.write(self.style.SUCCESS(f"Collection worker started ({workers} threads). Ctrl+C to stop."))
        worker_loop(stop, workers=workers, poll_interval=max(0.25, options["poll_interval"]))
