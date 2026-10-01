from .models import SystemsTracking

def _iso(value):
    if value is None:
        return None
    return value.isoformat()

def get_report():
    rows = SystemsTracking.objects.all()
    return [{'id': row.id, 'name': row.name, 'status': row.status, 'last_seen': _iso(row.last_seen), 'created_at': _iso(row.created_at), 'updated_at': _iso(row.updated_at)} for row in rows]
