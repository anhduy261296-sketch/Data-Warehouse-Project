from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('tracking', '0001_initial')]
    operations = [
        migrations.SeparateDatabaseAndState(state_operations=[migrations.DeleteModel(name='SystemsTracking')], database_operations=[]),
    ]
