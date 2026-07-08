from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Aktywny'
        PAUSED = 'paused', 'Wstrzymany'
        DONE = 'done', 'Zakończony'

    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='client_projects')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    client_hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    client_rate_currency = models.CharField(max_length=8, default='PLN')
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


class ProjectLabelRate(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='label_rates')
    label = models.CharField(max_length=80)
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=8, default='PLN')

    class Meta:
        ordering = ['label']
        unique_together = ('project', 'label')

    def __str__(self):
        return f'{self.project}: {self.label} - {self.hourly_rate} {self.currency}/h'


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
