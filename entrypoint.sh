#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py apply_db_migrations
python manage.py sync_access
python manage.py clearsessions

exec "$@"
