from django.core.management.base import BaseCommand, CommandError

from tracking.messaging import provider, sending
from tracking.messaging.values import MessagingError


class Command(BaseCommand):
    help = 'Chạy tiếp lô ZNS đang "Đang gửi" (vd. server restart giữa chừng). Mặc định dry_run, chỉ gửi thật khi ZNS_SEND_MODE=live.'

    def add_arguments(self, parser):
        parser.add_argument('batch_id', type=int)

    def handle(self, *args, **opts):
        self.stdout.write(f'Chế độ gửi: {provider.send_mode()}')
        try:
            counts = sending.run_send(opts['batch_id'])
        except MessagingError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'Xong lô #{opts["batch_id"]}: {counts}'))
