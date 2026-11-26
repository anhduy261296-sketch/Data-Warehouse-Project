from __future__ import annotations

import os

import psycopg2
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connections

from services.pipeline.dms_synced_documents import sync_dms_synced_documents
from tracking.core.cache import invalidate_source


class Command(BaseCommand):
    help = 'Dong bo truc tiep DMS_SO_ALL tu PostgreSQL sang SQL Server, khong can chay Airflow DAG.'

    def add_arguments(self, parser):
        parser.add_argument('--start-at', required=True, help='Dau cua so nap, ISO date/datetime, gio local.')
        parser.add_argument('--end-at', required=True, help='Cuoi cua so nap (exclusive), ISO date/datetime, gio local.')
        parser.add_argument('--target-profile', choices=('app', 'srv'), default='app', help='SQL Server credentials profile.')
        parser.add_argument('--target-host')
        parser.add_argument('--target-port')
        parser.add_argument('--target-database')

    def handle(self, *args, **options):
        source_keys = (
            'DMS_POSTGRES_HOST',
            'DMS_POSTGRES_PORT',
            'DMS_POSTGRES_DATABASE',
            'DMS_POSTGRES_USER',
            'DMS_POSTGRES_PASSWORD',
        )
        missing = [key for key in source_keys if not os.getenv(key)]
        if missing:
            raise CommandError(f'Missing DMS source connection settings: {", ".join(missing)}')

        target = connections['default']
        if options['target_host']:
            target.settings_dict['HOST'] = options['target_host']
        if options['target_port']:
            target.settings_dict['PORT'] = options['target_port']
        if options['target_database']:
            target.settings_dict['NAME'] = options['target_database']
        if options['target_profile'] == 'srv':
            target_user = os.getenv('SRV_SQLSERVER_USER')
            target_password = os.getenv('SRV_SQLSERVER_PASSWORD')
            if not target_user or not target_password:
                raise CommandError('Set SRV_SQLSERVER_USER and SRV_SQLSERVER_PASSWORD in .env for the srv profile.')
            target.settings_dict['USER'] = target_user
            target.settings_dict['PASSWORD'] = target_password

        source = None
        try:
            source = psycopg2.connect(
                host=os.environ['DMS_POSTGRES_HOST'],
                port=os.environ['DMS_POSTGRES_PORT'],
                dbname=os.environ['DMS_POSTGRES_DATABASE'],
                user=os.environ['DMS_POSTGRES_USER'],
                password=os.environ['DMS_POSTGRES_PASSWORD'],
                application_name='sync_dms_so_all_manual',
            )
            target.ensure_connection()
            row_count = sync_dms_synced_documents(
                source,
                target,
                start_at=options['start_at'],
                end_at=options['end_at'],
            )
            invalidate_source('dms_so_all')
        except (DatabaseError, psycopg2.Error, ValueError, RuntimeError) as exc:
            raise CommandError(f'DMS sync failed ({type(exc).__name__}); check the configured DB access and migrations.') from exc
        finally:
            if source is not None:
                source.close()
            target.close()

        self.stdout.write(self.style.SUCCESS(f'Synced {row_count} DMS rows for {options["start_at"]} to {options["end_at"]}.'))
