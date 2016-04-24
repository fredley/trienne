#-*- coding: utf-8 -*-
from redis import ConnectionPool, StrictRedis
from ws4redis import settings
from ws4redis.redis_store import RedisStore

import logging

redis_connection_pool = ConnectionPool(**settings.WS4REDIS_CONNECTION)

logger = logging.getLogger("django")


class RedisPublisher(RedisStore):
    def __init__(self, **kwargs):
        """
        Initialize the channels for publishing messages through the message queue.
        """
        connection = StrictRedis(connection_pool=redis_connection_pool)
        super(RedisPublisher, self).__init__(connection)
        for key in self._get_message_channels(**kwargs):
            self._publishers.add(key)

    def fetch_message(self, request, facility, audience='any'):
        """
        Fetch the first message available for the given ``facility`` and ``audience``, if it has
        been persisted in the Redis datastore.
        The current HTTP ``request`` is used to determine to whom the message belongs.
        A unique string is used to identify the bucket's ``facility``.
        Determines the ``audience`` to check for the message. Must be one of ``broadcast``,
        ``group``, ``user``, ``session`` or ``any``. The default is ``any``, which means to check
        for all possible audiences.
        """
        pass
