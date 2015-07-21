#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime, tzinfo, timedelta
from operator import attrgetter

from HTMLParser import HTMLParser

from google.appengine.api.mail import InboundEmailMessage
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
from google.appengine.ext import ndb

import jinja2
import json
import logging
import os
import random
import re
import speller
import traceback
import webapp2

import fix_libs
import tabun_api
# Use HTTPS:
tabun_api.http_host = u'https://tabun.everypony.ru'

################################### Templates ##################################

JINJA_ENVIRONMENT = jinja2.Environment(
  loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
  extensions=['jinja2.ext.autoescape'],
  autoescape=True)

JINJA_ENVIRONMENT.filters['spell_place'] = speller.spell_place
JINJA_ENVIRONMENT.filters['spell_weekday'] = speller.spell_weekday
JINJA_ENVIRONMENT.filters['spell_next_date'] = speller.spell_next_date
JINJA_ENVIRONMENT.filters['conjugate_votes'] = speller.conjugate_votes

##################################### Email ####################################

ZERO = timedelta(0)

class FixedOffsetTZ(tzinfo):
  def __init__(self, offset, name):
    self.__offset = timedelta(hours = offset)
    self.__name = name
  def utcoffset(self, dt):
    return self.__offset
  def tzname(self, dt):
    return self.__name
  def dst(self, dt):
    return ZERO

# Note: App Engine uses UTC as the timezone in Datastore!
UTC = FixedOffsetTZ(0, 'UTC')
MOSCOW_TIME = FixedOffsetTZ(3, 'Moscow Time')

def utc_to_moscow_time(datetime):
  """Only accepts datetime!"""
  return datetime.replace(tzinfo=UTC).astimezone(MOSCOW_TIME)
def moscow_to_utc_time(datetime):
  """Only accepts datetime!"""
  return datetime.replace(tzinfo=MOSCOW_TIME).astimezone(UTC)

class Email(ndb.Model):
  subject = ndb.StringProperty()
  sender = ndb.StringProperty()
  to = ndb.StringProperty()
  time = ndb.DateTimeProperty(auto_now_add = True)
  body_html = ndb.TextProperty()
  read = ndb.BooleanProperty()
  
  ANCESTOR_KEY = ndb.Key("Mail", "Inbox")

class InboxHandler(webapp2.RequestHandler):
  def get(self):
    if self.request.get('unread'):
      inbox = Email.query(Email.read==False).order(-Email.time).fetch()
    else:
      inbox = Email.query().order(-Email.time).fetch()
    template = JINJA_ENVIRONMENT.get_template('inbox.html')
    template_values = {
      'mail': inbox
    }
    self.response.write(template.render(template_values))

def is_art_battle_topic(topic):
  return re.match(u'(арт(-)?)?батт?л', topic.lower(), re.UNICODE) != None

def parse_email(msg):
  # Process Art-Battle messages:
  if msg.subject.find(u'У вас новое письмо') != -1:
    m = re.match(u'.*Вам пришло новое письмо от пользователя <a href="http://tabun\\.everypony\\.ru/profile/(?P<user>.+?)/".*'+
                 u'Тема письма: <b>(?P<topic>.+?)</b>.*"(?P<art_url>https?://i\.imgur.+?)".*', msg.body_html, re.UNICODE|re.DOTALL)
    if m and is_art_battle_topic(m.group('topic')):
      ab = get_state().current_battle.get()
      if ab:
        if ab.phase == ArtBattle.PHASE_BATTLE_ON:
          ab.add_participant(m.group('user'), m.group('art_url'), msg.time, msg.key)
          msg.read = True
          msg.put()
          logging.info("Successfully parsed Tabun email %d" % msg.key.id())
        else:
          logging.warn('Attempting to add participant to Art-Battle %s that is not currently on' % ab.date)
      else:
        logging.error('No current Art-Battle')
    else:
      logging.error("Couldn't parse Tabun email %d" % msg.key.id())

