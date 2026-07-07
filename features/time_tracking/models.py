from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from features.projects.models import Project
from features.tasks.models import Task


class TimeEntry(models.Model):
    class Source(models.TextChoices):
        AUTO = 'auto', 'Automatyczny'
        MANUAL = 'manual', 'Ręczny'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='time_entries')
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='time_entries')
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True, related_name='time_entries')
    start = models.DateTimeField()
    end = models.DateTimeField()
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL)
    comment = models.CharField(max_length=240, blank=True)
    editable_until = models.DateTimeField()
    edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='edited_time_entries')
    edited_at = models.DateTimeField(null=True, blank=True)
    inactive_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-start']
        indexes = [models.Index(fields=['user', 'start']), models.Index(fields=['project', 'start'])]

    def __str__(self):
        return f'{self.user} {self.start:%Y-%m-%d %H:%M}'

    @property
    def duration_minutes(self):
        seconds = max(0, int((self.end - self.start).total_seconds()))
        return max(0, seconds // 60 - self.inactive_minutes)

    @property
    def hours(self):
        return Decimal(self.duration_minutes) / Decimal(60)

    def can_be_edited_by(self, user):
        from features.accounts.models import is_management

        return is_management(user) or (self.user_id == user.id and timezone.now() <= self.editable_until)


class WorkSession(models.Model):
    class State(models.TextChoices):
        RUNNING = 'running', 'Uruchomiona'
        PAUSED = 'paused', 'Pauza'
        STOPPED = 'stopped', 'Zakończona'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='work_sessions')
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    paused_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.RUNNING)
    inactive_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.user} {self.get_state_display()}'
