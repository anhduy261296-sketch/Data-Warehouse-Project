from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.CreateModel(name='SystemsTracking', fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('name', models.CharField(max_length=255)), ('status', models.CharField(max_length=50)), ('last_seen', models.DateTimeField(blank=True, null=True)), ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True))], options={'db_table': 'AllSystemsTracking', 'ordering': ['name']})]
