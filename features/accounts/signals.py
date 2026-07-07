from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=UserProfile)
def sync_management_staff_flag(sender, instance, **kwargs):
    should_be_staff = instance.role == UserProfile.Role.MANAGEMENT
    if instance.user.is_staff != should_be_staff:
        instance.user.is_staff = should_be_staff
        if not should_be_staff:
            instance.user.is_superuser = False
            instance.user.save(update_fields=['is_staff', 'is_superuser'])
        else:
            instance.user.save(update_fields=['is_staff'])
