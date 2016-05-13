import json
# -*- coding: utf-8 -*-
import re
import collections
import logging

from cgi import escape
from urlparse import urlparse

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin, AccessMixin
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.views.generic import DetailView
from django.views.generic.base import TemplateView, View
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.decorators.csrf import csrf_exempt

from django_gravatar.helpers import get_gravatar_url
from ratelimit.mixins import RatelimitMixin
from ws4redis.redis_store import RedisMessage
from ws4redis.publisher import RedisPublisher

from .models import *
from .forms import *
from .utils import is_email_public
from .emails import *

logger = logging.getLogger('django')
User = get_user_model()

url_dot_test = re.compile(ur'.+\..+')
lf_youtube = re.compile(ur'(.*)v=([A-Za-z0-9]*)')
reply_test = re.compile(ur'^(:[0-9]+ )')
username_test = re.compile("^([a-z][0-9]+)+$")


def valid_link(text, is_onebox=False):
  if len(text.split(" ")) != 1 or '"' in text or "'" in text:
    return False
  url = urlparse(text)
  if url.scheme in ['http', 'https'] and len(re.findall(url_dot_test, url.netloc)) > 0:
    # Is a valid link, now find out what kind
    if not is_onebox:
      return True
    if url.path.lower().split(".")[-1] in ["jpg", "jpeg", "png", "gif"]:
      return onebox('<a href="{0}" rel="nofollow" target="_blank"><img src="{0}" alt="" onload="scrolldown()"></a>'.format(text))
    elif url.netloc in ["www.youtube.com", "youtube.com", "youtu.be"]:
      slug = url.path[1:] if url.netloc == "youtu.be" else re.search(lf_youtube, url.query).group(2)
      return onebox('<iframe width="400" height="300" src="https://www.youtube.com/embed/{}" frameborder="0"></iframe>'.format(slug))
    else:
      return False
  else:
    return False


def link_formatter(match_obj):
  link = match_obj.group(2).strip()
  if valid_link(link):
    return r'[{}]({})'.format(match_obj.group(1), match_obj.group(2))
  return r'<a href="{}" rel="nofollow">{}</a>'.format(link, match_obj.group(1))


md_rules = collections.OrderedDict()
md_rules[re.compile(r'\[([^\[]+)\]\(([^\)]+)\)')] = link_formatter    # links
md_rules[re.compile(r'(\*\*|__)(.*?)\1')] = r'<strong>\2</strong>'    # bold
md_rules[re.compile(r'(\*|_)(.*?)\1')] = r'<em>\2</em>'               # emphasis
md_rules[re.compile(r'\-\-\-(.*?)\-\-\-')] = r'<del>\1</del>'         # del
md_rules[re.compile(r'^&gt; (.*)')] = r'<blockquote>\1</blockquote>'  # quote
md_rules[re.compile(r'`(.*?)`')] = r'<code>\1</code>'                 # inline code


def onebox(text):
  return '<div class="ob">' + text + '</div>'


def process_text(text):
  # Check that message is not blank
  if text.strip() == "":
    raise
  # strip reply if there is one
  reply = re.search(reply_test, text)
  reply_prefix = ""
  notified = set()
  if reply is not None:
    reply_prefix = reply.group(0)
    text = text[len(reply_prefix):]
    try:
      notified.add(Post.objects.get(id=int(reply_prefix.strip(': '))).author)
    except:
      pass
  # Check for anyone else that's pinged
  words = text.split(' ')
  for word in words:
    if len(word) > 1 and word[0] == '@':
      try:
        notified.add(User.objects.get(username=word[1:]))
      except:
        pass
  # Check for entire block indented by 4 spaces
  is_code = True
  code = ""
  for line in text.split("\n"):
    if line[0:4] == "    ":
      code += line[4:] + "\n"
    else:
      is_code = False
      break
  if is_code:
    result = "<pre>{}</pre>".format(escape(code).replace("'", "&#39;"))
  else:
    # Check for oneboxes
    link = valid_link(text, is_onebox=True)
    if link is not False:
      result = link
    else:
      text = escape(text).replace("'", "&#39;").replace("\n", "<br>")
      # Apply Markdown rules
      for regex, replacement in md_rules.items():
        result = re.sub(regex, replacement, text)
  return {
      'text': reply_prefix + result.strip(),
      'notified': notified
  }


