from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


class UserProfile(models.Model):
    class Role(models.TextChoices):
        CLIENT = 'client', 'Klient'
        EMPLOYEE = 'employee', 'Pracownik'
        MANAGEMENT = 'management', 'Management'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE)
    bank_account = models.CharField(max_length=64, blank=True)
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        name = self.user.get_full_name() or self.user.username
        return f'{name} ({self.get_role_display()})'


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Aktywny'
        PAUSED = 'paused', 'Wstrzymany'
        DONE = 'done', 'Zakończony'

    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='client_projects')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through='ProjectAssignment', related_name='assigned_projects')

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['status']), models.Index(fields=['client'])]

    def __str__(self):
        return self.name

    @property
    def visible_hours(self):
        return self.tasks.aggregate(total=Sum('worklogs__hours', filter=Q(worklogs__visible_to_client=True)))['total'] or Decimal('0')


class ProjectAssignment(models.Model):
    class ProjectRole(models.TextChoices):
        CLIENT = 'client', 'Klient'
        EMPLOYEE = 'employee', 'Pracownik'
        LEAD = 'lead', 'Lead'

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    project_role = models.CharField(max_length=20, choices=ProjectRole.choices, default=ProjectRole.EMPLOYEE)

    class Meta:
        unique_together = ('project', 'user')

    def __str__(self):
        return f'{self.user} -> {self.project}'


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


class ChecklistItem(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='checklist')
    text = models.CharField(max_length=180)
    is_done = models.BooleanField(default=False)

    def __str__(self):
        return self.text


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


class HourlyRate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hourly_rates')
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3, default='PLN')
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_rates')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-valid_from']

    def __str__(self):
        return f'{self.user}: {self.amount} {self.currency} od {self.valid_from}'


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


def is_management(user):
    profile = getattr(user, 'profile', None)
    return user.is_authenticated and (user.is_superuser or getattr(profile, 'role', None) == UserProfile.Role.MANAGEMENT)


def user_role(user):
    if not user.is_authenticated:
        return None
    return getattr(getattr(user, 'profile', None), 'role', UserProfile.Role.EMPLOYEE)


def ensure_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile
