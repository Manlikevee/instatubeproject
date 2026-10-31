import re

from django.db import migrations


USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def attach_existing_videos(apps, schema_editor):
    Collection = apps.get_model("video_viewer", "ProfileCollection")
    Video = apps.get_model("video_viewer", "VideoPost")
    alias = schema_editor.connection.alias
    usernames = Video.objects.using(alias).values_list("username", flat=True).distinct()
    for username in usernames:
        normalized = (username or "").lower()
        if USERNAME_RE.fullmatch(normalized):
            collection, _ = Collection.objects.using(alias).get_or_create(username=normalized)
            Video.objects.using(alias).filter(username=username, collection__isnull=True).update(collection_id=collection.pk)


class Migration(migrations.Migration):
    dependencies = [("video_viewer", "0003_profilecollection_collectionrefreshjob_and_more")]
    operations = [migrations.RunPython(attach_existing_videos, migrations.RunPython.noop)]