def ratelimit(request, ex):
  return JsonResponse({
      'error': True,
      'message': 'Too Fast!'
  }, status=418)


class LoginOrMaybeBotMixin(AccessMixin):
  allow_bots = False

  def dispatch(self, request, *args, **kwargs):
    if self.allow_bots and 'bot_token' in request.POST:
      try:
        token = BotToken.objects.get(token=request.POST.get('bot_token'))
        request.user = User.objects.get(bot=token.bot)
      except:
        raise PermissionDenied
    elif not request.user.is_authenticated():
      return self.handle_no_permission()
    return super(LoginOrMaybeBotMixin, self).dispatch(request, *args, **kwargs)


class AjaxResponseMixin(object):
  def form_invalid(self, form):
    response = super(AjaxResponseMixin, self).form_invalid(form)
    if self.request.is_ajax():
      return JsonResponse(form.errors, status=400)
    else:
      return response

  def form_valid(self, form):
    response = super(AjaxResponseMixin, self).form_valid(form)
    if self.request.is_ajax():
      data = {
          'id': self.object.id,
      }
      return JsonResponse(data)
    else:
      return response


class RoomPostView(LoginOrMaybeBotMixin, RatelimitMixin, View):

  ratelimit_key = 'user'
  ratelimit_rate = '3/3s'
  ratelimit_block = True
  ratelimit_method = 'POST'
  ratelimit_group = 'posts'

  require_admin = False

  @csrf_exempt
  def dispatch(self, *args, **kwargs):
    return super(RoomPostView, self).dispatch(*args, **kwargs)

  def post(self, request, *args, **kwargs):
    self.room = Room.objects.get(id=kwargs['room_id'])
    self.publisher = RedisPublisher(facility='room_' + str(kwargs['room_id']), broadcast=True)
    if request.user.is_bot and request.user.bot.responds_to(self.room):
      return self.generate_response(request)
    if self.room.organisation not in request.user.organisations.all():
      raise PermissionDenied
    if self.room.privacy == Room.PRIVACY_PRIVATE and request.user not in self.room.members.all():
      raise PermissionDenied
    if self.require_admin and not (request.user.is_admin(self.room.organisation) or
      request.user not in self.room.owners.all()):
      raise PermissionDenied
    return self.generate_response(request)


class RoomView(LoginRequiredMixin, TemplateView):
  template_name = 'room.html'

  def get_context_data(self, **kwargs):
    context = super(RoomView, self).get_context_data(**kwargs)
    room = Room.objects.get(id=kwargs['room_id'])
    if not self.request.user.is_member(room.organisation):
      logger.debug("Not a member")
      raise PermissionDenied
    if not self.request.user.can_view(room):
      logger.debug("Can't view")
      raise PermissionDenied
    elif self.request.user not in room.members.all():
      logger.debug("Added " + str(self.request.user) + " to " + str(room))
      room.members.add(self.request.user)
    pinned = []
    for post in room.pinned:
      vote = 0
      try:
        vote = Vote.objects.get(post=post, user=self.request.user).score
      except:
        pass
      pinned.append({
          "post": post,
          "vote": vote
      })
    users = room.members.all()
    online = []
    for u in users:
      online.append({
          "username": u.username,
          "email": u.email,
          "id": u.id,
          "status": u.get_status(room.organisation)
      })
    status = OrgMembership.objects.get(user=self.request.user, organisation=room.organisation).status
    if status == OrgMembership.STATUS_OFFLINE:
      # Just joining, so set to Online
      status = OrgMembership.STATUS_ONLINE
    context.update(room=room,
                   rooms=self.request.user.get_rooms(),
                   org=room.organisation,
                   is_admin=self.request.user.is_admin(room.organisation),
                   is_member=True,
                   status=status,
                   can_participate=self.request.user.is_member(room.organisation),
                   is_owner=self.request.user in room.owners.all(),
                   pinned=pinned,
                   prefs=RoomPrefs.objects.get_or_create(room=room, user=self.request.user)[0],
                   users=online)
    return context


