from django.contrib.admin.apps import AdminConfig


class YuikaoriAdminConfig(AdminConfig):
    """標準の管理サイトの代わりに、書き出し機能付きの YuikaoriAdminSite を使う。"""
    default_site = "catalog.admin_site.YuikaoriAdminSite"
