from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0005_documentitem_project'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='documentitem',
            options={'ordering': ['kind', 'name']},
        ),
        migrations.RemoveField(
            model_name='documentitem',
            name='is_pinned',
        ),
    ]
