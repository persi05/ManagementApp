from django.conf import settings
from django.db import models
from django.utils import timezone


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
        constraints = [
            models.UniqueConstraint(fields=['user', 'valid_from'], name='unique_hourly_rate_per_user_date'),
        ]

    def __str__(self):
        return f'{self.user}: {self.amount} {self.currency} od {self.valid_from}'


class EmployeeCharge(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employee_charges')
    name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    starts_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_employee_charges',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-starts_at', '-created_at']

    def __str__(self):
        return f'{self.name}: {self.amount} PLN ({self.user})'
