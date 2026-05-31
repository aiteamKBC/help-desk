from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth.models import Group

from .roles import ADMIN_ACCESS_GROUP_NAME, SUPPORT_ACCESS_GROUP_NAME

User = get_user_model()


def user_has_group_access(user, group_name: str) -> bool:
    return bool(getattr(user, "pk", None)) and user.groups.filter(name=group_name).exists()


def user_has_support_access(user) -> bool:
    return user_has_group_access(user, SUPPORT_ACCESS_GROUP_NAME)


def user_has_admin_access(user) -> bool:
    return user_has_group_access(user, ADMIN_ACCESS_GROUP_NAME)


def sync_access_group_membership(user, group_name: str, enabled: bool) -> None:
    if not getattr(user, "pk", None):
        return

    if enabled:
        access_group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(access_group)
        return

    access_group = Group.objects.filter(name=group_name).first()
    if access_group:
        user.groups.remove(access_group)


def sync_support_access_group_membership(user, enabled: bool) -> None:
    sync_access_group_membership(user, SUPPORT_ACCESS_GROUP_NAME, enabled)


def sync_admin_access_group_membership(user, enabled: bool) -> None:
    sync_access_group_membership(user, ADMIN_ACCESS_GROUP_NAME, enabled)


class SupportAccessFormMixin:
    support_access = forms.BooleanField(
        required=False,
        label="Support access",
        help_text="Allow this account to sign in to the Kent support admin experience.",
    )
    admin_access = forms.BooleanField(
        required=False,
        label="Admin access",
        help_text="Allow this support account to use the admin dashboard login.",
    )

    def _initialize_support_access_field(self) -> None:
        instance = getattr(self, "instance", None)
        self.fields["support_access"].initial = user_has_support_access(instance) if instance is not None else False
        self.fields["admin_access"].initial = user_has_admin_access(instance) if instance is not None else False


class SupportAccessUserChangeForm(SupportAccessFormMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialize_support_access_field()


class SupportAccessUserCreationForm(SupportAccessFormMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialize_support_access_field()


class SupportAccessUserAdmin(DjangoUserAdmin):
    form = SupportAccessUserChangeForm
    add_form = SupportAccessUserCreationForm
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Support access",
            {
                "fields": ("support_access", "admin_access"),
                "description": "Grant both support access and admin access to allow this user to sign in to the support dashboard.",
            },
        ),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "Support access",
            {
                "classes": ("wide",),
                "fields": ("support_access", "admin_access"),
            },
        ),
    )
    list_display = DjangoUserAdmin.list_display + ("support_access_enabled", "admin_access_enabled")

    @admin.display(boolean=True, description="Support")
    def support_access_enabled(self, obj):
        return user_has_support_access(obj)

    @admin.display(boolean=True, description="Admin")
    def admin_access_enabled(self, obj):
        return user_has_admin_access(obj)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        sync_support_access_group_membership(form.instance, bool(form.cleaned_data.get("support_access")))
        sync_admin_access_group_membership(form.instance, bool(form.cleaned_data.get("admin_access")))


admin.site.unregister(User)
admin.site.register(User, SupportAccessUserAdmin)
