from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_not_required, login_required
from django.shortcuts import redirect, render
from .models import LoginActivityLog

def _client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

@login_not_required
def login_view(request):
    if request.user.is_authenticated:
        return redirect('recon-ecom')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        ip_address = _client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            LoginActivityLog.objects.create(user=user, username_attempted=username, action=LoginActivityLog.ACTION_LOGIN_SUCCESS, ip_address=ip_address, user_agent=user_agent)
            next_url = request.POST.get('next') or 'recon-ecom'
            return redirect(next_url)
        LoginActivityLog.objects.create(user=None, username_attempted=username, action=LoginActivityLog.ACTION_LOGIN_FAILED, ip_address=ip_address, user_agent=user_agent, detail='Invalid username or password')
        messages.error(request, 'Sai tên đăng nhập hoặc mật khẩu.')
    return render(request, 'accounts/login.html', {'next': request.GET.get('next', '')})

@login_required
def logout_view(request):
    LoginActivityLog.objects.create(user=request.user, username_attempted=request.user.username, action=LoginActivityLog.ACTION_LOGOUT, ip_address=_client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', '')[:255])
    logout(request)
    return redirect('login')