class ProcessEmailHandler(webapp2.RequestHandler):
  def post(self):
    email_id = int(self.request.get('id'))
    action = self.request.get('action')
    msg = Email.get_by_id(email_id, parent=Email.ANCESTOR_KEY)
    if msg:
      if action == 'parse':
        parse_email(msg)
      elif action == 'mark_read':
        msg.read = True
        msg.put()
      elif action == 'delete':
        msg.key.delete()
      else:
        logging.error("Unknown email action '%s'" % action)
    else:
      logging.error("Email not found with id '%s'" % email_id)
      self.response.set_status(404)
      self.response.write("Email not found with id '%s'" % email_id)

class EmailHandler(InboundMailHandler):
  def post(self):
    in_msg = InboundEmailMessage(self.request.body)
    logging.info("You've got mail: \"%s\" %s" % (in_msg.subject, in_msg.date))
    body = in_msg.bodies().next()
    if body[0] != 'text/html':
      logging.warn('HTML body not found')
    # Unescape because Gmail escapes HTML tags when forwarding
    body_decoded = HTMLParser().unescape(body[1].decode())
    msg = Email(parent = Email.ANCESTOR_KEY,
                   subject = in_msg.subject,
                   sender = in_msg.sender,
                   to = in_msg.to,
                   body_html = body_decoded,
                   read = False)
    msg.put()
    parse_email(msg)

    
################################## Art-Battle ##################################

TEST_BLOG_ID = 40151
ART_BATTLE_BLOG_ID = 15543


class ArtBattleError(Exception):
  pass

class ArtBattleState(ndb.Model):
  # There should only be one instance of ArtBattleState, accessed by this key name:
  KEY_ID = 'single state'
  # Current Art-Battle is the one to which participants will be added with incoming emails
  current_battle = ndb.KeyProperty(kind='ArtBattle')
  
  # Current user logged in to Tabun:
  login = ndb.StringProperty()
  phpsessid = ndb.StringProperty()
  security_ls_key = ndb.StringProperty()
  login_key = ndb.StringProperty()
  
  def get_admin(self):
    return tabun_api.User(login=self.login, phpsessid=self.phpsessid, security_ls_key=self.security_ls_key, key=self.login_key)

def get_state():
  return ArtBattleState.get_or_insert(ArtBattleState.KEY_ID)

class TabunUser(ndb.Model):
  ANCESTOR_KEY = ndb.Key('TabunUser', 'Tabun users')
  # name = ndb.StringProperty() # key is name

class Participant(ndb.Model):
  STATUS_PENDING = 0
  STATUS_APPROVED = 1
  STATUS_DECLINED = 2  # Completely denied because broke some of the strict rules: i.e. gore/vulgar content
  STATUS_LATE = 3
  STATUS_DISQUALIFIED = 4  # Broke some of the less rules: i.e. self-deanonymized
  
  number = ndb.IntegerProperty() # assigned via random shuffle before creating a poll
  user = ndb.KeyProperty(kind='TabunUser')
  art_url = ndb.StringProperty()
  art_preview_url = ndb.StringProperty()
  time = ndb.DateTimeProperty() # UTC datetime of submitting artwork. Only the time part is relevant though.
  votes = ndb.IntegerProperty(default=0)
  original_email = ndb.KeyProperty(kind='Email') # will be None for manually added participants
  status = ndb.IntegerProperty(default=STATUS_PENDING)
  
  def get_name(self):
    # Workaround for the fact that apparently python interprets Key ids as
    # non-unicode strings, and that causes jinja2 templates to fail to render
    # with a UnicodeDecodeError.
    return self.user.id().decode('utf-8')
  
  def local_time(self):
    return utc_to_moscow_time(self.time)

