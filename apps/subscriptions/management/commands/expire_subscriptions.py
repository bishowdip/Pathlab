from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.subscriptions.models import Subscription


class Command(BaseCommand):
    help = "Mark subscriptions whose expires_at has passed as 'expired'. Run daily via cron."

    def handle(self, *args, **opts):
        now = timezone.now()
        qs = Subscription.objects.filter(
            status="active", expires_at__isnull=False, expires_at__lt=now,
        )
        count = qs.update(status="expired")
        self.stdout.write(self.style.SUCCESS(f"✓ Expired {count} subscription(s)."))
