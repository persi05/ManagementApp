from django.db import migrations, models


def notification_defaults(position, max_position):
    return {
        'notify_client_on_task_create': position == 0,
        'notify_client_on_note': position == 0,
        'notify_client_on_move_to': position == max_position,
        'notify_assignee_on_move_to': True,
    }


def backfill_notification_settings(apps, schema_editor):
    BoardColumn = apps.get_model('tasks', 'BoardColumn')
    project_ids = BoardColumn.objects.values_list('project_id', flat=True).distinct()
    for project_id in project_ids:
        columns = list(BoardColumn.objects.filter(project_id=project_id).order_by('position', 'id'))
        if not columns:
            continue
        max_position = columns[-1].position
        for column in columns:
            for field_name, value in notification_defaults(column.position, max_position).items():
                setattr(column, field_name, value)
            column.save(update_fields=list(notification_defaults(column.position, max_position).keys()))


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0006_notification_title_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='boardcolumn',
            name='notify_assignee_on_move_to',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='notify_client_on_move_to',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='notify_client_on_note',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='notify_client_on_task_create',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(backfill_notification_settings, migrations.RunPython.noop),
    ]
