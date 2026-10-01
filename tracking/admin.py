from django.contrib import admin
from .models import SystemsTracking

@admin.register(SystemsTracking)
class SystemsTrackingAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'last_seen', 'updated_at')
    search_fields = ('name', 'status')