class ArtBattle(ndb.Model):
  PHASE_UPCOMING = 0
  PHASE_ANNOUNCED = 1
  PHASE_PREPARED = 2
  PHASE_BATTLE_ON = 3
  PHASE_REVIEW = 4 # May be skipped if all artworks are approved by the end of the battle
  PHASE_VOTING = 5
  PHASE_FINISHED = 6
  phase = ndb.IntegerProperty(default=PHASE_UPCOMING)
  
  date = ndb.DateProperty() # No two Art-Battles may have the same date!
  #TODO variable start times and length
  theme = ndb.StringProperty()
  participants = ndb.StructuredProperty(Participant, repeated=True)
  total_votes = ndb.IntegerProperty()
  
  cover_art_url = ndb.StringProperty()
  cover_art_author = ndb.KeyProperty(kind='TabunUser') # used if cover art is custom-made by a user
  cover_art_source_url = ndb.StringProperty() # used if cover art is a placeholder
  proof_screenshot_url = ndb.StringProperty()
  
  blog_id = ndb.IntegerProperty(default=ART_BATTLE_BLOG_ID)
  announcement_post_id = ndb.IntegerProperty() # the pre-announcement a couple of days before
  battle_post_id = ndb.IntegerProperty() # the post in which the theme is revealed
  poll_post_id = ndb.IntegerProperty()
  result_post_id = ndb.IntegerProperty()

  ANCESTOR_KEY = ndb.Key('ArtBattle', 'Art-Battles')
  
  def find_participant_by_number(self, i):
    for p in self.participants:
      if p.number == i:
        return p
    return None
  
  def next_ArtBattle(self):
    return ArtBattle.query(ArtBattle.date > self.date, ancestor=ArtBattle.ANCESTOR_KEY).order(ArtBattle.date).get()
  
  def post_announcement(self, draft=True):
    """Creates a post announcing the upcoming Art-Battle. Not used if the artist decides to post to 'ЯРОК'
    If announcement_post_id exists, then that post will be updated instead."""
    logging.info("Announcing Art-Battle %s" % self.date)
    # Construct post from template:
    template = JINJA_ENVIRONMENT.get_template('post-announcement.html')
    template_values = {
      'date': self.date,
      'cover_art_url': self.cover_art_url,
      'cover_art_author': self.cover_art_author,
      'cover_art_source_url': self.cover_art_source_url,
    }
    if self.date - datetime.now().date() == timedelta(1): # <- This will work only if posting exactly the day before the battle
      template_values['tomorrow'] = True
    
    post_title = u'Объявление Арт-Баттла %s' % self.date
    post_body = template.render(template_values)
    post_tags = u'Арт-Баттл, объявление, конкурс, %s' % self.date
    user = get_state().get_admin()
    if not self.announcement_post_id: # first time:
      ret = user.add_post(self.blog_id, post_title, post_body, post_tags, draft)
      self.announcement_post_id = ret[1]
      self.phase = ArtBattle.PHASE_ANNOUNCED
      self.put()
      logging.info('Created announcement post for Art-Battle %s' % self.date)
    else:
      user.edit_post(self.announcement_post_id, self.blog_id, post_title, post_body, post_tags, draft)
      logging.info('Updated announcement post for Art-Battle %s' % self.date)
  
  def post_battle(self, draft=True):
    """Creates a post for the date's Art-Battle. This post will be later updated with the theme.
    If battle_post_id exists, then that post will be updated instead"""
    logging.info("Preparing Art-Battle %s" % self.date)
    user = get_state().get_admin()
    # Construct post from template:
    template = JINJA_ENVIRONMENT.get_template('post-battle.html')
    template_values = {
      'date': self.date,
      'admin_login': user.username,
      'cover_art_url': self.cover_art_url,
      'cover_art_author': self.cover_art_author,
      'cover_art_source_url': self.cover_art_source_url,
    }
    if self.phase >= ArtBattle.PHASE_BATTLE_ON:
      template_values['theme'] = self.theme
    post_title = u'Арт-Баттл %s' % self.date
    post_body = template.render(template_values)
    post_tags = u'Арт-Баттл, конкурс, %s' % self.date
    if not self.battle_post_id:
      ret = user.add_post(self.blog_id, post_title, post_body, post_tags, draft)
      self.battle_post_id = ret[1]
      self.phase = ArtBattle.PHASE_PREPARED
      self.put()
      logging.info('Created post for Art-Battle %s' % self.date)
    else:
      user.edit_post(self.battle_post_id, self.blog_id, post_title, post_body, post_tags, draft)
      logging.info('Updated post for Art-Battle %s' % self.date)

  def set_theme(self, theme, draft=False):
    """Sets the theme and begins Art-Battle."""
    logging.info("Setting Art-Battle theme: '%s'. Art-Battle begins!" % theme)
    self.theme = theme
    self.put()
    if self.battle_post_id:
      self.phase = ArtBattle.PHASE_BATTLE_ON
      self.put()
      self.post_battle(draft)
    else:
      raise ArtBattleError('Battle post ID not set')

  def post_poll(self, draft=True):
    """Ends Art-Battle and starts a poll to find the winner.
    If poll_post_id exists, that post will be updated instead."""
    # Make sure all submissions have been reviewed:
    for p in self.participants:
      if p.status == Participant.STATUS_PENDING:
        raise ArtBattleError('Not all participants have been reviewed')
    logging.info("Creating poll for Art-Battle %s" % self.date)
    choices = []
    # Shuffle participants' numbers:
    i = 1
    for p in random.sample(self.participants, len(self.participants)):
      p.number = i
      if p.status == Participant.STATUS_APPROVED:
        choices.append(u'Участник %d' % i)
      i += 1
    
    has_disqualified = False
    for p in self.participants:
      if p.status == Participant.STATUS_DISQUALIFIED:
        has_disqualified = True
        break
    # Construct post from template:
    participant_sorted = sorted(self.participants, key=attrgetter('number'))
    template = JINJA_ENVIRONMENT.get_template('post-poll.html')
    template_values = {
      'theme': self.theme,
      'participants': participant_sorted,
      'has_disqualified': has_disqualified,
    }
    post_title = u'Голосование за Арт-Баттл %s' % self.date
    post_body = template.render(template_values)
    post_tags = u'Арт-Баттл, голосование, %s, %s' % (self.date, self.theme)
    user = get_state().get_admin()
    if not self.poll_post_id:
      ret = user.add_poll(self.blog_id, post_title, choices, post_body, post_tags, draft)
      self.poll_post_id = ret[1]
      # TODO check if artworks need approval and then proceed to either PHASE_REVIEW or PHASE_VOTING
      self.phase = ArtBattle.PHASE_VOTING
      self.put()
      logging.info('Created poll post for Art-Battle %s' % self.date)
      # Vote (for no candidate) to make sure poll results are readable:
      user.poll_answer(self.poll_post_id, -1)
    else:
      # TODO edit poll to accept late submissions
      logging.info('[NOT IMPLEMENTED] Updated poll post for Art-Battle %s' % self.date)

  def count_votes(self):
    """Parse poll post to update participants with their respective vote coutn"""
    logging.info("Ending and counting votes for Art-Battle %s" % self.date)
    user = get_state().get_admin()
    # Vote (for no candidate) to make sure poll results are readable:
    try:
      poll = user.poll_answer(self.poll_post_id, -1)
    except tabun_api.TabunResultError: # Probably means we've already voted
      poll = user.get_post(self.poll_post_id).poll
    try:
      self.total_votes = poll.total
      for i in range(len(poll.items)):
        p = self.find_participant_by_number(i+1)
        if p:
          p.votes = poll.items[i][2]
        else:
          logging.warn('Participant #%d found in vote but not in Art-Battle' % i)
    except AttributeError:
      raise tabun_api.TabunError(msg="Invalid poll post #%d" % self.poll_post_id)
    #TODO take screenshot
    self.put()
  
  def post_results(self, draft=True):
    """Creates a post with results.
    If result_post_id exists, that post will be updated instead."""
    places = [] # Participants grouped by the number of votes
    disqualified = [] # Disqualified participants
    participant_sorted = sorted(self.participants, key=attrgetter('votes'), reverse=True)
    current_votes = -1
    current_place = []
    for p in participant_sorted:
      if p.status == Participant.STATUS_APPROVED:
        if current_votes == p.votes:
          current_place.append(p)
        else:
          current_place = [p]
          places.append(current_place)
          current_votes = p.votes
      elif p.status == Participant.STATUS_DISQUALIFIED or p.status == Participant.STATUS_LATE:
        disqualified.append(p)
    
    # Construct post from template:
    template = JINJA_ENVIRONMENT.get_template('post-results.html')
    template_values = {
      'theme': self.theme,
      'places': places,
      'disqualified': disqualified,
      'proof_screenshot_url': self.proof_screenshot_url,
    }
    next_ab = self.next_ArtBattle()
    if next_ab:
      template_values['next_date'] = next_ab.date
      if next_ab.date == self.date:
        template_values['next_today'] = True
      elif next_ab.date - self.date == timedelta(1):
        template_values['next_tomorrow'] = True
    
    post_title = u'Итоги голосования за Арт-Баттл %s' % self.date
    post_body = template.render(template_values)
    post_tags = u'Арт-Баттл, итоги голосования, %s, %s' % (self.date, self.theme)
    logging.info(post_body)
    user = get_state().get_admin()
    if not self.result_post_id:
      ret = user.add_post(self.blog_id, post_title, post_body, post_tags, draft)
      self.result_post_id = ret[1]
      # TODO: send message to winner(s)
      self.phase = ArtBattle.PHASE_FINISHED
      self.put()
      logging.info('Created results post for Art-Battle %s' % self.date)
    else:
      user.edit_post(self.result_post_id, self.blog_id, post_title, post_body, post_tags, draft)
      logging.info('Updated results post for Art-Battle %s' % self.date)
  
  def add_participant(self, username, art_url, time=datetime.now(), original_email_key=None):
    """Add a participant to this Art-Battle and format their artwork."""
    user = TabunUser.get_or_insert(username, parent=TabunUser.ANCESTOR_KEY)
    # TODO: resize image and upload to imgur.com (if needed)
    p = Participant(user=user.key, art_url=art_url, time=time, original_email=original_email_key, number=len(self.participants)+1)
    # Assuming an imgur.com URL, the preview URL is "....s.jpg/png"
    p.art_preview_url = art_url[:-4] + 's' + art_url[-4:]
    self.participants.append(p)
    self.put()


