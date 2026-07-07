from django.conf import settings
from django.db import models
from django.utils import timezone


class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Oczekuje'
        APPROVED = 'approved', 'Zaakceptowany'
        REJECTED = 'rejected', 'Odrzucony'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leave_requests')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=240, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_leave_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'start_date']),
            models.Index(fields=['status', 'start_date']),
        ]

    def __str__(self):
        return f'{self.user} {self.start_date:%Y-%m-%d} - {self.end_date:%Y-%m-%d}'

    def set_status(self, status, reviewer):
        self.status = status
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.read_at = None
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'read_at'])

    def mark_as_read(self):
        self.read_at = timezone.now()
        self.save(update_fields=['read_at'])

    @property
    def is_past(self):
        return self.end_date < timezone.localdate()
