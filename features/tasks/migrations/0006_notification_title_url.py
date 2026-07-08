from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0005_boardcolumn_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='title',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='notification',
            name='url',
            field=models.CharField(blank=True, max_length=240),
        ),
    ]
