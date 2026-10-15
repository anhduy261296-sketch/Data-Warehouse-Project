"""Xoa dong trung lap trong dbo.OMS_ORDERS (do loi xoa cua so cu cua pipeline OMS - da sua trong services/pipeline/oms_orders.py).

    python manage.py dedupe_oms_orders            # chi dem (khong xoa)
    python manage.py dedupe_oms_orders --apply    # xoa ban thua, giu dong ghi som nhat (_row_id nho nhat)

Trung = giong het moi cot du lieu (bo qua _row_id, _scraped_at va cot tinh san).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection, transaction

TABLE = 'dbo.OMS_ORDERS'
_TECH_COLUMNS = ('_row_id', '_scraped_at')


class Command(BaseCommand):
    help = 'Xoa dong trung lap trong OMS_ORDERS (mac dinh chi dem; --apply de xoa).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Xoa that (mac dinh chi dem)')

    def handle(self, *args, **opts):
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sys.columns WHERE object_id = OBJECT_ID(%s) AND is_computed = 0 ORDER BY column_id", [TABLE])
            columns = [r[0] for r in cursor.fetchall() if r[0] not in _TECH_COLUMNS]
            # dau van tay cua dong: moi cot (NULL danh dau rieng de khong lan voi chuoi rong)
            fingerprint = ' + '.join(f"ISNULL(CAST([{c}] AS NVARCHAR(MAX)), N'<NULL>') + N'|'" for c in columns)
            dup_cte = f"""
                ;WITH d AS (
                    SELECT _row_id, ROW_NUMBER() OVER (PARTITION BY HASHBYTES('SHA2_256', {fingerprint}) ORDER BY _row_id) AS rn
                    FROM {TABLE}
                )"""
            cursor.execute(f'{dup_cte} SELECT COUNT(*) FROM d WHERE rn > 1')
            extra = cursor.fetchone()[0]
            cursor.execute(f'SELECT COUNT(*) FROM {TABLE}')
            total = cursor.fetchone()[0]
            self.stdout.write(f'{TABLE}: {total} dong, {extra} dong thua (trung lap)')
            if not opts['apply'] or not extra:
                if extra:
                    self.stdout.write('Chua xoa. Chay lai voi --apply de xoa.')
                return
            with transaction.atomic():
                cursor.execute(f'{dup_cte} DELETE t FROM {TABLE} t JOIN d ON d._row_id = t._row_id WHERE d.rn > 1')
                deleted = cursor.rowcount
                cursor.execute(f'{dup_cte} SELECT COUNT(*) FROM d WHERE rn > 1')
                left = cursor.fetchone()[0]
                if deleted != extra or left:
                    raise RuntimeError(f'Xoa {deleted} dong, ky vong {extra}, con lai {left} -> rollback')
            self.stdout.write(self.style.SUCCESS(f'Da xoa {deleted} dong thua. Con {total - deleted} dong.'))