#################################### Editor ####################################

class ABBaseHandler(webapp2.RequestHandler):
  def get_date(self):
    param_date = self.request.get('date')
    try:
      return datetime.strptime(param_date, '%Y-%m-%d').date()
    except:
      logging.warn("Couldn't parse date '%s'" % param_date)
      return None
  def get_ArtBattle(self):
    date = self.get_date()
    if date:
      ab = ArtBattle.query(ArtBattle.date==date, ancestor=ArtBattle.ANCESTOR_KEY).get()
      if not ab:
        logging.warn("Art-Battle not found on date '%s'" % date)
      return ab
    return None


class ABCreateHandler(ABBaseHandler):
  def post(self, *args):
    date = self.get_date()
    if date:
      if self.get_ArtBattle():
        logging.warn("Art-Battle already exists on date '%s'" % date)
      else:
        ArtBattle(parent=ArtBattle.ANCESTOR_KEY, date=date).put()
        logging.info("Created Art-Battle on '%s'" % date)
      self.redirect('/artbattle/edit?date=%s' % date)
    else:
      self.redirect('/artbattle/edit')

class ABDeleteHandler(ABBaseHandler):
  def delete(self, *args):
    ab = self.get_ArtBattle()
    if ab:
      ab.key.delete()
      logging.info("Deleted Art-Battle on '%s'" % ab.date)
    else:
      logging.warn("Art-Battle not found on date")
      self.response.set_status(404)

