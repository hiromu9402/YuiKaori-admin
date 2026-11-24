"""管理サイト。トップページに「公開ファイルの書き出し」「公開前のプレビュー」「データ更新の候補」を付ける。"""
from django.conf import settings
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, re_path, reverse

from . import preview

from .export_diff import changes
from .services import export_site
from .updates import load_report
from .validate import validate


def site_changes():
    """公開中の JSON と DB の違い。読めないときは None（画面には出さない）。"""
    try:
        return changes(settings.SITE_DIR)
    except OSError:
        return None


class YuikaoriAdminSite(admin.AdminSite):
    site_header = "ゆいかおりデータベース 管理"
    site_title = "ゆいかおりDB"
    index_title = "データ管理"
    index_template = "admin/yuikaori_index.html"

    def each_context(self, request):
        return {**super().each_context(request), "extra_script_url": settings.EXTRA_SCRIPT_URL}

    def index(self, request, extra_context=None):
        # manage.py check_updates（毎月 1 日に cron で実行）が集めた候補
        context = {"update_report": load_report(), "site_changes": site_changes(), "dev_preview": preview.dev_preview()}
        return super().index(request, {**(extra_context or {}), **context})

    def get_urls(self):
        return [
            path("export/", self.admin_view(self.export_view), name="export"),
            re_path(r"^preview/(?P<path>.*)$", self.admin_view(self.preview_view), name="preview"),
        ] + super().get_urls()

    def preview_view(self, request, path):
        return preview.serve(request, path, reverse("admin:index"), reverse("admin:preview", args=[""]))

    def export_view(self, request):
        context = {**self.each_context(request), "title": "公開ファイルの書き出し"}
        if request.method == "POST":
            result = export_site()
            if result["errors"]:
                messages.error(request, f"エラーが {len(result['errors'])} 件あるので書き出しませんでした。")
            elif result["changed"]:
                messages.success(request, f"書き出しました: {', '.join(result['changed'])}")
            else:
                messages.info(request, "変更はありませんでした。")
            request.session["export_result"] = result
            return redirect("admin:export")
        result = request.session.pop("export_result", None)
        if result is None:
            errors, warnings = validate()
            result = {"errors": errors, "warnings": warnings, "changed": None, "diffstat": ""}
        context.update(result=result, site_changes=site_changes(), dev_preview=preview.dev_preview())
        return TemplateResponse(request, "admin/catalog/export.html", context)