class RoomPrefsView(RoomPostView):

  def generate_response(self, request):
    volume = int(request.POST.get('volume'))
    prefs = RoomPrefs.objects.get(room=self.room, user=request.user)
    prefs.volume = volume
    prefs.save()
    return HttpResponse('OK')


class RoomPinView(RoomPostView):

  def generate_response(self, request):
    post = Post.objects.get(id=request.POST.get('id'))
    # Prevent people who've already voted from re-pinning
    if post.pinned or Vote.objects.filter(user=self.request.user, post=post).count() > 0:
      raise PermissionDenied
    post.pinned = True
    post.pinned_at = timezone.now()
    post.save()
    if post.author != self.request.user:
      Vote(user=self.request.user, post=post, score=1).save()
    message = {
        'type': 'pin',
        'score': post.score,
        'id': post.id,
        'author_id': post.author.id
    }
    if 'pincode' in request.POST:
      message['pincode'] = request.POST.get('pincode')
    self.publisher.publish_message(RedisMessage(json.dumps(message)))
    return HttpResponse('OK')


class RoomMessageView(RoomPostView):

  allow_bots = True

  def generate_response(self, request):
    post = Post(room=self.room, author=request.user)
    post.save()
    raw = request.POST.get('message')
    processed = process_text(raw)
    content = PostContent(
        author=request.user,
        post=post,
        raw=raw,
        content=processed['text'])
    content.save()
    message = {
        'type': 'msg',
        'author': {
            'name': request.user.username,
            'id': request.user.id,
            'img': get_gravatar_url(request.user.email, size=32)
        },
        'content': post.content,
        'raw': raw,
        'id': post.id
    }
    self.publisher.publish_message(RedisMessage(json.dumps(message)))
    for user in processed['notified']:
      user.notify(post)
    return HttpResponse('OK')


class RoomMemberView(RoomPostView):

  require_admin = True

  def generate_response(self, request):
    user = User.objects.get(username=request.POST.get('username').strip())
    OrgMembership.objects.get(user=user, organisation=self.room.organisation)
    self.room.members.add(user)
    return HttpResponse(user.id)


class OrgMixin(LoginRequiredMixin):

  require_admin = False

  def dispatch(self, *args, **kwargs):
    self.org = Organisation.objects.get(slug=kwargs.get('slug'))
    if self.require_admin and not self.request.user.is_admin(self.org):
      logger.debug("Not admin")
      raise PermissionDenied
    return super(OrgMixin, self).dispatch(*args, **kwargs)

  def get_context_data(self, **kwargs):
    context = super(OrgMixin, self).get_context_data(**kwargs)
    user = self.request.user
    is_member = self.org in user.organisations.all()
    if is_member:
      status = OrgMembership.objects.get(user=self.request.user, organisation=self.org).status
      if status == OrgMembership.STATUS_OFFLINE:
        # Just joining, so set to online
        status = OrgMembership.STATUS_ONLINE
    else:
      status = OrgMembership.STATUS_OFFLINE
    context.update(org=self.org,
                   rooms=Room.objects.filter(members__in=[user]),
                   is_admin=user.is_admin(self.org),
                   has_applied=OrgApplication.objects.filter(user=user, organisation=self.org).count() > 0,
                   is_member=is_member,
                   status=status,
                   is_follower=self.org in user.subscribed.all())
    return context


