from django.conf import settings
from django.db import models


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
