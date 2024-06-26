# Generated by Django 5.0.6 on 2024-06-28 17:04

import mdeditor.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sbook", "0020_alter_event_event_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="Faq",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("question", mdeditor.fields.MDTextField()),
                ("answer", mdeditor.fields.MDTextField()),
                ("stars", models.IntegerField(default=0)),
            ],
        ),
    ]
