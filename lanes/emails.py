from django.core.mail import send_mail


class BaseEmail(object):

  from_email = 'noreply@lanes.net'

  def get_subject(self):
    return self.subject

  def get_message(self):
    return self.message

  def get_from(self):
    return self.from_email

  def send(self, recipients):
    if isinstance(recipients, basestring):
      recipients = [recipients]
    send_mail(self.get_subject(), self.get_message(), self.get_from(), recipients, fail_silently=True)


class InvitationEmail(BaseEmail):

  def __init__(self, org, link):
    self.message = 'You have been invited to join {} on lanes, please click this link to sign up:\n\n{}'.format(org.name, link)
    self.subject = 'Join {} on lanes'.format(org.name)


class NotificationEmail(BaseEmail):

  def __init__(self, post):
    self.message = 'While you were away, {0} sent you a message on lanes:\n\n"{1}"'.format(post.author.username, post.get_content())
    self.subject = 'New notification on lanes'