class ABEditorHandler(ABBaseHandler):
  def get(self, *args):
    template = JINJA_ENVIRONMENT.get_template('art-battle-edit.html')
    template_values = {
      'user': get_state().login,
      'edit_participants': self.request.get('edit_participants', 0) != 0
    }
    # Read list of dates:
    dates = ArtBattle.query(ancestor=ArtBattle.ANCESTOR_KEY).order(ArtBattle.date).fetch(projection=ArtBattle.date)
    template_values['dates'] = dates
    # Read Art-Battle:
    ab = self.get_ArtBattle()
    if ab:
      template_values['artbattle'] = ab
    self.response.write(template.render(template_values))

class ABPostAnnouncementHandler(ABBaseHandler):
  def post(self, *args):
    ab = self.get_ArtBattle()
    if ab:
      try:
        ab.post_announcement(draft=self.request.get('draft'))
      except (tabun_api.TabunError, ArtBattleError) as e:
        logging.error(traceback.format_exc())
        self.response.set_status(403)
        self.response.write(e.message)

class ABPostBattleHandler(ABBaseHandler):
  def post(self, *args):
    ab = self.get_ArtBattle()
    if ab:
      try:
        ab.post_battle(draft=self.request.get('draft'))
      except (tabun_api.TabunError, ArtBattleError) as e:
        logging.error(traceback.format_exc())
        self.response.set_status(403)
        self.response.write(e.message)

