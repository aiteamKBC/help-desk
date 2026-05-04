from django.contrib import admin
from django.urls import include, path, re_path

from support_portal import views as support_views

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/", include("support_portal.urls")),
    re_path(r"^(?!api/|django-admin/)(?P<path>.*)$", support_views.frontend_entry),
]
