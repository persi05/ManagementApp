from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_owner_pins(apps, schema_editor):
    DocumentItem = apps.get_model('documents', 'DocumentItem')
    DocumentPin = apps.get_model('documents', 'DocumentPin')
    DocumentPin.objects.bulk_create([
        DocumentPin(item_id=item.id, user_id=item.owner_id)
        for item in DocumentItem.objects.filter(is_pinned=True)
    ], ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ('documents', '0003_merge_duplicate_document_access'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentPin',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_pins', to='documents.documentitem')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_pins', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('item', 'user'), name='unique_document_pin_per_user')],
            },
        ),
        migrations.RunPython(migrate_owner_pins, migrations.RunPython.noop),
    ]
