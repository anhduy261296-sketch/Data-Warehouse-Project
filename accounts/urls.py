from django.urls import path
from . import views
urlpatterns = [path('login/', views.login_view, name='login'), path('logout/', views.logout_view, name='logout'), path('login/captcha/', views.login_captcha, name='login-captcha')]
