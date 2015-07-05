#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime, tzinfo, timedelta

from google.appengine.api.mail import InboundEmailMessage
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
from google.appengine.ext import ndb

import jinja2
import json
import logging
import os
import random
import traceback
import webapp2

import fix_libs
import tabun_api

JINJA_ENVIRONMENT = jinja2.Environment(
  loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
  extensions=['jinja2.ext.autoescape'],
  autoescape=True)


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


class Email(ndb.Model):
  subject = ndb.StringProperty()
  sender = ndb.StringProperty()
  to = ndb.StringProperty()
  time = ndb.DateTimeProperty(auto_now_add = True)
  body_html = ndb.TextProperty()
  read = ndb.BooleanProperty()
  
  def moscow_time(self):
    return self.time.replace(tzinfo=UTC).astimezone(MOSCOW_TIME)

class InboxHandler(webapp2.RequestHandler):
  def get(self):
    self.response.write('<html><body>')
    inbox = Email.query().order(-Email.time).fetch()
    for mail in inbox:
      self.response.write('<h1>%s</h1><a>From: %s<br>To: %s<br>Time: %s</a><p>%s</p><hr>' % (mail.subject, mail.sender, mail.to, mail.moscow_time(), mail.body_html))
    self.response.write('</body></html>')


class EmailHandler(InboundMailHandler):
  def post(self):
    msg = InboundEmailMessage(self.request.body)
    logging.info("You've got mail: \"%s\" %s" % (msg.subject, msg.date))
    body = msg.bodies(content_type='text/html').next()
    if body[0] != 'text/html':
      logging.warn('HTML body not found')
    msg_db = Email(parent = ndb.Key("Mail", "Inbox"),
                   subject = msg.subject,
                   sender = msg.sender,
                   to = msg.to,
                   body_html = body[1].decode(),
                   read = False)
    msg_db.put()

    
################################## Art-Battle ##################################

LOGIN = 'minihorse'
PASSWORD = 'tabunminihorsebot'

TEST_BLOG_ID = 40151
ART_BATTLE_BLOG_ID = 15543
BLOG_ID = TEST_BLOG_ID # The value used by the ArtBattle class


def get_admin():
  return tabun_api.User(LOGIN, PASSWORD)

class ArtBattleError(Exception):
  pass

class TabunUser(ndb.Model):
  ANCESTOR_KEY = ndb.Key('TabunUser', 'Tabun users')
  name = ndb.StringProperty()

