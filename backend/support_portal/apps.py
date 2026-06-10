from django.apps import AppConfig
from django.db.models.signals import post_migrate


def ensure_support_access_group(**kwargs):
    from django.contrib.auth.models import Group

    from .roles import ADMIN_ACCESS_GROUP_NAME, OPERATIONS_ACCESS_GROUP_NAME, SUPPORT_ACCESS_GROUP_NAME

    Group.objects.get_or_create(name=SUPPORT_ACCESS_GROUP_NAME)
    Group.objects.get_or_create(name=ADMIN_ACCESS_GROUP_NAME)
    Group.objects.get_or_create(name=OPERATIONS_ACCESS_GROUP_NAME)


class SupportPortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "support_portal"
    verbose_name = "Support Portal"

    def ready(self):
        post_migrate.connect(
            ensure_support_access_group,
            sender=self,
            dispatch_uid="support_portal.ensure_support_access_group",
        )
