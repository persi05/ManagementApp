from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0001_initial'),
        ('tasks', '0008_boardcolumn_is_done_column'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attachment',
            name='url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='attachment',
            name='file',
            field=models.FileField(blank=True, upload_to='task_attachments/%Y/%m/'),
        ),
        migrations.AddField(
            model_name='attachment',
            name='document',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_attachments', to='documents.documentitem'),
        ),
    ]
