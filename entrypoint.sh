#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py apply_db_migrations

exec "$@"
