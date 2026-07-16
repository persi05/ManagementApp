from django.db import migrations, models
from django.db.models import Q


def merge_duplicate_accesses(apps, schema_editor):
    DocumentAccess = apps.get_model('documents', 'DocumentAccess')

    groups = {}
    for access in DocumentAccess.objects.order_by('id'):
        key = (access.item_id, access.user_id, access.role or '')
        groups.setdefault(key, []).append(access)

    for duplicates in groups.values():
        if len(duplicates) <= 1:
            continue
        primary = duplicates[0]
        primary.can_edit = any(access.can_edit for access in duplicates)
        primary.can_manage = any(access.can_manage for access in duplicates)
        primary.save(update_fields=['can_edit', 'can_manage'])
        DocumentAccess.objects.filter(id__in=[access.id for access in duplicates[1:]]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0002_document_visibility_block'),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_accesses, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='documentaccess',
            constraint=models.UniqueConstraint(
                fields=('item', 'user'),
                condition=Q(user__isnull=False),
                name='unique_document_access_user',
            ),
        ),
        migrations.AddConstraint(
            model_name='documentaccess',
            constraint=models.UniqueConstraint(
                fields=('item', 'role'),
                condition=Q(user__isnull=True) & ~Q(role=''),
                name='unique_document_access_role',
            ),
        ),
    ]
