import requests

from ws4redis.redis_store import RedisMessage
from ws4redis.publisher import RedisPublisher

from .celeryapp import app
from .models import *
from .emails import NotificationEmail


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


@app.task(bind=True)
def send_notifications(self):
  # Get all notifications
  print("Sending notification emails")
  for n in Notification.objects.all():
    print("Sending notification to " + n.user.email)
    NotificationEmail(n.post).send(n.user.email)
    n.delete()


@app.task(bind=True)
def ping_bot(self, post, user):
  print "Pinging bot " + user.username
  data = {
      'action': 'message',
      'key': user.bot.notify_key,
      'organisation': {
          'slug': post.organisation.slug,
          'name': post.organisation.name
      },
      'room': {
          'id': post.room.id,
          'name': post.room.name
      },
      'message': {
          'id': post.id,
          'timestamp': post.created,
          'content': post.get_content()
      },
  }
  requests.post(user.bot.notify_url, data=data)