class RoomAddView(OrgMixin, CreateView):
  model = Room
  form_class = RoomForm
  template_name = "add_room.html"

  def get_success_url(self):
    return ''

  def get_initial(self):
    return {'owners': "{}".format(self.request.user.id)}

  def form_valid(self, form):
    room = form.save(commit=False)
    room.organisation = self.org
    room.creator = self.request.user
    super(RoomAddView, self).form_valid(form)
    if self.request.user not in room.owners.all():
      room.owners.add(self.request.user)
    room.members = [u for u in room.owners.all()]
    self.object = room
    return HttpResponseRedirect(reverse("room", kwargs={"room_id": room.id}))


class RoomEditView(LoginRequiredMixin, UpdateView):
  template_name = "room_edit.html"
  model = Room
  pk_url_kwarg = 'room_id'
  form_class = RoomForm

  def get_context_data(self, *args, **kwargs):
    if not (self.request.user.is_admin(self.object.organisation) or
        self.request.user in self.object.owners.all()):
      raise PermissionDenied
    return super(RoomEditView, self).get_context_data(*args, **kwargs)

  def get_success_url(self):
    return reverse("room", kwargs={"room_id": self.object.id})


class PostView(LoginRequiredMixin):

  require_owner = True
  require_not_owner = False
  allow_deleted = False

  @csrf_exempt
  def dispatch(self, *args, **kwargs):
    user = self.request.user
    post = Post.objects.get(id=kwargs.get('post_id'))
    self.msg = post
    if not user.is_member(post.room.organisation) or not(user.can_view(post.room)):
      logger.debug("Not a member")
      raise PermissionDenied
    if self.require_owner and not (post.author == user or user.is_admin(post.room.organisation)):
      logger.debug("Not my post")
      raise PermissionDenied
    if self.require_not_owner and post.author == user:
      logger.debug("My post!")
      raise PermissionDenied
    if not self.allow_deleted and post.deleted:
      logger.debug("Deleted post!")
      raise PermissionDenied
    return super(PostView, self).dispatch(*args, **kwargs)


class PostEditView(PostView, View):

  def post(self, request, *args, **kwargs):
    raw = request.POST.get('message')
    try:
        processed, notified = process_text(raw)
    except:
        return HttpResponse('Not OK')
    content = PostContent(
        author=request.user,
        post=self.msg,
        raw=raw,
        content=processed['text'])
    content.save()
    message = {
        'type': 'edit',
        'content': processed,
        'raw': raw,
        'id': self.msg.id
    }
    RedisPublisher(facility='room_' + str(self.msg.room.id), broadcast=True) \
        .publish_mressage(RedisMessage(json.dumps(message)))
    for user in processed['notified']:
      user.notify(self.msg)
    return HttpResponse('OK')


class PostVoteView(PostView, View):

  require_owner = False
  require_not_owner = True

  def post(self, request, *args, **kwargs):
    post = self.msg
    value = int(request.POST.get('value'))
    if value not in [-1, 1]:
      raise PermissionDenied
    if Vote.objects.filter(post=post, user=request.user).count() > 0:
      raise PermissionDenied
    vote = Vote(post=post,
        user=request.user,
        score=value)
    vote.save()
    score = post.score
    post.update_hotness()
    if score < -4:
      #unpin
      post.pinned = False
      post.save()
      message = {
          'type': 'unpin',
          'id': post.id
      }
      RedisPublisher(facility='room_' + str(post.room.id), broadcast=True) \
          .publish_message(RedisMessage(json.dumps(message)))
    else:
      message = {
          'type': 'vote',
          'content': score,
          'id': post.id
      }
      RedisPublisher(facility='room_' + str(post.room.id), broadcast=True) \
          .publish_message(RedisMessage(json.dumps(message)))
    return HttpResponse('OK')