class ABSetThemeHandler(ABBaseHandler):
  def post(self, *args):
    theme = self.request.get('theme')
    ab = self.get_ArtBattle()
    if ab:
      try:
        ab.set_theme(theme, draft=self.request.get('draft'))
      except (tabun_api.TabunError, ArtBattleError) as e:
        logging.error(traceback.format_exc())
        self.response.set_status(403)
        self.response.write(e.message)

class ABPostPollHandler(ABBaseHandler):
  def post(self, *args):
    ab = self.get_ArtBattle()
    if ab:
      try:
        ab.post_poll(draft=self.request.get('draft'))
      except (tabun_api.TabunError, ArtBattleError) as e:
        logging.error(traceback.format_exc())
        self.response.set_status(403)
        self.response.write(e.message)

class ABCountVotesHandler(ABBaseHandler):
  def post(self, *args):
    ab = self.get_ArtBattle()
    if ab:
      try:
        ab.count_votes()
      except (tabun_api.TabunError, ArtBattleError) as e:
        logging.error(traceback.format_exc())
        self.response.set_status(403)
        self.response.write(e.message)

class ABPostResultsHandler(ABBaseHandler):
  def post(self, *args):
    ab = self.get_ArtBattle()
    if ab:
      try:
        ab.post_results(draft=self.request.get('draft'))
      except (tabun_api.TabunError, ArtBattleError) as e:
        logging.error(traceback.format_exc())
        self.response.set_status(403)
        self.response.write(e.message)

class ABUpdateHandler(ABBaseHandler):
  def update_field(self, ab, field, is_int=False):
    """Updates ArtBattle's field with str or int data from request.
       If field is empty, sets it to None."""
    field_value = self.request.get(field)
    if not field_value or field_value=='':
      setattr(ab, field, None)
    else:
      if is_int:
        setattr(ab, field, int(field_value))
      else:
        setattr(ab, field, field_value)
  
  def post(self, *args):
    ab = self.get_ArtBattle()
    if ab:
      try:
        self.update_field(ab, 'phase', True)
        self.update_field(ab, 'blog_id', True)
        self.update_field(ab, 'theme')
        self.update_field(ab, 'announcement_post_id', True)
        self.update_field(ab, 'battle_post_id', True)
        self.update_field(ab, 'poll_post_id', True)
        self.update_field(ab, 'result_post_id', True)
        self.update_field(ab, 'cover_art_url')
        self.update_field(ab, 'cover_art_source_url')
        self.update_field(ab, 'proof_screenshot_url')
        cover_art_author = self.request.get('cover_art_author')
        if cover_art_author and cover_art_author != '':
          ab.cover_art_author = TabunUser.get_or_insert(cover_art_author, parent=TabunUser.ANCESTOR_KEY).key
        else:
          ab.cover_art_author = None
        ab.put()
      except ValueError as e:
        logging.error(traceback.format_exc())
        self.response.set_status(400)
        self.response.write(e.message)

class ABParticipantAddHandler(ABBaseHandler):
  def post(self, *args):
    ab = self.get_ArtBattle()
    if ab:
      try:
        username = self.request.get('username').strip()
        time = datetime.combine(ab.date, moscow_to_utc_time(datetime.strptime(self.request.get('time'), '%H:%M')).time())
        art_url = self.request.get('art_url')
        ab.add_participant(username, art_url, time)
        ab.put()
      except ValueError as e:
        logging.error(traceback.format_exc())
        self.response.set_status(400)
        self.response.write(e.message)

class ABParticipantReviewHandler(ABBaseHandler):
  def post(self, *args):
    ab = self.get_ArtBattle()
    if ab:
      verdict = self.request.get('verdict')
      p_id = int(self.request.get('id'))
      logging.info("Reviewing participant %d with verdict '%s'" % (p_id, verdict))
      participant = ab.participants[p_id]
      if verdict == 'approve':
        participant.status = Participant.STATUS_APPROVED
        ab.put()
      elif verdict == 'decline':
        participant.status = Participant.STATUS_DECLINED
        ab.put()
      else:
        logging.warn("Unknown review verdict ''" % verdict)

