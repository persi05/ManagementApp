from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tasks', '0002_remove_task_labels'),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskEditNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='edit_notes', to='tasks.task')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='task_edit_notes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['created_at', 'id'],
            },
        ),
    ]
