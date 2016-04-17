import gevent.monkey
from ws4redis.uwsgi_runserver import uWSGIWebsocketServer

gevent.monkey.patch_thread()
application = uWSGIWebsocketServer()
