from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_not_required, login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from .models import LoginActivityLog

def _client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

def _is_locked_out(username, ip_address):
    """Chống dò mật khẩu: quá nhiều lần sai gần đây theo (tài khoản + IP) hoặc theo riêng IP."""
    since = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    failed = LoginActivityLog.objects.filter(action=LoginActivityLog.ACTION_LOGIN_FAILED, created_at__gte=since, ip_address=ip_address)
    if failed.count() >= settings.LOGIN_LOCKOUT_IP_ATTEMPTS:
        return True
    return failed.filter(username_attempted=username).count() >= settings.LOGIN_LOCKOUT_ATTEMPTS

@login_not_required
def login_view(request):
    if request.user.is_authenticated:
        return redirect('recon-ecom')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        ip_address = _client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
        if _is_locked_out(username, ip_address):
            LoginActivityLog.objects.create(user=None, username_attempted=username, action=LoginActivityLog.ACTION_LOGIN_FAILED, ip_address=ip_address, user_agent=user_agent, detail='Locked out')
            messages.error(request, f'Đăng nhập sai quá nhiều lần. Vui lòng thử lại sau {settings.LOGIN_LOCKOUT_MINUTES} phút.')
            return render(request, 'accounts/login.html', {'next': request.POST.get('next', '')}, status=429)
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            LoginActivityLog.objects.create(user=user, username_attempted=username, action=LoginActivityLog.ACTION_LOGIN_SUCCESS, ip_address=ip_address, user_agent=user_agent)
            next_url = request.POST.get('next') or ''
            # Chỉ cho quay về trang trong hệ thống (chặn link "next" trỏ ra website lạ).
            if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                next_url = 'recon-ecom'
            return redirect(next_url)
        LoginActivityLog.objects.create(user=None, username_attempted=username, action=LoginActivityLog.ACTION_LOGIN_FAILED, ip_address=ip_address, user_agent=user_agent, detail='Invalid username or password')
        messages.error(request, 'Sai tên đăng nhập hoặc mật khẩu.')
    return render(request, 'accounts/login.html', {'next': request.GET.get('next', '')})

@login_required
def logout_view(request):
    LoginActivityLog.objects.create(user=request.user, username_attempted=request.user.username, action=LoginActivityLog.ACTION_LOGOUT, ip_address=_client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', '')[:255])
    logout(request)
    return redirect('login')
