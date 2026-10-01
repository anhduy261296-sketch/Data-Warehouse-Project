from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import LoginActivityLog, User

@admin.register(User)
class AppUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('Thông tin bổ sung', {'fields': ('employee_code', 'department', 'role')}),)
    list_display = ('username', 'email', 'employee_code', 'department', 'role', 'is_staff')

@admin.register(LoginActivityLog)
class LoginActivityLogAdmin(admin.ModelAdmin):
    list_display = ('username_attempted', 'action', 'ip_address', 'created_at')
    list_filter = ('action',)
    search_fields = ('username_attempted', 'ip_address')
    readonly_fields = [f.name for f in LoginActivityLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
