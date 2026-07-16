from django.db import migrations, models


def keep_one_done_column_per_project(apps, schema_editor):
    BoardColumn = apps.get_model('tasks', 'BoardColumn')
    project_ids = BoardColumn.objects.filter(is_done_column=True).values_list('project_id', flat=True).distinct()
    for project_id in project_ids:
        done_ids = list(
            BoardColumn.objects.filter(project_id=project_id, is_done_column=True)
            .order_by('position', 'id')
            .values_list('id', flat=True)
        )
        if len(done_ids) > 1:
            BoardColumn.objects.filter(id__in=done_ids[1:]).update(is_done_column=False)


class Migration(migrations.Migration):
    dependencies = [
        ('tasks', '0014_task_card_style_and_full_default_permissions'),
    ]

    operations = [
        migrations.RunPython(keep_one_done_column_per_project, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='boardcolumn',
            constraint=models.UniqueConstraint(
                condition=models.Q(is_done_column=True),
                fields=('project',),
                name='unique_done_column_per_project',
            ),
        ),
    ]
