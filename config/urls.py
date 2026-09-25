from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path
from django.views.static import serve

urlpatterns = [
    # 利用者は本人だけなので、collectstatic した管理画面の CSS/JS も Django から配信する
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT}),
    path("", admin.site.urls),
]