class ABParticipantsEditHandler(ABBaseHandler):
  def post(self, *args):
    ab = self.get_ArtBattle()
    to_delete = []
    # array params don't seem to work for me, so using a JSON string instead :/
    req_participants = json.loads(self.request.get('participants'))
    if ab:
      try:
        for p, req in zip(ab.participants, req_participants):
          if req['delete']:
            to_delete.append(p)
          else:
            p.time = datetime.combine(ab.date, moscow_to_utc_time(datetime.strptime(req['time'], '%H:%M')).time())
            p.user = TabunUser.get_or_insert(req['username'].strip(), parent=TabunUser.ANCESTOR_KEY).key
            p.art_url = req['art_url']
            p.art_preview_url = req['art_preview_url']
            p.number = int(req['number'])
            p.votes = int(req['votes'])
            p.status = int(req['status'])
        for p in to_delete:
          ab.participants.remove(p)
        # Recalculate total_votes
        total_votes = 0
        for p in ab.participants:
          total_votes += p.votes
        ab.total_votes = total_votes
        ab.put()
      except ValueError as e:
        logging.error(traceback.format_exc())
        self.response.set_status(400)
        self.response.write(e.message)

class ABCurrentHandler(ABBaseHandler):
  """GET request returns current Art-Battle, POST request makes given date current."""
  def get(self, *args):
    state = get_state()
    if state.current_battle:
      self.redirect('/artbattle/edit?date=%s' % state.current_battle.get().date)
    else:
      self.redirect('/artbattle/edit')
  def post(self, *args):
    state = get_state()
    ab = self.get_ArtBattle()
    if ab:
      logging.info('Made date %s current' % ab.date)
      state.current_battle = ab.key
      state.put()

class ABLoginHandler(ABBaseHandler):
  def get(self, *args):
    state = get_state()
    template = JINJA_ENVIRONMENT.get_template('login.html')
    template_values = {
      'user': state.login
    }
    self.response.write(template.render(template_values))
  def post(self, *args):
    """Log in and store login, phpsessid and security_ls_key"""
    try:
      state = get_state()
      user = tabun_api.User(self.request.get('login'), self.request.get('password'))
      state.login = user.username
      state.phpsessid = user.phpsessid
      state.security_ls_key = user.security_ls_key
      state.login_key = user.key
      state.put()
      logging.info('Logged in as %s' % state.login)
      self.redirect('/artbattle/edit')
    except (tabun_api.TabunError, ValueError) as e:
        logging.error(traceback.format_exc())
        self.response.set_status(403)
        self.response.write(e.message)


##################################### Misc #####################################
  
class HelloHandler(webapp2.RequestHandler):
  def get(self):
    self.response.write("Hi! I'm minihorse.")


app = webapp2.WSGIApplication([
  ('/', HelloHandler),
  ('/inbox', InboxHandler),
  ('/process_email', ProcessEmailHandler),
  EmailHandler.mapping(),
  ('/artbattle/create', ABCreateHandler),
  ('/artbattle/delete', ABDeleteHandler),
  ('/artbattle/edit', ABEditorHandler),
  ('/artbattle/update', ABUpdateHandler),
  ('/artbattle/post_announcement', ABPostAnnouncementHandler),
  ('/artbattle/post_battle', ABPostBattleHandler),
  ('/artbattle/set_theme', ABSetThemeHandler),
  ('/artbattle/post_poll', ABPostPollHandler),
  ('/artbattle/count_votes', ABCountVotesHandler),
  ('/artbattle/post_results', ABPostResultsHandler),
  ('/artbattle/participant/add', ABParticipantAddHandler),
  ('/artbattle/participant/review', ABParticipantReviewHandler),
  ('/artbattle/participant/edit', ABParticipantsEditHandler),
  ('/artbattle/current', ABCurrentHandler),
  ('/login', ABLoginHandler),
], debug=True)
