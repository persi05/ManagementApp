from django.conf import settings
from django.db import migrations, models


def copy_assignee_to_assignees(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    for task in Task.objects.exclude(assignee_id__isnull=True).iterator():
        task.assignees.add(task.assignee_id)


def copy_first_assignee_back(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    for task in Task.objects.prefetch_related('assignees').iterator():
        first_assignee = task.assignees.order_by('id').first()
        if first_assignee:
            task.assignee_id = first_assignee.id
            task.save(update_fields=['assignee'])


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0010_move_attachment_files_to_documents'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='assignees',
            field=models.ManyToManyField(blank=True, related_name='assigned_tasks', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(copy_assignee_to_assignees, copy_first_assignee_back),
    ]
