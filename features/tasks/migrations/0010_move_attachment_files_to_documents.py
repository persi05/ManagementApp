from django.db import migrations, models


IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'}


def attachment_owner_id(attachment, User):
    task = attachment.task
    if task.created_by_id:
        return task.created_by_id
    if task.assignee_id:
        return task.assignee_id
    if task.project.client_id:
        return task.project.client_id
    member_id = task.project.members.values_list('id', flat=True).first()
    if member_id:
        return member_id
    return User.objects.order_by('id').values_list('id', flat=True).first()


def document_kind_for_file(file_name):
    extension = file_name.lower().rsplit('.', 1)[-1] if '.' in file_name else ''
    return 'image' if extension in IMAGE_EXTENSIONS else 'file'


def migrate_attachment_files(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Attachment = apps.get_model('tasks', 'Attachment')
    DocumentItem = apps.get_model('documents', 'DocumentItem')
    DocumentAccess = apps.get_model('documents', 'DocumentAccess')

    attachments = (
        Attachment.objects
        .filter(document__isnull=True)
        .exclude(file='')
        .select_related('task', 'task__project')
    )
    for attachment in attachments:
        owner_id = attachment_owner_id(attachment, User)
        if not owner_id:
            continue

        file_name = attachment.file.name.rsplit('/', 1)[-1] if attachment.file else ''
        name = attachment.name or file_name or 'Zalacznik'
        document = DocumentItem.objects.create(
            owner_id=owner_id,
            name=name,
            kind=document_kind_for_file(file_name),
            file=attachment.file,
        )
        attachment.document = document
        attachment.name = name
        attachment.save(update_fields=['document', 'name'])

        user_ids = set(attachment.task.project.members.values_list('id', flat=True))
        if attachment.task.project.client_id:
            user_ids.add(attachment.task.project.client_id)
        user_ids.discard(owner_id)
        for user_id in user_ids:
            DocumentAccess.objects.get_or_create(
                item=document,
                user_id=user_id,
                defaults={'can_edit': False, 'can_manage': False},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0009_task_attachment_files_documents'),
    ]

    operations = [
        migrations.RunPython(migrate_attachment_files, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='attachment',
            name='file',
        ),
        migrations.AlterField(
            model_name='attachment',
            name='document',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='task_attachments', to='documents.documentitem'),
        ),
    ]
