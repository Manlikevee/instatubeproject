from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("video_viewer", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="videopost",
            name="video_url",
            field=models.URLField(blank=True, max_length=2000),
        ),
    ]
