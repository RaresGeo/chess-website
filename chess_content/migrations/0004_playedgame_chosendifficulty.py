# Generated by Django 4.2.3 on 2023-09-14 21:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chess_content', '0003_playedgame_gotcorrectroundnumber'),
    ]

    operations = [
        migrations.AddField(
            model_name='playedgame',
            name='chosenDifficulty',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
