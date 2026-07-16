import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0004_documentpin'),
        ('projects', '0002_client_rates'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentitem',
            name='project',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='document_items',
                to='projects.project',
            ),
        ),
    ]
