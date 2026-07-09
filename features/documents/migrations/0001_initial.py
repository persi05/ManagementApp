# Generated manually for documents module.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.db.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=180)),
                ('kind', models.CharField(choices=[('folder', 'Folder'), ('document', 'Dokument'), ('file', 'Plik'), ('image', 'Zdjęcie')], max_length=20)),
                ('file', models.FileField(blank=True, upload_to='documents/%Y/%m/')),
                ('content', models.TextField(blank=True)),
                ('is_pinned', models.BooleanField(default=False)),
                ('is_archived', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_items', to=settings.AUTH_USER_MODEL)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='documents.documentitem')),
            ],
            options={
                'ordering': ['-is_pinned', 'kind', 'name'],
            },
        ),
        migrations.CreateModel(
            name='DocumentAccess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(blank=True, choices=[('client', 'Klient'), ('employee', 'Pracownik'), ('management', 'Management')], max_length=20)),
                ('can_edit', models.BooleanField(default=False)),
                ('can_manage', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='accesses', to='documents.documentitem')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='document_accesses', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['role', 'user__username'],
            },
        ),
        migrations.AddIndex(
            model_name='documentitem',
            index=models.Index(fields=['parent', 'is_archived'], name='documents_d_parent__55c84e_idx'),
        ),
        migrations.AddIndex(
            model_name='documentitem',
            index=models.Index(fields=['owner', 'is_archived'], name='documents_d_owner_i_7aaf99_idx'),
        ),
        migrations.AddIndex(
            model_name='documentitem',
            index=models.Index(fields=['kind'], name='documents_d_kind_89e682_idx'),
        ),
        migrations.AddConstraint(
            model_name='documentaccess',
            constraint=models.CheckConstraint(condition=(models.Q(('user__isnull', False)) | ~models.Q(('role', ''))), name='documents_access_user_or_role'),
        ),
    ]
