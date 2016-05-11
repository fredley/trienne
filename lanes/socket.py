import logging

logger = logging.getLogger('django')


def get_allowed_channels(request, channels):
  return set(channels).intersection(['subscribe-broadcast'])
