from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required, login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from tracking.core import audit
from . import captcha
from .models import LoginActivityLog

LOCKOUT_CLEARED_DETAIL = 'Cleared by password reset'
_PASSWORD_RULES = {
    'password_too_short': 'Mật khẩu phải có ít nhất 8 ký tự.',
    'password_too_common': 'Mật khẩu này quá phổ biến.',
    'password_entirely_numeric': 'Mật khẩu không được chỉ gồm chữ số.',
    'password_too_similar': 'Mật khẩu quá giống tên đăng nhập hoặc thông tin cá nhân.',
}


def _client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _recent_failures():
    since = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    return LoginActivityLog.objects.filter(action=LoginActivityLog.ACTION_LOGIN_FAILED, created_at__gte=since).exclude(detail=LOCKOUT_CLEARED_DETAIL)


def _is_locked_out(username, ip_address):
    failed = _recent_failures().filter(ip_address=ip_address)
    if failed.count() >= settings.LOGIN_LOCKOUT_IP_ATTEMPTS:
        return True
    return failed.filter(username_attempted=username).count() >= settings.LOGIN_LOCKOUT_ATTEMPTS


def _temp_password_expired(user):
    return user.must_change_password and user.temp_password_expires_at is not None and timezone.now() >= user.temp_password_expires_at


def clear_login_lockout(username):
    """Mở khóa bằng cách đánh dấu các lần sai gần đây để không tính nữa, vẫn giữ dòng trong nhật ký đăng nhập."""
    _recent_failures().filter(username_attempted=username).update(detail=LOCKOUT_CLEARED_DETAIL)


@login_not_required
def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        ip_address = _client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
        if _is_locked_out(username, ip_address):
            LoginActivityLog.objects.create(
                user=None,
                username_attempted=username,
                action=LoginActivityLog.ACTION_LOGIN_FAILED,
                ip_address=ip_address,
                user_agent=user_agent,
                detail='Locked out',
            )
            messages.error(request, f'Đăng nhập sai quá nhiều lần. Vui lòng thử lại sau {settings.LOGIN_LOCKOUT_MINUTES} phút.')
            return render(request, 'accounts/login.html', {'next': request.POST.get('next', ''), 'username': username}, status=429)
        if not captcha.check(request.session, request.POST.get('captcha', '')):
            messages.error(request, 'Mã xác nhận không đúng hoặc đã hết hạn.')
            return render(request, 'accounts/login.html', {'next': request.POST.get('next', ''), 'username': username})
        user = authenticate(request, username=username, password=password)
        if user is not None and _temp_password_expired(user):
            LoginActivityLog.objects.create(
                user=None,
                username_attempted=username,
                action=LoginActivityLog.ACTION_LOGIN_FAILED,
                ip_address=ip_address,
                user_agent=user_agent,
                detail='Temporary password expired',
            )
            messages.error(request, 'Mật khẩu tạm đã hết hạn. Hãy liên hệ quản trị viên để được cấp lại.')
            return render(request, 'accounts/login.html', {'next': request.POST.get('next', ''), 'username': username})
        if user is not None:
            login(request, user)
            request.session.clear_expired()
            LoginActivityLog.objects.create(
                user=user,
                username_attempted=username,
                action=LoginActivityLog.ACTION_LOGIN_SUCCESS,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            next_url = request.POST.get('next') or ''
            if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                next_url = 'home'
            return redirect(next_url)
        LoginActivityLog.objects.create(
            user=None,
            username_attempted=username,
            action=LoginActivityLog.ACTION_LOGIN_FAILED,
            ip_address=ip_address,
            user_agent=user_agent,
            detail='Invalid username or password',
        )
        messages.error(request, 'Sai tên đăng nhập hoặc mật khẩu.')
        return render(request, 'accounts/login.html', {'next': request.POST.get('next', ''), 'username': username})
    return render(request, 'accounts/login.html', {'next': request.GET.get('next', '')})


@login_not_required
def login_captcha(request):
    response = HttpResponse(captcha.render_svg(captcha.new_code(request.session)), content_type='image/svg+xml')
    response['Cache-Control'] = 'no-store, max-age=0'
    return response


@login_required
def logout_view(request):
    if request.method != 'POST':
        return redirect(settings.LOGIN_REDIRECT_URL)
    LoginActivityLog.objects.create(
        user=request.user,
        username_attempted=request.user.username,
        action=LoginActivityLog.ACTION_LOGOUT,
        ip_address=_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
    )
    logout(request)
    return redirect('login')


def _password_change_error(user, current, new, confirm):
    if not user.check_password(current):
        return 'Mật khẩu hiện tại không đúng.'
    if new != confirm:
        return 'Mật khẩu nhập lại không khớp.'
    if new == current:
        return 'Mật khẩu mới phải khác mật khẩu hiện tại.'
    try:
        validate_password(new, user)
    except ValidationError as exc:
        return ' '.join(_PASSWORD_RULES.get(e.code) or ' '.join(e.messages) for e in exc.error_list)
    return None


@login_required
def password_change(request):
    user = request.user
    context = {'forced': user.must_change_password}
    if request.method == 'POST':
        new = request.POST.get('new_password', '')
        error = _password_change_error(user, request.POST.get('current_password', ''), new, request.POST.get('confirm_password', ''))
        if error:
            context['error'] = error
            return render(request, 'accounts/password_change.html', context, status=400)
        forced = user.must_change_password
        user.set_password(new)
        user.must_change_password = False
        user.temp_password_expires_at = None
        user.save(update_fields=['password', 'must_change_password', 'temp_password_expires_at'])
        # Giữ phiên đang dùng; các phiên khác của người này bị đăng xuất vì mật khẩu đã đổi.
        update_session_auth_hash(request, user)
        audit.log('user.password_change', user.get_username(), 'user', user.username)
        if forced:
            return redirect('home')
        context.update(forced=False, saved=True)
    return render(request, 'accounts/password_change.html', context)
