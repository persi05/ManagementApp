from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from features.tasks.models import Notification


class Command(BaseCommand):
    help = 'Usuwa stare powiadomienia zgodnie z retencja ustawiona w env.'

    def handle(self, *args, **options):
        now = timezone.now()
        read_cutoff = now - timezone.timedelta(days=settings.NOTIFICATIONS_READ_RETENTION_DAYS)
        unread_cutoff = now - timezone.timedelta(days=settings.NOTIFICATIONS_UNREAD_RETENTION_DAYS)

        read_deleted, _ = Notification.objects.filter(is_read=True, created_at__lt=read_cutoff).delete()
        unread_deleted, _ = Notification.objects.filter(is_read=False, created_at__lt=unread_cutoff).delete()

        self.stdout.write(self.style.SUCCESS(
            f'Usunieto powiadomienia: przeczytane={read_deleted}, nieprzeczytane={unread_deleted}.'
        ))
