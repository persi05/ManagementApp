from decimal import Decimal
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from features.projects.models import Project
from features.tasks.models import Task


def local_day_end(value):
    local_value = timezone.localtime(value) if hasattr(value, 'tzinfo') and value.tzinfo else value
    local_date = local_value.date() if isinstance(local_value, datetime) else local_value
    return timezone.make_aware(datetime.combine(local_date, time.max))


def employee_time_entry_edit_deadline(start):
    local_start = timezone.localtime(start)
    days = 3 if local_start.weekday() == 4 else 1
    return local_day_end(local_start.date() + timedelta(days=days))


def month_edit_deadline(value):
    local_value = timezone.localtime(value) if isinstance(value, datetime) else value
    local_date = local_value.date() if isinstance(local_value, datetime) else local_value
    if local_date.month == 12:
        next_month = local_date.replace(year=local_date.year + 1, month=1, day=1)
    else:
        next_month = local_date.replace(month=local_date.month + 1, day=1)
    return timezone.make_aware(datetime.combine(next_month, time.min)) - timedelta(microseconds=1)


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
    inactive_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-start']
        indexes = [models.Index(fields=['user', 'start']), models.Index(fields=['project', 'start'])]

    def __str__(self):
        return f'{self.user} {self.start:%Y-%m-%d %H:%M}'

    @property
    def duration_minutes(self):
        return self.duration_seconds // 60

    @property
    def duration_seconds(self):
        seconds = max(0, int((self.end - self.start).total_seconds()))
        inactive_seconds = max(self.inactive_seconds, self.inactive_minutes * 60)
        return max(0, seconds - inactive_seconds)

    @property
    def hours(self):
        return Decimal(self.duration_minutes) / Decimal(60)

    def can_be_edited_by(self, user):
        from features.accounts.models import is_management

        now = timezone.now()
        if is_management(user):
            return now <= month_edit_deadline(self.start)
        return self.user_id == user.id and now <= self.editable_until


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
    inactive_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.user} {self.get_state_display()}'

    @property
    def total_inactive_seconds(self):
        return max(self.inactive_seconds, self.inactive_minutes * 60)

    def active_seconds(self, now=None):
        now = now or timezone.now()
        end_at = self.paused_at if self.state == self.State.PAUSED and self.paused_at else now
        elapsed_seconds = max(0, int((end_at - self.started_at).total_seconds()))
        return max(0, elapsed_seconds - self.total_inactive_seconds)

    def set_inactive_seconds(self, seconds):
        self.inactive_seconds = max(0, int(seconds))
        self.inactive_minutes = self.inactive_seconds // 60