class Participant(ndb.Model):
  STATUS_PENDING = 0
  STATUS_APPROVED = 1
  STATUS_DECLINED = 2 # Broke some of the rules: i.e. self-deanonymized
  STATUS_LATE = 3
  number = ndb.IntegerProperty() # assigned via random shuffle before creating a poll
  user = ndb.KeyProperty(kind='TabunUser')
  art_url = ndb.StringProperty()
  art_preview_url = ndb.StringProperty()
  time = ndb.TimeProperty() # UTC time of submitting artwork
  votes = ndb.IntegerProperty(default=0)
  original_email = ndb.KeyProperty(kind='Email') # will be None for manually added participants
  status = ndb.IntegerProperty(default=STATUS_PENDING)

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
  theme = ndb.StringProperty()
  participants = ndb.StructuredProperty(Participant, repeated=True)
  total_votes = ndb.IntegerProperty()
  
  cover_art_url = ndb.StringProperty()
  cover_art_author = ndb.KeyProperty(kind='TabunUser') # used if cover art is custom-made by a user
  cover_art_source_url = ndb.StringProperty() # used if cover art is a placeholder
  
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
  
  def announce(self):
    """Creates a post announcing the upcoming Art-Battle. Not used if the artist decides to post to 'ЯРОК'"""
    logging.info("Announcing Art-Battle %s" % self.date)
    user = get_admin()
    # TODO: pre-announcement text
    text = u'Текст объявления Арт-Баттла'
    ret = user.add_post(BLOG_ID, u'Объявление Арт-Баттла %s' % self.date, text, u'Арт-Баттл, объявление, конкурс, %s' % self.date)
    self.announcement_post_id = ret[1]
    self.phase = ArtBattle.PHASE_ANNOUNCED
    self.put()
  
  def prepare(self):
    """Creates a post for the date's Art-Battle. This post will be later updated with the theme."""
    logging.info("Preparing Art-Battle %s" % self.date)
    user = get_admin()
    # TODO: announcement text
    text = u'Текст Арт-Баттла без темы'
    ret = user.add_post(BLOG_ID, u'Арт-Баттл %s' % self.date, text, u'Арт-Баттл, конкурс, %s' % self.date)
    self.battle_post_id = ret[1]
    self.phase = ArtBattle.PHASE_PREPARED
    self.put()

  def set_theme(self, theme):
    """Sets the theme and begins Art-Battle."""
    logging.info("Setting Art-Battle theme: '%s'. Art-Battle begins!" % theme)
    self.theme = theme
    self.put()
    user = get_admin()
    # TODO: announcement text + theme
    text = u'Текст Арт-Баттла с темой'
    user.edit_post(self.battle_post_id, BLOG_ID, u'Арт-Баттл %s' % self.date, text, u'Арт-Баттл, конкурс, %s' % self.date)
    self.phase = ArtBattle.PHASE_BATTLE_ON
    self.put()

  def create_poll(self):
    """Ends Art-Battle and starts a poll to find the winner."""
    # Make sure all submissions have been reviewed:
    for p in self.participants:
      if p.status == Participant.STATUS_PENDING:
        raise ArtBattleError('Not all participants have been reviewed')
    logging.info("Creating poll for Art-Battle %s" % self.date)
    user = get_admin()
    # TODO: voting text
    text = u'Текст голосования'
    choices = []
    # Shuffle participants' numbers:
    i = 1
    for p in random.sample(self.participants, len(self.participants)):
      p.number = i
      choices.append(u'Участник %d' % i)
      i += 1
    ret = user.add_poll(BLOG_ID, u'Голосование за Арт-Баттл %s' % self.date, choices, text, u'Арт-Баттл, голосвание, %s' % self.date)
    self.poll_post_id = ret[1]
    # TODO check if artworks need approval and then proceed to either PHASE_REVIEW or PHASE_VOTING
    self.phase = ArtBattle.PHASE_VOTING
    self.put()
  
  def update_poll(self):
    """Update the poll post with late submissions"""
    # TODO: update_poll
    pass

  def count_votes(self):
    """Ends voting and creates a post with results."""
    logging.info("Ending and counting votes for Art-Battle %s" % self.date)
    user = get_admin()
    post = user.get_post(self.poll_post_id)
    try:
      self.total_votes = post.poll.total
      for i in range(len(post.poll.items)):
        p = self.find_participant_by_number(i+1)
        if p:
          p.votes = post.poll.items[i][2]
        else:
          logging.warn('Participant #%d found in vote but not in Art-Battle' % i)
    except AttributeError:
      raise tabun_api.TabunError(msg="Invalid poll post #%d" % self.poll_post_id)
    # TODO: voting result text
    text = u'Текст результата'
    ret = user.add_post(BLOG_ID, u'Итоги голосования за Арт-Баттл %s' % self.date, text, u'Арт-Баттл, итоги голосования, %s' % self.date)
    self.result_post_id = ret[1]
    # TODO: send message to winner(s)
    self.phase = ArtBattle.PHASE_FINISHED
    self.put()
  
  def add_participant(self, username, art_url, time=datetime.now().time(), original_email=None):
    """Add a participant to this Art-Battle and format their artwork."""
    user = TabunUser.get_or_insert(username, parent=TabunUser.ANCESTOR_KEY)
    # TODO: resize image and upload to imgur.com (if needed)
    p = Participant(user=user.key, art_url=art_url, time=time, original_email=original_email)
    # Assuming an imgur.com URL, the preview URL is "....s.jpg/png"
    p.art_preview_url = art_url[:-4] + 's' + art_url[-4:]
    self.participants.append(p)
    self.put()

