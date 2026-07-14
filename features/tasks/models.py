from decimal import Decimal
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from features.projects.models import Project


class BoardColumn(models.Model):
    PERMISSION_FIELDS = (
        'client_can_move_to',
        'client_can_edit_tasks',
        'client_can_delete_tasks',
        'employee_can_move_to',
        'employee_can_edit_tasks',
        'employee_can_delete_tasks',
        'lead_can_move_to',
        'lead_can_edit_tasks',
        'lead_can_delete_tasks',
    )
    NOTIFICATION_FIELDS = (
        'notify_client_on_task_create',
        'notify_client_on_note',
        'notify_client_on_move_to',
        'notify_assignee_on_move_to',
    )

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='columns')
    name = models.CharField(max_length=80)
    position = models.PositiveIntegerField(default=0)
    is_done_column = models.BooleanField(default=False)
    client_can_move_to = models.BooleanField(default=False)
    client_can_edit_tasks = models.BooleanField(default=False)
    client_can_delete_tasks = models.BooleanField(default=False)
    employee_can_move_to = models.BooleanField(default=False)
    employee_can_edit_tasks = models.BooleanField(default=False)
    employee_can_delete_tasks = models.BooleanField(default=False)
    lead_can_move_to = models.BooleanField(default=False)
    lead_can_edit_tasks = models.BooleanField(default=False)
    lead_can_delete_tasks = models.BooleanField(default=False)
    notify_client_on_task_create = models.BooleanField(default=False)
    notify_client_on_note = models.BooleanField(default=False)
    notify_client_on_move_to = models.BooleanField(default=False)
    notify_assignee_on_move_to = models.BooleanField(default=True)

    class Meta:
        ordering = ['position', 'id']

    @staticmethod
    def default_permissions_for_position(position):
        defaults = {field_name: False for field_name in BoardColumn.PERMISSION_FIELDS}
        if position == 0:
            defaults.update({
                'client_can_edit_tasks': True,
                'client_can_delete_tasks': True,
                'employee_can_move_to': True,
                'employee_can_edit_tasks': True,
                'employee_can_delete_tasks': True,
                'lead_can_move_to': True,
                'lead_can_edit_tasks': True,
                'lead_can_delete_tasks': True,
            })
        elif position == 1:
            defaults.update({
                'employee_can_move_to': True,
                'employee_can_edit_tasks': True,
                'lead_can_move_to': True,
                'lead_can_edit_tasks': True,
            })
        elif position == 2:
            defaults.update({
                'employee_can_move_to': True,
                'lead_can_move_to': True,
                'lead_can_edit_tasks': True,
            })
        else:
            defaults.update({
                'lead_can_move_to': True,
            })
        return defaults

    @staticmethod
    def default_notifications_for_position(position):
        return {
            'notify_client_on_task_create': position == 0,
            'notify_client_on_note': position == 0,
            'notify_client_on_move_to': position >= 3,
            'notify_assignee_on_move_to': True,
        }

    def save(self, *args, **kwargs):
        if self._state.adding and not any(getattr(self, field_name) for field_name in self.PERMISSION_FIELDS):
            for field_name, value in self.default_permissions_for_position(self.position).items():
                setattr(self, field_name, value)
        client_notification_fields = (
            'notify_client_on_task_create',
            'notify_client_on_note',
            'notify_client_on_move_to',
        )
        if self._state.adding and not any(getattr(self, field_name) for field_name in client_notification_fields):
            for field_name, value in self.default_notifications_for_position(self.position).items():
                if field_name in client_notification_fields:
                    setattr(self, field_name, value)
        super().save(*args, **kwargs)

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
    assignees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='assigned_tasks')
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.MEDIUM)
    labels = models.CharField(max_length=180, blank=True)
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

    @property
    def labels_list(self):
        return [label.strip() for label in self.labels.split(',') if label.strip()]

    @property
    def assignees_list(self):
        assigned = list(self.assignees.all())
        if assigned:
            return assigned
        return [self.assignee] if self.assignee_id else []


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

    @staticmethod
    def employee_edit_deadline(worklog_date):
        return timezone.make_aware(datetime.combine(worklog_date, time.max))

    @staticmethod
    def management_edit_deadline(worklog_date):
        if worklog_date.month == 12:
            next_month = worklog_date.replace(year=worklog_date.year + 1, month=1, day=1)
        else:
            next_month = worklog_date.replace(month=worklog_date.month + 1, day=1)
        return timezone.make_aware(datetime.combine(next_month, time.min)) - timedelta(microseconds=1)

    def can_be_edited_by(self, user):
        from features.accounts.models import is_management

        now = timezone.now()
        if is_management(user):
            return now <= self.management_edit_deadline(self.date)
        return self.user_id == user.id and now <= self.employee_edit_deadline(self.date)


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
    url = models.URLField(blank=True)
    document = models.ForeignKey('documents.DocumentItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='task_attachments')

    def __str__(self):
        return self.name


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=120, blank=True)
    content = models.CharField(max_length=240)
    kind = models.CharField(max_length=40, default='system')
    url = models.CharField(max_length=240, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title or self.content