class PostHistoryView(PostView, TemplateView):

  template_name = "post_history.html"
  allow_deleted = True

  def get_context_data(self, **kwargs):
    context = super(PostHistoryView, self).get_context_data(**kwargs)
    logger.debug(self.msg)
    context.update(post=self.msg,
                   history=self.msg.history,
                   org=self.msg.room.organisation,
                   is_admin=self.request.user.is_admin(self.msg.room.organisation),
                   can_participate=self.request.user.is_member(self.msg.room.organisation))
    return context

  def post(self, request, *args, **kwargs):
    if self.msg.deleted:
      raise PermissionDenied
    self.msg.deleted = True
    self.msg.pinned = False
    self.msg.save()
    content = PostContent(
        author=request.user,
        post=self.msg,
        raw="(deleted)",
        content="(deleted)")
    content.save()
    message = {
        'type': 'delete',
        'id': self.msg.id
    }
    RedisPublisher(facility='room_' + str(self.msg.room.id), broadcast=True) \
        .publish_message(RedisMessage(json.dumps(message)))
    return HttpResponseRedirect(reverse('post_history', kwargs={'post_id': self.msg.id}))


class OrgsView(LoginRequiredMixin, TemplateView):
  template_name = 'orgs.html'


class UserJsonView(LoginRequiredMixin, View):
  """ endpoint to supply data for user autocomplete """

  data = 'org'

  def get(self, request, *args, **kwargs):
    logger.debug(request.GET)
    if 'org' not in request.GET or 's' not in request.GET:
      raise PermissionDenied
    org = Organisation.objects.get(slug=request.GET.get('org'))
    memberships = OrgMembership.objects.filter(organisation=org, user__username__icontains=request.GET.get('s'))[:10]
    res = []
    for m in memberships:
      res.append({
          'id': m.user.id,
          'username': m.user.username
      })
    return JsonResponse({'results': res})


class OrgJsonView(LoginRequiredMixin, View):
  """ endpoint to supply data for the orgs page
      /ajax/c/all/      - all orgs
      /ajax/c/mine/     - my orgs
      /ajax/c/watching/ - orgs I'm watching
  """

  data = 'all'

  def get(self, request, *args, **kwargs):
    qs = Organisation.objects
    data = self.data
    page = 1
    if 'page' in kwargs:
      page = int(kwargs.get('page'))
    start = (page - 1) * 20
    end = start + 20
    if data == 'all':
      qs = qs.filter(visibility=Organisation.VISIBILITY_PUBLIC)[start:end]
    elif data == 'mine':
      if not request.user.is_authenticated():
        raise PermissionDenied
      qs = request.user.organisations.all()[start:end]
    elif data == 'followed':
      if not request.user.is_authenticated():
        raise PermissionDenied
      qs = request.user.subscribed.all()[start:end]
    elif data == 'search':
      qs = qs.filter(visibility=Organisation.VISIBILITY_PUBLIC, name__icontains=request.GET.get('s'))
    else:
      raise SuspiciousOperation
    return JsonResponse({'orgs': [{
        'slug': o.slug,
        'name': o.name,
        'privacy': o.privacy
    } for o in qs]})


class OrgInviteView(OrgMixin, AjaxResponseMixin, CreateView):

  model = Invitation
  fields = ['organisation', 'email']

  def get_success_url(self):
    return ''

  def form_valid(self, form):
    if self.org.privacy == Organisation.PRIVACY_ORG and \
        form.instance.email.split('@', 1) != self.org.domain:
      return JsonResponse({'error_message=''ail': 'You can only invite people with ' + self.org.domain + ' addresses'}, status=400)
    users = User.objects.filter(email=form.instance.email)
    if users.count() > 0:
      # Just add user as member
      OrgMembership(user=users[0], organisation=self.org).save()
      return HttpResponse('OK')
    response = super(OrgInviteView, self).form_valid(form)  # Saves form
    link = 'http://' + settings.ALLOWED_HOSTS[0] + reverse('invitation', kwargs={'token': form.instance.token})
    InvitationEmail(org=self.org, link=link).send(form.instance.email)
    return response


