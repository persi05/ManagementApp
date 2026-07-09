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
    is_pinned = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', 'kind', 'name']
        indexes = [
            models.Index(fields=['parent', 'is_archived']),
            models.Index(fields=['owner', 'is_archived']),
            models.Index(fields=['kind']),
        ]

    def __str__(self):
        return self.name

    @classmethod
    def visible_to(cls, user):
        if is_management(user):
            return cls.objects.all()
        role = user_role(user)
        return cls.objects.filter(
            Q(owner=user)
            | Q(accesses__user=user)
            | Q(accesses__role=role)
            | Q(parent__accesses__user=user)
            | Q(parent__accesses__role=role)
            | Q(parent__owner=user)
        ).distinct()

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
        if is_management(user) or self.owner_id == user.id:
            return True
        return self.accesses.filter(Q(user=user) | Q(role=user_role(user)), can_manage=True).exists()

    def can_edit(self, user):
        if self.can_manage(user):
            return True
        return self.accesses.filter(Q(user=user) | Q(role=user_role(user)), can_edit=True).exists()


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
        ]

    def __str__(self):
        target = self.user.get_username() if self.user_id else self.get_role_display()
        return f'{self.item} -> {target}'
