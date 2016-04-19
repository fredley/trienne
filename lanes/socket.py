import logging

logger = logging.getLogger('django')


def get_allowed_channels(request, channels):
  logger.debug(channels)
  return set(channels).intersection(['subscribe-broadcast'])
