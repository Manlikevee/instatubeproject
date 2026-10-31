from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="ProfileSearch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(db_index=True, max_length=30)),
                ("searched_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(default="pending", max_length=24)),
                ("message", models.CharField(blank=True, max_length=240)),
                ("posts_found", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ["-searched_at"]},
        ),
        migrations.CreateModel(
            name="VideoPost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shortcode", models.CharField(max_length=32, unique=True)),
                ("username", models.CharField(db_index=True, max_length=30)),
                ("caption", models.TextField(blank=True)),
                ("posted_at", models.DateTimeField(blank=True, null=True)),
                ("thumbnail_url", models.URLField(blank=True, max_length=2000)),
                ("instagram_url", models.URLField(max_length=500)),
                ("media_type", models.CharField(default="video", max_length=20)),
                ("fetched_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-posted_at", "-id"]},
        ),
    ]
