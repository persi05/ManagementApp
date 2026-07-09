from django.db import migrations, models


DONE_COLUMN_NAMES = {
    'done',
    'skonczone',
    'skończone',
    'zakonczone',
    'zakończone',
    'zrobione',
}


def backfill_done_columns(apps, schema_editor):
    BoardColumn = apps.get_model('tasks', 'BoardColumn')
    for column in BoardColumn.objects.all():
        if column.name.strip().casefold() in DONE_COLUMN_NAMES:
            column.is_done_column = True
            column.save(update_fields=['is_done_column'])


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0007_boardcolumn_notification_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='boardcolumn',
            name='is_done_column',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(backfill_done_columns, migrations.RunPython.noop),
    ]