class ArtBattleState(ndb.Model):
  # There should only be one instance of ArtBattleState, accessed by this key name:
  KEY_ID = 'single state'
  # Current Art-Battle is the one to which participants will be added with incoming emails
  current_battle = ndb.KeyProperty(kind='ArtBattle')


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

class ABAnnounceHandler(ABBaseHandler):
  def post(self, *args):
    ab = self.get_ArtBattle()
    if ab:
      try:
        ab.announce()
      except tabun_api.TabunError as e:
        logging.error(traceback.format_exc())
        self.response.set_status(403)
        self.response.write(e.message)

class ABSetThemeHandler(ABBaseHandler):
  def post(self, *args):
    theme = self.request.get('theme')
    ab = self.get_ArtBattle()
    if ab:
      try:
        ab.set_theme(theme)
      except tabun_api.TabunError as e:
        logging.error(traceback.format_exc())
        self.response.set_status(403)
        self.response.write(e.message)

class ABCreatePollHandler(ABBaseHandler):
  def post(self, *args):
    ab = self.get_ArtBattle()
    if ab:
      try:
        ab.create_poll()
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
      except tabun_api.TabunError as e:
        logging.error(traceback.format_exc())
        self.response.set_status(403)
        self.response.write(e.message)

class ABUpdateHandler(ABBaseHandler):
  def update_field(self, ab, field, is_int=True):
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
        self.update_field(ab, 'announcement_post_id', True)
        self.update_field(ab, 'battle_post_id', True)
        self.update_field(ab, 'poll_post_id', True)
        self.update_field(ab, 'result_post_id', True)
        self.update_field(ab, 'cover_art_url')
        self.update_field(ab, 'cover_art_source_url')
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
        username = self.request.get('username')
        time = datetime.strptime(self.request.get('time'), '%H:%M').time()
        art_url = self.request.get('art_url')
        ab.add_participant(username, art_url)
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
      art_url = self.request.get('art_url')
      logging.info("Reviewing participant '%s' with verdict '%s'" % (art_url, verdict))
      participant = None
      for p in ab.participants:
        if p.art_url == art_url:
          participant = p
          break
      if not participant:
        logging.warn("Participant not found for art URL '%s'" % art_url)
      else:
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
            p.time = datetime.strptime(req['time'], '%H:%M').time()
            p.user = TabunUser.get_or_insert(req['username'], parent=TabunUser.ANCESTOR_KEY).key
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
    state = ArtBattleState.get_or_insert(ArtBattleState.KEY_ID)
    if state.current_battle:
      self.redirect('/artbattle/edit?date=%s' % state.current_battle.get().date)
    else:
      self.redirect('/artbattle/edit')
  def post(self, *args):
    state = ArtBattleState.get_or_insert(ArtBattleState.KEY_ID)
    ab = self.get_ArtBattle()
    if ab:
      logging.info('Made date %s current' % ab.date)
      state.current_battle = ab.key
      state.put()


##################################### Misc #####################################
  
class HelloHandler(webapp2.RequestHandler):
  def get(self):
    self.response.write("Hi! I'm minihorse.")


app = webapp2.WSGIApplication([
  ('/', HelloHandler),
  ('/inbox', InboxHandler),
  EmailHandler.mapping(),
  ('/artbattle/create', ABCreateHandler),
  ('/artbattle/delete', ABDeleteHandler),
  ('/artbattle/edit', ABEditorHandler),
  ('/artbattle/update', ABUpdateHandler),
  ('/artbattle/announce', ABAnnounceHandler),
  ('/artbattle/set_theme', ABSetThemeHandler),
  ('/artbattle/create_poll', ABCreatePollHandler),
  ('/artbattle/count_votes', ABCountVotesHandler),
  ('/artbattle/participant/add', ABParticipantAddHandler),
  ('/artbattle/participant/review', ABParticipantReviewHandler),
  ('/artbattle/participant/edit', ABParticipantsEditHandler),
  ('/artbattle/current', ABCurrentHandler),
], debug=True)
