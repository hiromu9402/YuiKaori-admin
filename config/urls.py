from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path
from django.views.static import serve

admin.site.site_header = "ゆいかおりデータベース 管理"
admin.site.site_title = "ゆいかおりDB"
admin.site.index_title = "データ管理"

urlpatterns = [
    # 利用者は本人だけなので、collectstatic した管理画面の CSS/JS も Django から配信する
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT}),
    path("", admin.site.urls),
]
