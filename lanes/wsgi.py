import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lanes.settings')

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from ws4redis.uwsgi_runserver import uWSGIWebsocketServer
from whitenoise.django import DjangoWhiteNoise


_django_app = DjangoWhiteNoise(get_wsgi_application())
_websocket_app = uWSGIWebsocketServer()


def application(environ, start_response):
    if environ.get('PATH_INFO').startswith(settings.WEBSOCKET_URL):
        return _websocket_app(environ, start_response)
    return _django_app(environ, start_response)
