"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# YUIKAORI_URL_PREFIX（例: /example）を指定したときは、そのパスの下で動かす
if os.environ.get("YUIKAORI_URL_PREFIX", "").strip("/"):
    from config.prefix import PrefixMiddleware

    application = PrefixMiddleware(application, os.environ["YUIKAORI_URL_PREFIX"])
