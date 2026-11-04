from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render

from accounts.views import _client_ip

from . import access
from .core import audit

DENIED_MESSAGE = 'Bạn không có quyền thực hiện thao tác này.'


class AccessControlMiddleware:
    """Chặn route theo danh mục quyền. Route chưa khai báo trong tracking.access mặc định bị chặn."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = audit.client_ip.set(_client_ip(request))
        try:
            return self.get_response(request)
        finally:
            audit.client_ip.reset(token)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if not getattr(view_func, 'login_required', True) or not request.user.is_authenticated or match.namespace == 'admin':
            return None
        if access.can_open(request.user, match.url_name):
            return None
        audit.log('access.denied', request.user.get_username(), 'route', match.url_name, f'{request.method} {request.path}')
        if request.path.startswith('/api/'):
            return JsonResponse({'error': DENIED_MESSAGE}, status=403)
        return render(request, '403.html', status=403)
