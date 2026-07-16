from django.db import migrations, models


def backfill_column_create_visibility_permissions(apps, schema_editor):
    BoardColumn = apps.get_model('tasks', 'BoardColumn')
    projects = {}
    for column in BoardColumn.objects.order_by('project_id', 'position', 'id'):
        projects.setdefault(column.project_id, []).append(column)

    for columns in projects.values():
        first_column_id = columns[0].id if columns else None
        for column in columns:
            can_create = column.id == first_column_id
            column.client_can_view_column = True
            column.employee_can_view_column = True
            column.lead_can_view_column = True
            column.client_can_create_tasks = can_create
            column.employee_can_create_tasks = can_create
            column.lead_can_create_tasks = can_create
            column.save(update_fields=[
                'client_can_view_column',
                'employee_can_view_column',
                'lead_can_view_column',
                'client_can_create_tasks',
                'employee_can_create_tasks',
                'lead_can_create_tasks',
            ])


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0011_task_assignees'),
    ]

    operations = [
        migrations.AddField(
            model_name='boardcolumn',
            name='client_can_create_tasks',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='client_can_view_column',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='employee_can_create_tasks',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='employee_can_view_column',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='lead_can_create_tasks',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='lead_can_view_column',
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(backfill_column_create_visibility_permissions, migrations.RunPython.noop),
    ]
