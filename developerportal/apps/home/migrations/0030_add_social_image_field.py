# Generated by Django 2.2.6 on 2019-10-01 15:59

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mozimages', '0001_initial'),
        ('home', '0029_update_home_manager'),
    ]

    operations = [
        migrations.AddField(
            model_name='homepage',
            name='social_image',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='mozimages.MozImage'),
        ),
    ]
