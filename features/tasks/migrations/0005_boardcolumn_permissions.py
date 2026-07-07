from django.db import migrations, models


def default_permissions_for_position(position):
    defaults = {
        'client_can_move_to': False,
        'client_can_edit_tasks': False,
        'client_can_delete_tasks': False,
        'employee_can_move_to': False,
        'employee_can_edit_tasks': False,
        'employee_can_delete_tasks': False,
        'lead_can_move_to': False,
        'lead_can_edit_tasks': False,
        'lead_can_delete_tasks': False,
    }
    if position == 0:
        defaults.update({
            'client_can_edit_tasks': True,
            'client_can_delete_tasks': True,
            'employee_can_move_to': True,
            'employee_can_edit_tasks': True,
            'employee_can_delete_tasks': True,
            'lead_can_move_to': True,
            'lead_can_edit_tasks': True,
            'lead_can_delete_tasks': True,
        })
    elif position == 1:
        defaults.update({
            'employee_can_move_to': True,
            'employee_can_edit_tasks': True,
            'lead_can_move_to': True,
            'lead_can_edit_tasks': True,
        })
    elif position == 2:
        defaults.update({
            'employee_can_move_to': True,
            'lead_can_move_to': True,
            'lead_can_edit_tasks': True,
        })
    else:
        defaults.update({
            'lead_can_move_to': True,
        })
    return defaults


def backfill_board_column_permissions(apps, schema_editor):
    BoardColumn = apps.get_model('tasks', 'BoardColumn')
    for column in BoardColumn.objects.all():
        for field_name, value in default_permissions_for_position(column.position).items():
            setattr(column, field_name, value)
        column.save(update_fields=list(default_permissions_for_position(column.position).keys()))


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0004_task_labels'),
    ]

    operations = [
        migrations.AddField(
            model_name='boardcolumn',
            name='client_can_delete_tasks',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='client_can_edit_tasks',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='client_can_move_to',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='employee_can_delete_tasks',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='employee_can_edit_tasks',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='employee_can_move_to',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='lead_can_delete_tasks',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='lead_can_edit_tasks',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='boardcolumn',
            name='lead_can_move_to',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(backfill_board_column_permissions, migrations.RunPython.noop),
    ]
