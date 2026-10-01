from django.db import models

class SystemsTracking(models.Model):
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=50)
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'AllSystemsTracking'
        ordering = ['name']

    def __str__(self):
        return self.name
