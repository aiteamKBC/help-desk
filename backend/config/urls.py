from django.contrib import admin
from django.urls import include, path, re_path

from support_portal import views as support_views

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("coverage/tutor-response", support_views.coverage_tutor_response, name="coverage-tutor-response-public"),
    path("coverage/tutor-response/result", support_views.coverage_tutor_response_result, name="coverage-tutor-response-result-public"),
    path("api/knowledge-base/", include("knowledge_base.urls")),
    path("api/", include("support_portal.urls")),
    re_path(r"^(?!api/|django-admin/)(?P<path>.*)$", support_views.frontend_entry),
]
