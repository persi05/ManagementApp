import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0001_initial'),
        ('projects', '0002_client_rates'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='default_tasks_project',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='default_for_profiles',
                to='projects.project',
            ),
        ),
    ]
