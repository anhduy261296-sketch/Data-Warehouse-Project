import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from django.core.management.base import BaseCommand

from tracking.messaging.provider import mask_phone

SCENARIOS = """
Tình huống theo 2 số cuối của SĐT (mặc định: thành công):
  02  HTTP 503 hai lần đầu, lần 3 thành công      -> Đã gửi, 3 lần thử
  03  HTTP 503 mọi lần                            -> Gửi thất bại (tạm thời), 3 lần thử
  04  Lần đầu không phản hồi, lần sau thành công  -> Chưa rõ kết quả; gửi lại thì Đã gửi
  05  status -2 nếu list_param thiếu voucher_name -> Gửi thất bại (cấu hình)
  06  HTTP 502                                    -> Chưa rõ kết quả
  07  Đứt kết nối, không trả gì                   -> Chưa rõ kết quả
Mã template có chữ BAD: status -6 cho mọi số     -> Gửi thất bại (cấu hình), lô tạm dừng sau 5 lỗi liên tiếp
"""


def _handler(hang_seconds: int, stdout):
    calls: dict[str, int] = {}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
            phone = str(payload.get('phonenumber') or '')
            with lock:
                calls[phone] = calls.get(phone, 0) + 1
                nth = calls[phone]
            stdout.write(f'MOCK INCOM sđt={mask_phone(phone)} lần={nth} template={payload.get("templatecode")}\n')
            suffix = phone[-2:]
            if 'BAD' in str(payload.get('templatecode')):
                return self._reply(200, {'idOmniMess': None, 'status': '-6', 'code': f"Can't find template with templatecode: {payload.get('templatecode')}"})
            if (suffix == '02' and nth <= 2) or suffix == '03':
                return self._reply(503, {'message': 'Service Unavailable'})
            if suffix == '04' and nth == 1:
                time.sleep(hang_seconds)
                return None
            if suffix == '05' and 'voucher_name' not in (payload.get('list_param') or {}):
                return self._reply(200, {'status': '-2', 'code': 'Some parameters is missing: voucher_name'})
            if suffix == '06':
                return self._reply(502, {'message': 'Bad Gateway'})
            if suffix == '07':
                self.connection.shutdown(socket.SHUT_RDWR)
                return None
            return self._reply(200, {'idOmniMess': f'ICOMNI-MOCK-{phone}-{nth}', 'status': '1', 'code': 'Success'})

    return Handler


class Command(BaseCommand):
    help = 'API Incom giả để test gửi ZNS, không gửi tin thật. Trỏ ZNS_API_URL vào http://127.0.0.1:<port>/.' + SCENARIOS

    def add_arguments(self, parser):
        parser.add_argument('--port', type=int, default=8765)
        parser.add_argument('--hang', type=int, default=30, help='Số giây không phản hồi ở tình huống 04 (phải lớn hơn ZNS_API_TIMEOUT).')

    def handle(self, *args, **opts):
        server = ThreadingHTTPServer(('127.0.0.1', opts['port']), _handler(opts['hang'], self.stdout))
        self.stdout.write(f'API Incom giả chạy ở http://127.0.0.1:{opts["port"]}/' + SCENARIOS)
        server.serve_forever()
