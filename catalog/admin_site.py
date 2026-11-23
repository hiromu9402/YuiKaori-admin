"""管理サイト。トップページに「公開ファイルの書き出し」と「データ更新の候補」を付ける。"""
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path

from .services import export_site
from .updates import load_report
from .validate import validate


class YuikaoriAdminSite(admin.AdminSite):
    site_header = "ゆいかおりデータベース 管理"
    site_title = "ゆいかおりDB"
    index_title = "データ管理"
    index_template = "admin/yuikaori_index.html"

    def index(self, request, extra_context=None):
        # manage.py check_updates（毎月 1 日に cron で実行）が集めた候補
        return super().index(request, {**(extra_context or {}), "update_report": load_report()})

    def get_urls(self):
        return [path("export/", self.admin_view(self.export_view), name="export")] + super().get_urls()

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
        context.update(result=result)
        return TemplateResponse(request, "admin/catalog/export.html", context)
