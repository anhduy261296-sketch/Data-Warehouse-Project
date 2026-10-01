from django.contrib import admin
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.urls import include, path
urlpatterns = [path('admin/', admin.site.urls), path('favicon.ico', login_not_required(lambda request: HttpResponse(status=204))), path('', include('accounts.urls')), path('', include('tracking.urls'))]
