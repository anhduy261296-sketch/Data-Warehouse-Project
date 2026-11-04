from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from tracking import access


class Command(BaseCommand):
    help = 'Dong bo danh muc quyen trong tracking/access.py vao auth_permission, tao san vai tro. Khong ghi de vai tro da chinh sua.'

    @transaction.atomic
    def handle(self, *args, **options):
        content_type, _ = ContentType.objects.get_or_create(app_label=access.APP_LABEL, model=access.CONTENT_TYPE_MODEL)
        first_run = not Permission.objects.filter(content_type=content_type).exists()
        perms = {}
        new_codenames = set()
        for perm in access.ALL_PERMS:
            perms[perm.codename], created = Permission.objects.update_or_create(content_type=content_type, codename=perm.codename, defaults={'name': perm.label})
            if created:
                new_codenames.add(perm.codename)
        stale = Permission.objects.filter(content_type=content_type).exclude(codename__in=access.ALL_CODENAMES)
        stale.delete()

        for name, codenames in access.ROLE_SEEDS.items():
            if first_run:
                group, created = Group.objects.get_or_create(name=name)
                if created:
                    group.permissions.set(perms[c] for c in codenames)
            else:
                # Quyền mới thêm vào danh mục: cấp một lần cho nhóm mặc định còn tồn tại. Nhóm đã bị đổi tên hoặc xóa thì không tạo lại.
                group = Group.objects.filter(name=name).first()
                if group:
                    group.permissions.add(*(perms[c] for c in codenames if c in new_codenames))

        if first_run:
            self._grant_existing_users(perms)
            for group in Group.objects.filter(name__in=access.ROLE_DEPARTMENTS):
                access.set_department(group.id, True)
        self._assign_departments()
        unmapped = access.unmapped_routes()
        if unmapped:
            self.stdout.write(self.style.WARNING(f'Route chua khai bao quyen (se bi chan): {", ".join(unmapped)}'))
        self.stdout.write(self.style.SUCCESS(f'Da dong bo {len(perms)} quyen, {len(access.ROLE_SEEDS)} vai tro mac dinh.'))

    def _assign_departments(self):
        """Mẫu và lô chưa có phòng ban: gán theo phòng của người tạo nếu người đó thuộc đúng một phòng."""
        departments = access.department_ids()
        users = {u.get_username(): u for u in get_user_model().objects.prefetch_related('groups')}
        with connection.cursor() as cursor:
            cursor.execute('SELECT Id, CreatedBy FROM dbo.ZnsTemplates WHERE DepartmentId IS NULL')
            pending = cursor.fetchall()
            for template_id, created_by in pending:
                creator = users.get(created_by)
                found = departments & {g.id for g in creator.groups.all()} if creator else set()
                if len(found) == 1:
                    cursor.execute('UPDATE dbo.ZnsTemplates SET DepartmentId = %s WHERE Id = %s', [found.pop(), template_id])
            cursor.execute(
                """
                UPDATE b SET DepartmentId = t.DepartmentId
                FROM dbo.ZnsSendBatches b JOIN dbo.ZnsTemplates t ON t.Id = b.TemplateId
                WHERE b.DepartmentId IS NULL AND t.DepartmentId IS NOT NULL
                """
            )
            cursor.execute(
                """
                UPDATE a SET DepartmentId = b.DepartmentId
                FROM dbo.AppAuditLog a JOIN dbo.ZnsSendBatches b ON a.TargetType = 'batch' AND TRY_CAST(a.TargetId AS BIGINT) = b.Id
                WHERE a.DepartmentId IS NULL AND b.DepartmentId IS NOT NULL
                """
            )
            # Mã mẫu có thể trùng giữa 2 chủ hàng: chỉ gán khi mọi mẫu cùng mã thuộc một phòng.
            cursor.execute(
                """
                UPDATE a SET DepartmentId = t.DepartmentId
                FROM dbo.AppAuditLog a JOIN dbo.ZnsTemplates t ON a.TargetType = 'template' AND a.TargetId = t.ZnsCode
                WHERE a.DepartmentId IS NULL AND t.DepartmentId IS NOT NULL
                      AND NOT EXISTS (SELECT 1 FROM dbo.ZnsTemplates o WHERE o.ZnsCode = t.ZnsCode AND (o.DepartmentId IS NULL OR o.DepartmentId <> t.DepartmentId))
                """
            )
            cursor.execute('SELECT COUNT(*) FROM dbo.ZnsTemplates WHERE DepartmentId IS NULL AND DeletedAt IS NULL')
            left = cursor.fetchone()[0]
        if left:
            self.stdout.write(self.style.WARNING(f'{left} mau tin chua co phong ban: chi nguoi xem duoc moi phong ban moi thay.'))

    def _grant_existing_users(self, perms):
        """Lần đầu bật phân quyền: giữ nguyên quyền xem báo cáo và quyền quản lý mẫu cũ. Quyền gửi tin phải được gán lại."""
        viewer = Group.objects.get(name=access.ROLE_VIEWER)
        template_admin = Group.objects.get(name=access.ROLE_TEMPLATE_ADMIN)
        owners = Group.objects.filter(name__in=access.ROLE_OWNER.values())
        for user in get_user_model().objects.filter(is_active=True, is_superuser=False, deleted_at__isnull=True):
            user.groups.add(viewer)
            if user.is_staff:
                user.groups.add(template_admin, *owners)
                user.user_permissions.add(perms['report_ecom_refresh'])
