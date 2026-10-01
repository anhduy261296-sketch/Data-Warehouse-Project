from django.core.management.base import BaseCommand
from django.utils import timezone
from tracking.models import SystemsTracking

class Command(BaseCommand):
    help = 'Insert sample SystemsTracking rows if the table is empty.'

    def handle(self, *args, **options):
        if SystemsTracking.objects.exists():
            self.stdout.write('AllSystemsTracking already has rows; skip seed.')
            return
        now = timezone.now()
        SystemsTracking.objects.bulk_create([SystemsTracking(name='WMS', status='online', last_seen=now), SystemsTracking(name='OMS', status='degraded', last_seen=now), SystemsTracking(name='SAP', status='offline', last_seen=None)])
        self.stdout.write(self.style.SUCCESS('Seeded 3 sample systems.'))
