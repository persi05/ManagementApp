from django.db import migrations


def allow_create_on_first_columns(apps, schema_editor):
    BoardColumn = apps.get_model('tasks', 'BoardColumn')
    first_column_ids = []
    current_project_id = None
    for column in BoardColumn.objects.order_by('project_id', 'position', 'id'):
        if column.project_id == current_project_id:
            continue
        current_project_id = column.project_id
        first_column_ids.append(column.id)

    BoardColumn.objects.filter(id__in=first_column_ids).update(
        client_can_create_tasks=True,
        employee_can_create_tasks=True,
        lead_can_create_tasks=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0012_column_create_visibility_permissions'),
    ]

    operations = [
        migrations.RunPython(allow_create_on_first_columns, migrations.RunPython.noop),
    ]
