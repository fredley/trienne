# -*- coding: utf-8 -*-
import json
import re
import collections
import logging

from cgi import escape
from urlparse import urlparse

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.views.generic import DetailView
from django.views.generic.base import TemplateView, View
from django.views.generic.edit import CreateView, UpdateView
from django.views.decorators.csrf import csrf_exempt

from django_gravatar.helpers import get_gravatar_url
from ratelimit.mixins import RatelimitMixin
from ws4redis.redis_store import RedisMessage
from ws4redis.publisher import RedisPublisher

from .models import *
from .forms import *

url_dot_test = re.compile(ur'.+\..+')
logger = logging.getLogger('django')
User = get_user_model()


lf_youtube = re.compile(ur'(.*)v=([A-Za-z0-9]*)')


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
    return "<pre>{}</pre>".format(escape(code).replace("'", "&#39;"))
  # Check for oneboxes
  link = valid_link(text, is_onebox=True)
  if link is not False:
    return link
  text = escape(text).replace("'", "&#39;").replace("\n", "<br>")
  # Apply Markdown rules
  for regex, replacement in md_rules.items():
    text = re.sub(regex, replacement, text)
  return text.strip()


def ratelimit(request, ex):
  return JsonResponse({
      'error': True,
      'message': 'Too Fast!'
    }, status=418)


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


class RoomPostView(LoginRequiredMixin, RatelimitMixin, View):

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
    if self.room.organisation not in request.user.organisations.all():
      raise PermissionDenied
    if self.room.privacy == Room.PRIVACY_PRIVATE and request.user not in self.room.members.all():
      raise PermissionDenied
    if self.require_admin and not (request.user.is_admin(self.room.organisation) or
      request.user not in self.room.owners.all()):
      raise PermissionDenied
    self.publisher = RedisPublisher(facility='room_' + str(kwargs['room_id']), broadcast=True)
    return self.generate_response(request)