class OrgView(OrgMixin, TemplateView):
  template_name = "org.html"

  def get_context_data(self, **kwargs):
    context = super(OrgView, self).get_context_data(**kwargs)
    rooms = Room.objects.filter(organisation=self.org)
    if not self.request.user.is_admin(self.org):
      rooms = Room.objects.filter(organisation=self.org, )
      rs = [r for r in rooms if self.request.user.can_view(r)]
      context.update(rooms=rs)
    else:
      context.update(rooms=rooms)
    return context


class OrgManagementView(OrgMixin, UpdateView):
  template_name = 'manage_org.html'
  model = Organisation
  context_object_name = 'org'
  form_class = OrgEditForm
  require_admin = True

  def get_success_url(self):
    return reverse('org', kwargs={'slug': self.object.slug})

  def form_valid(self, form):
    logger.debug(form.instance.id)
    form = super(OrgManagementView, self).form_valid(form)

    return form

  def get_context_data(self, **kwargs):
    context = super(OrgManagementView, self).get_context_data(**kwargs)
    context.update(applications=OrgApplication.objects.filter(organisation=self.org, rejected=False))
    context.update(bots=User.objects.filter(is_bot=True, bot__organisation=self.org))
    return context


class OrgApprovalView(OrgMixin, View):

  require_admin = True

  def post(self, request, *args, **kwargs):
    user = User.objects.get(id=request.POST.get('id'))
    application = OrgApplication.objects.get(user=user, organisation=self.org)
    if request.POST.get('action') == 'approve':
      OrgMembership(user=user, organisation=self.org).save()
      application.delete()
    elif request.POST.get('action') == 'deny':
      application.rejected = True
      application.save()
    else:
      raise SuspiciousOperation
    return HttpResponse('OK')


class OrgCreateView(LoginRequiredMixin, CreateView):
  model = Organisation
  template_name = 'create_org.html'
  form_class = OrgForm

  def get_domain(self):
    return self.request.user.email.split('@')[1]

  def get_initial(self):
    return {'admins': "{}".format(self.request.user.id), 'domain': self.get_domain()}

  def get_context_data(self, *args, **kwargs):
    context = super(OrgCreateView, self).get_context_data(*args, **kwargs)
    context.update(domain_public=is_email_public(self.get_domain()))
    return context

  def form_valid(self, form):
    if str(self.request.user.id) not in form.cleaned_data['admins']:
      form.cleaned_data['admins'].append(self.request.user.id)
    domain = self.get_domain()
    if form.instance.privacy == Organisation.PRIVACY_ORG:
      form.cleaned_data['domain'] = domain
      form.cleaned_data['visibility'] = Organisation.VISIBILITY_PRIVATE
    else:
      form.cleaned_data['domain'] = None
    result = super(OrgCreateView, self).form_valid(form)
    if form.instance.privacy == Organisation.PRIVACY_ORG:
      if is_email_public(domain):
        raise PermissionDenied
      for u in User.objects.filter(email__iendswith=domain):
        OrgMembership(user=u, organisation=form.instance).save()
    for admin in form.instance.admins.all():
      try:
        OrgMembership(user=admin, organisation=form.instance, role=OrgMembership.ADMIN).save()
      except IntegrityError:
        # Already exists, so update
        mem = OrgMembership.objects.get(user=admin, organisation=form.instance)
        mem.role = OrgMembership.ADMIN
        mem.save()

    return result

  def get_success_url(self):
    return reverse('org', kwargs={'slug': self.object.slug})


