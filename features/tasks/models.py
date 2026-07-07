from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from features.projects.models import Project


class BoardColumn(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='columns')
    name = models.CharField(max_length=80)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return f'{self.project}: {self.name}'


class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = 'low', 'Niski'
        MEDIUM = 'medium', 'Średni'
        HIGH = 'high', 'Wysoki'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    column = models.ForeignKey(BoardColumn, on_delete=models.PROTECT, related_name='tasks')
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.MEDIUM)
    position = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['column__position', 'position', '-created_at']
        indexes = [models.Index(fields=['project', 'column']), models.Index(fields=['assignee'])]

    def __str__(self):
        return self.title

    @property
    def total_hours(self):
        return self.worklogs.aggregate(total=Sum('hours'))['total'] or Decimal('0')

    @property
    def client_hours(self):
        return self.worklogs.filter(visible_to_client=True).aggregate(total=Sum('hours'))['total'] or Decimal('0')


class TaskEditNote(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='edit_notes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='task_edit_notes')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.task}: {self.user}'


class ChecklistItem(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='checklist')
    text = models.CharField(max_length=180)
    is_done = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class TaskWorklog(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='worklogs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='task_worklogs')
    hours = models.DecimalField(max_digits=6, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    comment = models.CharField(max_length=240, blank=True)
    visible_to_client = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        indexes = [models.Index(fields=['user', 'date']), models.Index(fields=['task', 'visible_to_client'])]

    def __str__(self):
        return f'{self.task}: {self.hours}h'


class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class Attachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    name = models.CharField(max_length=160)
    url = models.URLField()

    def __str__(self):
        return self.name


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    content = models.CharField(max_length=240)
    kind = models.CharField(max_length=40, default='system')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
