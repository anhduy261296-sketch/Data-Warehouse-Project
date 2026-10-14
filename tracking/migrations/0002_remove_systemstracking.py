from django.db import migrations


class Migration(migrations.Migration):
    """Bo model SystemsTracking (trang goc "/" khong dung nua).

    Chi xoa khoi state cua Django, KHONG drop bang dbo.AllSystemsTracking tren DB (tranh mat du lieu).
    Muon xoa han: DROP TABLE dbo.AllSystemsTracking (thu cong).
    """

    dependencies = [('tracking', '0001_initial')]
    operations = [
        migrations.SeparateDatabaseAndState(state_operations=[migrations.DeleteModel(name='SystemsTracking')], database_operations=[]),
    ]
