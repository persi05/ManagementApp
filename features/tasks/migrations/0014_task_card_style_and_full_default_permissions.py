from django.db import migrations, models


def grant_full_column_permissions(apps, schema_editor):
    BoardColumn = apps.get_model('tasks', 'BoardColumn')
    permission_fields = (
        'client_can_view_column',
        'client_can_create_tasks',
        'client_can_move_to',
        'client_can_edit_tasks',
        'client_can_delete_tasks',
        'employee_can_view_column',
        'employee_can_create_tasks',
        'employee_can_move_to',
        'employee_can_edit_tasks',
        'employee_can_delete_tasks',
        'lead_can_view_column',
        'lead_can_create_tasks',
        'lead_can_move_to',
        'lead_can_edit_tasks',
        'lead_can_delete_tasks',
    )
    BoardColumn.objects.update(**{field_name: True for field_name in permission_fields})


class Migration(migrations.Migration):
    dependencies = [
        ('tasks', '0013_remove_done_column_create_restriction'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='card_color',
            field=models.CharField(
                choices=[
                    ('default', 'Domyslny'),
                    ('green', 'Zielony'),
                    ('blue', 'Niebieski'),
                    ('yellow', 'Zolty'),
                    ('red', 'Czerwony'),
                    ('violet', 'Fioletowy'),
                ],
                default='default',
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name='task',
            name='is_starred',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterModelOptions(
            name='task',
            options={'ordering': ['column__position', '-is_starred', 'position', '-created_at']},
        ),
        migrations.RunPython(grant_full_column_permissions, migrations.RunPython.noop),
    ]
