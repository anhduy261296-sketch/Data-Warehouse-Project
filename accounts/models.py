from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    employee_code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    role = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        db_table = 'AppUser'

    def __str__(self):
        return self.username

class LoginActivityLog(models.Model):
    ACTION_LOGIN_SUCCESS = 'LOGIN_SUCCESS'
    ACTION_LOGIN_FAILED = 'LOGIN_FAILED'
    ACTION_LOGOUT = 'LOGOUT'
    ACTION_CHOICES = [(ACTION_LOGIN_SUCCESS, 'Login success'), (ACTION_LOGIN_FAILED, 'Login failed'), (ACTION_LOGOUT, 'Logout')]
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='activity_logs')
    username_attempted = models.CharField(max_length=150)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)
    detail = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'LogActivity'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.username_attempted} - {self.action} - {self.created_at}'
