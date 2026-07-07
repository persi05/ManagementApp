from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0003_taskeditnote'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='labels',
            field=models.CharField(blank=True, max_length=180),
        ),
    ]
