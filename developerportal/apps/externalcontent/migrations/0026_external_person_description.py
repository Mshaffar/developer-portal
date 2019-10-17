# Generated by Django 2.2.6 on 2019-10-17 11:30

from django.db import migrations
import wagtail.core.blocks
import wagtail.core.fields
import wagtail.images.blocks


class Migration(migrations.Migration):

    dependencies = [
        ('externalcontent', '0025_add_social_image_field'),
    ]

    operations = [
        migrations.AlterField(
            model_name='externalarticle',
            name='authors',
            field=wagtail.core.fields.StreamField([('author', wagtail.core.blocks.PageChooserBlock(page_type=['people.Person'])), ('external_author', wagtail.core.blocks.StructBlock([('title', wagtail.core.blocks.CharBlock(label='Name')), ('image', wagtail.images.blocks.ImageChooserBlock()), ('description', wagtail.core.blocks.CharBlock(label='About', required=False)), ('url', wagtail.core.blocks.URLBlock(label='URL', required=False))]))], blank=True, help_text='Optional list of the article’s authors. Use ‘External author’ to add guest authors without creating a profile on the system', null=True),
        ),
    ]
