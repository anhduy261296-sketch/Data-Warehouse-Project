import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db_migrations"

CREATE_TRACKING_TABLE_SQL = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'SchemaMigrations')
BEGIN
    CREATE TABLE dbo.SchemaMigrations (
        filename NVARCHAR(255) NOT NULL PRIMARY KEY,
        applied_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
"""


class Command(BaseCommand):
    help = "Chay cac file .sql chua ap dung trong db_migrations/, theo thu tu ten file (dbo.SchemaMigrations luu vet da chay)."

    def add_arguments(self, parser):
        parser.add_argument('--target-host', help='SQL Server host override; uses SRV_SQLSERVER credentials.')
        parser.add_argument('--target-port', help='SQL Server port override.')
        parser.add_argument('--target-database', help='SQL Server database override.')

    def handle(self, *args, **options):
        target_overrides = (options['target_host'], options['target_port'], options['target_database'])
        if any(target_overrides):
            user = os.getenv('SRV_SQLSERVER_USER')
            password = os.getenv('SRV_SQLSERVER_PASSWORD')
            if not user or not password:
                raise CommandError('Set SRV_SQLSERVER_USER and SRV_SQLSERVER_PASSWORD in .env before using a target override.')
            connection.close()
            connection.settings_dict['USER'] = user
            connection.settings_dict['PASSWORD'] = password
            for setting, value in zip(('HOST', 'PORT', 'NAME'), target_overrides):
                if value:
                    connection.settings_dict[setting] = value

        with connection.cursor() as cursor:
            cursor.execute(CREATE_TRACKING_TABLE_SQL)
            cursor.execute("SELECT filename FROM dbo.SchemaMigrations")
            applied = {row[0] for row in cursor.fetchall()}

        if not MIGRATIONS_DIR.exists():
            self.stdout.write("Khong thay thu muc db_migrations/.")
            return

        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        pending = [f for f in files if f.name not in applied]

        if not pending:
            self.stdout.write(self.style.SUCCESS(f"Da ap dung du {len(files)} migration, khong co gi moi."))
            return

        for f in pending:
            sql = f.read_text(encoding="utf-8")
            self.stdout.write(f"Ap dung {f.name} ...")
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql)
                    cursor.execute(
                        "INSERT INTO dbo.SchemaMigrations (filename) VALUES (%s)",
                        [f.name],
                    )
            self.stdout.write(self.style.SUCCESS(f"  OK: {f.name}"))

        self.stdout.write(self.style.SUCCESS(f"Xong - da ap dung {len(pending)} migration moi."))
