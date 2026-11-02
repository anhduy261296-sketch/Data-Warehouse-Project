from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from tracking import access


class Command(BaseCommand):
    help = 'Dong bo danh muc quyen trong tracking/access.py vao auth_permission, tao san vai tro. Khong ghi de vai tro da chinh sua.'

    @transaction.atomic
    def handle(self, *args, **options):
        content_type, _ = ContentType.objects.get_or_create(app_label=access.APP_LABEL, model=access.CONTENT_TYPE_MODEL)
        perms = {}
        for perm in access.ALL_PERMS:
            perms[perm.codename], _ = Permission.objects.update_or_create(content_type=content_type, codename=perm.codename, defaults={'name': perm.label})
        stale = Permission.objects.filter(content_type=content_type).exclude(codename__in=access.ALL_CODENAMES)
        stale.delete()

        first_run = not Group.objects.filter(name=access.ROLE_ADMIN).exists()
        for name, codenames in access.ROLE_SEEDS.items():
            group, created = Group.objects.get_or_create(name=name)
            if created:
                group.permissions.set(perms[c] for c in codenames)

        if first_run:
            self._grant_existing_users(perms)
        unmapped = access.unmapped_routes()
        if unmapped:
            self.stdout.write(self.style.WARNING(f'Route chua khai bao quyen (se bi chan): {", ".join(unmapped)}'))
        self.stdout.write(self.style.SUCCESS(f'Da dong bo {len(perms)} quyen, {len(access.ROLE_SEEDS)} vai tro mac dinh.'))

    def _grant_existing_users(self, perms):
        """Lần đầu bật phân quyền: giữ nguyên quyền xem báo cáo và quyền quản lý mẫu cũ. Quyền gửi tin phải được gán lại."""
        viewer = Group.objects.get(name=access.ROLE_VIEWER)
        template_admin = Group.objects.get(name=access.ROLE_TEMPLATE_ADMIN)
        owners = Group.objects.filter(name__in=access.ROLE_OWNER.values())
        for user in get_user_model().objects.filter(is_active=True, is_superuser=False):
            user.groups.add(viewer)
            if user.is_staff:
                user.groups.add(template_admin, *owners)
                user.user_permissions.add(perms['report_ecom_refresh'])