class OrgJoinView(OrgMixin, View):

  def post(self, request, *args, **kwargs):
    org = self.org
    action = request.POST.get('action')
    result = 'error'
    if action == 'join':
      if org.privacy != org.PRIVACY_OPEN:
        return HttpResponse('error:You cannot join this community')
      if request.user.is_member(org):
        return HttpResponse('error:You are already a member of this community')
      OrgMembership(user=request.user, organisation=org).save()
      if request.user.is_subscribed(org):
        request.user.subscribed.remove(org)
      result = 'joined'
    elif action == 'leave' and request.user.is_member(org):
      admins = org.admins.all()
      if request.user in admins:
        if admins.count() == 1:
          # Don't let last admin leave
          return HttpResponse('error:You must appoint a new admin before leaving')
        org.admins.remove(request.user)
      OrgMembership.objects.get(user=request.user, organisation=org).delete()
      if org.privacy == org.PRIVACY_OPEN:
        result = 'left-join'
      elif org.privacy == org.PRIVACY_APPLY:
        result = 'left-apply'
      else:
        result = 'left'
    else:
      raise PermissionDenied
    return HttpResponse(result)


class OrgApplyView(OrgMixin, View):

  def post(self, request, *args, **kwargs):
    try:
      OrgApplication(user=request.user, organisation=self.org).save()
      return HttpResponse('applied')
    except:
        return HttpResponse('error:You have already applied')


class OrgWatchView(OrgMixin, View):

  def post(self, request, *args, **kwargs):
    org = self.org
    action = request.POST.get('action')
    result = 'error'
    if action == 'follow':
      if not request.user.is_subscribed(org):
        request.user.subscribed.add(org)
        result = 'followed'
      else:
        return HttpResponse('error:You are already following')
    elif action == 'unfollow' and request.user.is_subscribed(org):
      request.user.subscribed.remove(org)
      result = 'unfollowed'
    else:
      raise PermissionDenied
    return HttpResponse(result)


class UserProfileView(LoginRequiredMixin, DetailView):
  model = User
  pk_url_kwarg = 'user_id'
  template_name = 'user_profile.html'
  context_object_name = 'puser'


class OrgStatusView(OrgMixin, View):

  def post(self, request, *args, **kwargs):
    status = int(request.POST.get('status'))
    membership = OrgMembership.objects.get(user=self.request.user, organisation=self.org)
    membership.status = status
    membership.save()
    message = {
        "type": "status",
        "id": request.user.id,
        "status": membership.status
    }
    RedisPublisher(facility='org_' + self.org.slug, broadcast=True) \
        .publish_message(RedisMessage(json.dumps(message)))
    return HttpResponse('OK')


class BotCreateView(OrgMixin, CreateView):
  require_admin = True
  template_name = 'bot_create.html'
  model = Bot
  form_class = BotCreateForm

  def form_valid(self, form):
    bot = form.save(commit=False)
    bot.organisation = self.org
    bot.owner = self.request.user
    user = User(username=form.cleaned_data['username'], is_bot=True)
    bot.save()
    user.bot = bot
    user.save()
    BotToken(bot=bot).save()
    return super(BotCreateView, self).form_valid(bot)

  def get_success_url(self):
    return reverse('bot', kwargs={'slug': self.org.slug, 'username': self.request.POST['username']})


class BotUpdateView(OrgMixin, UpdateView):
  require_admin = True
  template_name = 'bot.html'
  model = Bot
  form_class = BotUpdateForm

  def get_object(self):
    return Bot.objects.get(user__username=self.kwargs['username'])

  def get_success_url(self):
    return reverse('manage_org', kwargs={'slug': self.org.slug})


class BotDeleteView(OrgMixin, DeleteView):
  require_admin = True
  model = Bot

  def get_object(self):
    return Bot.objects.get(user__username=self.kwargs['username'])

  def form_valid(self, form):
    User.objects.get(bot=form).delete()
    return super(BotDeleteView, self).form_valid(form)

  def get_success_url(self):
    return reverse('manage_org', kwargs={'slug': self.org.slug})


