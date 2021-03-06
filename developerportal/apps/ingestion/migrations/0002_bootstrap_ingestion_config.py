# Generated by Django 2.2.9 on 2020-01-02 22:24
import datetime
import pytz

from django.db import migrations

config = [
    {
        "source_name": "Mozilla Hacks",
        "integration_type": "ExternalArticle",
        "source_url": "https://hacks.mozilla.org/feed/",
        "last_sync": datetime.datetime(2020, 1, 1, tzinfo=pytz.utc),
    },
    {
        "source_name": "Mozilla Developer (YouTube)",
        "integration_type": "Video",
        "source_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCh5UlGiu9d6LegIeUCW4N1w",
        "last_sync": datetime.datetime(2020, 1, 1, tzinfo=pytz.utc),
    },
    {
        "source_name": "Layout Land (YouTube)",
        "integration_type": "Video",
        "source_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC7TizprGknbDalbHplROtag",
        "last_sync": datetime.datetime(2020, 1, 1, tzinfo=pytz.utc),
    },
    {
        "source_name": "Mozilla Hacks (YouTube)",
        "integration_type": "Video",
        "source_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCijjo5gfAscWgNCKFHWm1EA",
        "last_sync": datetime.datetime(2020, 1, 1, tzinfo=pytz.utc),
    },
    {
        "source_name": "Mixed Reality Blog",
        "integration_type": "ExternalArticle",
        "source_url": "https://blog.mozvr.com/rss",
        "last_sync": datetime.datetime(2020, 1, 1, tzinfo=pytz.utc),
    },
    {
        "source_name": "Add-ons Blog",
        "integration_type": "ExternalArticle",
        "source_url": "https://blog.mozilla.org/addons/feed",
        "last_sync": datetime.datetime(2020, 1, 1, tzinfo=pytz.utc),
    },
]


def forwards(apps, schema_editor):
    IngestionConfiguration = apps.get_model("ingestion", "IngestionConfiguration")

    for data in config:
        IngestionConfiguration.objects.create(**data)


def backwards(apps, schema_editor):
    IngestionConfiguration = apps.get_model("ingestion", "IngestionConfiguration")

    for data in config:
        ic = IngestionConfiguration.objects.get(source_name=data["source_name"])
        ic.delete()


class Migration(migrations.Migration):

    dependencies = [("ingestion", "0001_initial")]

    operations = [migrations.RunPython(forwards, backwards)]
