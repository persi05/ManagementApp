from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from features.accounts.models import UserProfile, is_management, user_role


class DocumentItem(models.Model):
    class Kind(models.TextChoices):
        FOLDER = 'folder', 'Folder'
        DOCUMENT = 'document', 'Dokument'
        FILE = 'file', 'Plik'
        IMAGE = 'image', 'Zdjęcie'

    name = models.CharField(max_length=180)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    file = models.FileField(upload_to='documents/%Y/%m/', blank=True)
    content = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='document_items')
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='document_items',
    )
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['kind', 'name']
        indexes = [
            models.Index(fields=['parent', 'is_archived']),
            models.Index(fields=['owner', 'is_archived']),
            models.Index(fields=['kind']),
        ]

    def __str__(self):
        return self.name

    @classmethod
    def visible_to(cls, user):
        qs = cls.objects.all()
        if not user.is_superuser:
            qs = qs.exclude(Q(visibility_blocks__user=user) | Q(parent__visibility_blocks__user=user))
        if is_management(user):
            return qs
        role = user_role(user)
        return qs.filter(
            Q(owner=user)
            | Q(project__members=user)
            | Q(project__client=user)
            | Q(accesses__user=user)
            | Q(accesses__role=role)
            | Q(parent__accesses__user=user)
            | Q(parent__accesses__role=role)
            | Q(parent__owner=user)
            | Q(parent__project__members=user)
            | Q(parent__project__client=user)
            | Q(task_attachments__task__project__members=user)
            | Q(task_attachments__task__project__client=user)
            | Q(task_attachments__task__assignee=user)
            | Q(task_attachments__task__assignees=user)
        ).distinct()

    def can_assign_project(self, user):
        return is_management(user) or self.owner_id == user.id

    @property
    def is_file_like(self):
        return self.kind in {self.Kind.FILE, self.Kind.IMAGE}

    @property
    def extension(self):
        if self.file:
            return self.file.name.rsplit('.', 1)[-1].upper() if '.' in self.file.name else 'PLIK'
        if self.kind == self.Kind.FOLDER:
            return 'Folder'
        return 'DOC'

    @property
    def size_label(self):
        if not self.file:
            return '—'
        try:
            size = self.file.size
        except OSError:
            return '—'
        if size >= 1024 * 1024:
            return f'{size / (1024 * 1024):.1f} MB'
        if size >= 1024:
            return f'{size / 1024:.0f} KB'
        return f'{size} B'

    @property
    def modified_label(self):
        local_date = timezone.localtime(self.updated_at).date()
        today = timezone.localdate()
        if local_date == today:
            return 'dziś'
        if local_date == today - timedelta(days=1):
            return 'wczoraj'
        return local_date.strftime('%Y-%m-%d')

    def can_manage(self, user):
        if is_management(user):
            return True
        user_access = self.accesses.filter(user=user).first()
        if user_access is not None:
            return user_access.can_manage
        if self.owner_id == user.id:
            return True
        return self.accesses.filter(role=user_role(user), can_manage=True).exists()

    def can_edit(self, user):
        if is_management(user):
            return True
        user_access = self.accesses.filter(user=user).first()
        if user_access is not None:
            return user_access.can_edit
        if self.owner_id == user.id:
            return True
        return self.accesses.filter(role=user_role(user), can_edit=True).exists()

    def delete(self, *args, **kwargs):
        file_name = self.file.name if self.file else ''
        super().delete(*args, **kwargs)
        if file_name and not type(self).objects.filter(file=file_name).exists():
            self.file.storage.delete(file_name)


class DocumentAccess(models.Model):
    item = models.ForeignKey(DocumentItem, on_delete=models.CASCADE, related_name='accesses')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='document_accesses')
    role = models.CharField(max_length=20, choices=UserProfile.Role.choices, blank=True)
    can_edit = models.BooleanField(default=False)
    can_manage = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['role', 'user__username']
        constraints = [
            models.CheckConstraint(
                condition=Q(user__isnull=False) | ~Q(role=''),
                name='documents_access_user_or_role',
            ),
            models.UniqueConstraint(
                fields=('item', 'user'),
                condition=Q(user__isnull=False),
                name='unique_document_access_user',
            ),
            models.UniqueConstraint(
                fields=('item', 'role'),
                condition=Q(user__isnull=True) & ~Q(role=''),
                name='unique_document_access_role',
            ),
        ]

    def __str__(self):
        target = self.user.get_username() if self.user_id else self.get_role_display()
        return f'{self.item} -> {target}'


class DocumentVisibilityBlock(models.Model):
    item = models.ForeignKey(DocumentItem, on_delete=models.CASCADE, related_name='visibility_blocks')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='document_visibility_blocks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['user__username']
        constraints = [
            models.UniqueConstraint(fields=['item', 'user'], name='unique_document_visibility_block'),
        ]

    def __str__(self):
        return f'{self.item} hidden from {self.user.get_username()}'


class DocumentPin(models.Model):
    item = models.ForeignKey(DocumentItem, on_delete=models.CASCADE, related_name='user_pins')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='document_pins')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('item', 'user'), name='unique_document_pin_per_user'),
        ]

    def __str__(self):
        return f'{self.user.get_username()} pinned {self.item}'
