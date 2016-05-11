from datetime import datetime, timedelta
from math import log

from ws4redis.redis_store import RedisMessage
from ws4redis.publisher import RedisPublisher

from .celeryapp import app
from .models import *


@app.task(bind=True)
def reorder_stars(self):
  # Update hotness for all pinned posts
  print "Updating post hotness"
  for post in Post.objects.filter(pinned=True):
    post.update_hotness()
  # Push out updates for all rooms
  for room in Room.objects.all():
    print "Broadcasting hotness for " + room.name
    posts = Post.objects.filter(pinned=True, room=room).order_by('-hotness')[:20]
    message = {
        'type': 'hotness',
        'posts': [
            {
              'hotness': post.hotness,
              'score': post.score,
              'id': post.id
            }
            for post in posts
        ]
    }
    RedisPublisher(facility='room_' + str(room.id), broadcast=True) \
          .publish_message(RedisMessage(json.dumps(message)))
