import re
import collections

from django.db import models
from django.conf import settings


class Organisation(models.Model):
  name = models.CharField(max_length=200)
  domain = models.CharField(max_length=200)
  admins = models.ManyToManyField(settings.AUTH_USER_MODEL)

  def __unicode__(self):
    return self.name


class Room(models.Model):
  name = models.CharField(max_length=100)
  topic = models.CharField(max_length=200)
  organisation = models.ForeignKey(Organisation)
  creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='creator')
  created = models.DateTimeField(auto_now_add=True)
  owners = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='owners')

  def get_history(self):
    posts = Post.objects.filter(room=self).order_by('-created')[:100]
    return posts[::-1]

  history = property(get_history)

  def get_pinned(self):
    posts = Post.objects.filter(room=self, pinned=True).order_by('-pinned_at')[:20]
    return posts[::-1]

  pinned = property(get_pinned)

  def __unicode__(self):
    return self.name


class Post(models.Model):
  room = models.ForeignKey(Room)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  created = models.DateTimeField(auto_now_add=True)
  pinned = models.BooleanField(default=False)
  pinned_at = models.DateTimeField(null=True, default=None)
  deleted = models.BooleanField(default=False)

  def get_content(self):
    if self.deleted:
      return "(deleted)"
    return PostContent.objects.filter(post=self).order_by('-created')[0].content

  def get_markdown(self):
    if self.deleted:
      return "(deleted)"
    return PostContent.objects.filter(post=self).order_by('-created')[0].markdown

  markdown = property(get_markdown)
  content = property(get_content)

  def __unicode__(self):
    return self.author.username + ' - ' + self.content


def paragraph(match_obj):
  line = match_obj.group(1)
  trimmed = line.strip()
  if re.search(r'^<\/?(ul|ol|li|h|p|bl)', trimmed):
    return "\n" + line + "\n"
  return "\n<p>{}</p>\n".format(trimmed);


class PostContent(models.Model):
  post = models.ForeignKey(Post)
  author = models.ForeignKey(settings.AUTH_USER_MODEL)
  content = models.CharField(max_length=512)
  created = models.DateTimeField(auto_now_add=True)

  def get_markdown(self):
    rules = collections.OrderedDict()
    rules[r'\[([^\[]+)\]\(([^\)]+)\)'] = r'<a href="\2">\1</a>' # links
    rules[r'(\*\*|__)(.*?)\1'] = r'<strong>\2</strong>' # bold
    rules[r'(\*|_)(.*?)\1'] = r'<em>\2</em>' # emphasis
    rules[r'\-\-\-(.*?)\-\-\-'] = r'<del>\1</del>' # del
    rules[r'\:\"(.*?)\"\:'] = r'<q>\1</q>' # quote
    rules[r'`(.*?)`'] = r'<code>\1</code>' # inline code
    rules[r'\n([^\n]+)\n'] = paragraph # add paragraphs
    text = self.content
    for regex, replacement in rules.items():
      text = re.sub(regex, replacement, text)
    return text.strip()

  markdown = property(get_markdown)


  def __unicode__(self):
    return self.content
