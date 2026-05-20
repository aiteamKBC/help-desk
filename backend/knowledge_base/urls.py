from django.urls import path

from . import views

urlpatterns = [
    path("articles", views.articles_collection, name="knowledge-base-articles"),
    path("articles/<path:filename>", views.article_detail, name="knowledge-base-article-detail"),
    path("assets/<path:asset_path>", views.article_asset, name="knowledge-base-article-asset"),
]