class BotTokenCreateView(OrgMixin, CreateView):
  require_admin = True
  model = BotToken
  fields = []

  def dispatch(self, *args, **kwargs):
    self.bot = Bot.objects.get(user__username=self.kwargs['username'])
    return super(BotTokenCreateView, self).dispatch(*args, **kwargs)

  def form_valid(self, form):
    token = form.save(commit=False)
    token.bot = self.bot
    return super(BotTokenCreateView, self).form_valid(token)

  def get_success_url(self):
    return reverse('bot', kwargs={'slug': self.org.slug, 'username': self.bot.user.username})


class RegisterView(CreateView):
  template_name = "registration/register.html"
  model = User
  form_class = RegisterForm

  def get_success_url(self):
    if 'organisation' in self.request.POST:
      return reverse('org', kwargs={'slug': self.request.POST.get('organisation')})
    else:
      return reverse('orgs')

  def get_context_data(self):
    context = super(RegisterView, self).get_context_data()
    if 'token' in self.kwargs:
      logout(self.request)
      context.update(invite=Invitation.objects.get(token=self.kwargs.get('token')))
    return context

  def get_initial(self, **kwargs):
    if 'token' in self.kwargs:
      return {'email': Invitation.objects.get(token=self.kwargs.get('token')).email}
    else:
      return {}

  def form_valid(self, form):
    response = super(RegisterView, self).form_valid(form)
    # process invitation, if there was one
    if 'organisation' in self.request.POST:
      org = Organisation.objects.get(id=self.request.POST.get('organisation'))
      invites = Invitation.objects.filter(email=self.request.POST.get('email'), organisation=org)
      if invites.count() == 0:
        raise PermissionDenied
      membership = OrgMembership(user=user, organisation=org)
      membership.save()
      [i.delete() for i in invites]
    # Log in user
    u = authenticate(username=self.request.POST['username'].lower(), password=self.request.POST['password'])
    if u is not None and u.is_active:
      login(request, u)
    return response


class PasswordRecoveryView(TemplateView):

  email_sent = False

  def get_template_names(self):
    if self.email_sent:
      return ["password_recover_sent.html"]
    else:
      return ["password_recover.html"]

  def post(self, request, *args, **kwargs):
    user = User.objects.get(email=request.POST.get('email'))
    token = ResetToken(user=user)
    token.save()
    link = 'http://' + settings.ALLOWED_HOSTS[0] + reverse('reset_password', kwargs={'token': token.token})
    PasswordRecoveryEmail(link).send(user.email)
    self.email_sent = True
    return super(PasswordRecoveryView, self).get(request, *args, **kwargs)


class PasswordResetView(TemplateView):
  template_name = "password_reset.html"

  def get_context_data(self, *args, **kwargs):
    context = super(PasswordResetView, self).get_context_data(*args, **kwargs)
    try:
      context.update(
          user=ResetToken.objects.get(token=self.kwargs['token']).user,
          token=self.kwargs['token']
      )
    except:
      raise SuspiciousOperation
    return context

  def post(self, request, *args, **kwargs):
    pw = self.request.POST['password1']
    if pw == self.request.POST['password2']:
      user = self.get_context_data()['user']
      user.set_password(pw)
      user.save()
      ResetToken.objects.get(token=kwargs['token']).delete()
      u = authenticate(username=user.username, password=pw)
      if u is not None and u.is_active:
        login(request, u)
      return HttpResponseRedirect(reverse('orgs'))
    else:
      return super(PasswordResetView, self).get(request, *args, **kwargs)


class LandingView(TemplateView):
  template_name = "index.html"

  def dispatch(self, *args, **kwargs):
    logger.debug(self.request.user.is_authenticated)
    if self.request.user.is_authenticated:
      return OrgsView.as_view()(self.request)
    return super(LandingView, self).dispatch(*args, **kwargs)


class Error500(TemplateView):
  template_name = "error_500.html"


class Error404(TemplateView):
  template_name = "error_404.html"