class RoomView(LoginRequiredMixin, TemplateView):
  template_name = 'room.html'

  def get_context_data(self, **kwargs):
    context = super(RoomView, self).get_context_data(**kwargs)
    room = Room.objects.get(id=kwargs['room_id'])
    if not self.request.user.can_view(room):
      raise PermissionDenied
    elif self.request.user not in room.members.all():
      logger.debug("Added " + str(self.request.user) + " to " + str(room))
      room.members.add(self.request.user)
    publisher = RedisPublisher(facility='room_' + str(kwargs['room_id']), broadcast=True)
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
          "online": (publisher.get_present(u) or u == self.request.user)
      })
    message = {
        'type': 'join',
        'id': self.request.user.id,
        # Add this in case user is brand new and not in list
        'username': self.request.user.username,
        'img': get_gravatar_url(self.request.user.email, size=32)
    }
    publisher.publish_message(RedisMessage(json.dumps(message)))
    context.update(room=room,
                   org=room.organisation,
                   is_admin=self.request.user.is_admin(room.organisation),
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

  def generate_response(self, request):
    post = Post(room=self.room, author=request.user)
    post.save()
    raw = request.POST.get('message')
    try:
        processed = process_text(raw)
        logger.debug(processed)
    except:
        return HttpResponse('Not OK')
    content = PostContent(
        author=request.user,
        post=post,
        raw=raw,
        content=processed)
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
      raise PermissionDenied
    return super(OrgMixin, self).dispatch(*args, **kwargs)

  def get_context_data(self, **kwargs):
    context = super(OrgMixin, self).get_context_data(**kwargs)
    user = self.request.user
    context.update(org=self.org,
                   is_admin=user.is_admin(self.org),
                   has_applied=OrgApplication.objects.filter(user=user, organisation=self.org).count() > 0,
                   is_member=self.org in user.organisations.all(),
                   is_follower=self.org in user.subscribed.all())
    return context


class RoomAddView(OrgMixin, CreateView):
  model = Room
  form_class = RoomForm
  template_name = "add_room.html"

  def get_initial(self):
    return {'owners': "{}".format(self.request.user.id)}

  def form_valid(self, form):
    room = form.save(commit=False)
    room.organisation = self.org
    room.creator = self.request.user
    room.save()
    room.members = [self.request.user]
    if self.request.user not in room.owners.all():
      room.owners.add(self.request.user)
    self.object = room
    return HttpResponseRedirect(reverse("room", kwargs={"room_id": room.id}))


class RoomEditView(LoginRequiredMixin, UpdateView):
  template_name = "room_edit.html"
  model = Room
  pk_url_kwarg = 'room_id'
  form_class = RoomForm

  def get_context_data(self, *args, **kwargs):
    logger.debug(self.object.owners.all())
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
        processed = process_text(raw)
    except:
        return HttpResponse('Not OK')
    content = PostContent(
        author=request.user,
        post=self.msg,
        raw=raw,
        content=processed)
    content.save()
    message = {
        'type': 'edit',
        'content': processed,
        'raw': raw,
        'id': self.msg.id
    }
    RedisPublisher(facility='room_' + str(self.msg.room.id), broadcast=True) \
        .publish_mressage(RedisMessage(json.dumps(message)))
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
      /ajax/orgs/all/      - all orgs
      /ajax/orgs/mine/     - my orgs
      /ajax/orgs/watching/ - orgs I'm watching
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


class UserManagementView(LoginRequiredMixin, AjaxResponseMixin, CreateView):

  template_name = "user_management.html"
  model = Invitation
  fields = ['organisation', 'email']

  def get_success_url(self):
    return ''

  def form_valid(self, form):
    users = User.objects.filter(email=form.instance.email)
    if users.count() > 0:
      # Just add user as member
      OrgMembership(user=users[0], organisation=form.instance.organisation).save()
      return HttpResponse('OK')
    response = super(UserManagementView, self).form_valid(form)  # Saves form
    org = form.instance.organisation
    link = 'http://' + settings.ALLOWED_HOSTS[0] + reverse('invitation', kwargs={'token': form.instance.token})
    send_mail('Join {} on lanes'.format(org.name),
        'You have been invited to join {} on lanes, please click this link to sign up:\n\n{}'.format(org.name, link),
        'noreply@lanes.net',
    [form.instance.email], fail_silently=True)
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
  form_class = OrgForm
  require_admin = True

  def get_context_data(self, **kwargs):
    context = super(OrgManagementView, self).get_context_data(**kwargs)
    context.update(applications=OrgApplication.objects.filter(organisation=self.org, rejected=False))
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

  def get_initial(self):
    return {'admins': "{}".format(self.request.user.id)}

  def form_valid(self, form):
    if str(self.request.user.id) not in form.cleaned_data['admins']:
      form.cleaned_data['admins'].append(self.request.user.id)
    result = super(OrgCreateView, self).form_valid(form)
    logger.debug(form.instance.id)
    for admin in form.instance.admins.all():
      OrgMembership(user=admin, organisation=form.instance, role=OrgMembership.ADMIN).save()
    return result

  def get_success_url(self):
    return reverse('org', kwargs={'slug': self.object.slug})


class OrgJoinView(OrgMixin, AjaxResponseMixin, View):

  def post(self, request, *args, **kwargs):
    org = self.org
    action = request.POST.get('action')
    result = 'error'
    if action == 'join':
      if org.privacy == Organisation.PRIVACY_OPEN and not request.user.is_member(org):
        OrgMembership(user=request.user, organisation=org).save()
        if request.user.is_subscribed(org):
          request.user.subscribed.remove(org)
        result = 'joined'
      else:
        raise PermissionDenied
    elif action == 'leave' and request.user.is_member(org):
      OrgMembership.objects.get(user=request.user, organisation=org).delete()
      if request.user in org.admins.all():
        org.admins.remove(request.user)
      result = 'left'
    else:
      raise PermissionDenied
    return HttpResponse(result)


class OrgApplyView(OrgMixin, AjaxResponseMixin, View):

  def post(self, request, *args, **kwargs):
    OrgApplication(user=request.user, organisation=self.org).save()
    return HttpResponse('applied')


class OrgWatchView(OrgMixin, AjaxResponseMixin, View):

  def post(self, request, *args, **kwargs):
    org = self.org
    action = request.POST.get('action')
    result = 'error'
    if action == 'follow':
      if not request.user.is_subscribed(org):
        request.user.subscribed.add(org)
        result = 'followed'
      else:
        raise PermissionDenied
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


class RegisterView(TemplateView):
  template_name = "registration/register.html"

  def get_context_data(self, **kwargs):
    context = super(RegisterView, self).get_context_data(**kwargs)
    if 'token' in kwargs:
      logout(self.request)
      context.update(invite=Invitation.objects.get(token=kwargs.get('token')))
    return context

  def post(self, request, *args, **kwargs):
    user = User.objects.create_user(request.POST['username'], request.POST['email'],
                                    request.POST['password'])
    user.save()
    if 'organisation' in request.POST:
      org = Organisation.objects.get(id=request.POST.get('organisation'))
      invites = Invitation.objects.filter(email=request.POST.get('email'), organisation=org)
      if invites.count() == 0:
        raise PermissionDenied
      membership = OrgMembership(user=user, organisation=org)
      membership.save()
      [i.delete() for i in invites]
    u = authenticate(username=request.POST['username'], password=request.POST['password'])
    if u is not None and u.is_active:
      login(request, u)
    if 'organisation' in request.POST:
      return HttpResponseRedirect(reverse('org', kwargs={'slug': org.slug}))
    else:
      return HttpResponseRedirect(reverse('orgs'))
