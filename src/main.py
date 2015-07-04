#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime, tzinfo, timedelta

from google.appengine.api.mail import InboundEmailMessage
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
from google.appengine.ext import ndb

import jinja2
import logging
import os
import random
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

class TabunUser(ndb.Model):
  name = ndb.StringProperty()

class Participant(ndb.Model):
  number = ndb.IntegerProperty() # assigned via random shuffle before creating a poll
  user = ndb.KeyProperty(kind='TabunUser')
  art_url = ndb.StringProperty()
  art_preview_url = ndb.StringProperty()
  time = ndb.TimeProperty(auto_now_add=True) # UTC time of submitting artwork
  votes = ndb.IntegerProperty()
  original_email = ndb.KeyProperty(kind='Email') # will be None for manually added participants
  approved = ndb.BooleanProperty()

class ArtBattle(ndb.Model):
  PHASE_UPCOMING = 0
  PHASE_ANNOUNCED = 1
  PHASE_PREPARED = 2
  PHASE_BATTLE_ON = 3
  PHASE_APPROVAL = 4 # May be skipped if all artworks are approved by the end of the battle
  PHASE_VOTING = 5
  PHASE_FINISHED = 6
  phase = ndb.IntegerProperty(default=PHASE_UPCOMING)
  
  date = ndb.DateProperty() # No two Art-Battles may have the same date!
  theme = ndb.StringProperty()
  participants = ndb.StructuredProperty(Participant, repeated=True)
  
  cover_art_url = ndb.StringProperty()
  cover_art_author = ndb.KeyProperty(kind='TabunUser') # used if cover art is custom-made by a user
  cover_art_source_url = ndb.StringProperty() # used if cover art is a placeholder
  
  announcement_post_id = ndb.StringProperty() # the pre-announcement a couple of days before
  battle_post_id = ndb.StringProperty() # the post in which the theme is revealed
  poll_post_id = ndb.StringProperty()
  result_post_id = ndb.StringProperty()

  ANCESTOR_KEY = ndb.Key('ArtBattle', 'Art-Battles')
  
  def announce(self):
    """Creates a post announcing the upcoming Art-Battle. Not used if the artist decides to post to 'ЯРОК'"""
    logging.info("Announcing Art-Battle %s" % self.date)
    user = get_admin()
    # TODO: pre-announcement text
    text = u'Текст объявления Арт-Баттла'
    ret = user.add_post(BLOG_ID, u'Объявление Арт-Баттла %s' % self.date, text, u'Арт-Баттл, объявление, конкурс, %s' % self.date)
    self.announcement_post_id = ret[1]
    self.phase = PHASE_ANNOUNCED
    self.put()
    # TODO: handle exceptions
  
  def prepare(self):
    """Creates a post for date's Art-Battle. This post will be later updated with the theme."""
    logging.info("Preparing Art-Battle %s" % self.date)
    user = get_admin()
    # TODO: announcement text
    text = u'Текст Арт-Баттла без темы'
    ret = user.add_post(BLOG_ID, u'Арт-Баттл %s' % self.date, text, u'Арт-Баттл, конкурс, %s' % self.date)
    self.battle_post_id = ret[1]
    self.phase = PHASE_PREPARED
    self.put()

  def set_theme(self, theme):
    """Sets the theme and begins Art-Battle."""
    logging.info("Setting Art-Battle theme: %s. Art-Battle begins!" % theme)
    user = get_admin()
    # TODO: announcement text + theme
    text = u'Текст Арт-Баттла с темой'
    user.edit_post(self.battle_post_id, BLOG_ID, u'Арт-Баттл %s' % self.date, text, u'Арт-Баттл, конкурс, %s' % self.date)
    self.phase = PHASE_BATTLE_ON
    self.put()

  def create_poll(self):
    """Ends Art-Battle and starts a poll to find the winner."""
    logging.info("Creating poll for Art-Battle %s" % self.date)
    user = get_admin()
    # TODO: voting text
    text = u'Текст голосования'
    choices = []
    # Shuffle participants' numbers:
    i = 1
    for p in random.sample(self.participants, len(self.participants)):
      p.number = i
      i += 1
      choices.append(u'Участник %d\n<img src="%s"/>' % i, p.art_preview_url)
    ret = user.add_poll(BLOG_ID, u'Голосование за Арт-Баттл %s' % self.date, choices, text, u'Арт-Баттл, голосвание, %s' % self.date)
    self.poll_post_id = ret[1]
    # TODO check if artworks need approval and then proceed to either PHASE_APPROVAL or PHASE_VOTING
    self.phase = PHASE_VOTING
    self.put()

  def count_votes(self):
    """Ends voting and creates a post with results."""
    logging.info("Ending and counting votes for Art-Battle %s" % self.date)
    user = get_admin()
    post = user.get_post(self.poll_post_id)
    for i in range(len(post.poll.items)):
      self.participants[i].votes = post.poll.items[i][2]
    # TODO: voting result text
    text = u'Текст результата'
    ret = user.add_post(BLOG_ID, u'Итоги голосования за Арт-Баттл %s' % self.date, text, u'Арт-Баттл, итоги голосования, %s' % self.date)
    self.result_post_id = ret[1]
    # TODO: send message to winner(s)
    self.phase = PHASE_FINISHED
    self.put()
  
  def add_participant(self, username, art_url, original_email=None):
    """Add a participant to this Art-Battle and format their artwork."""
    user = TabunUser.get_or_insert(id=username)
    # TODO: resize image and upload to imgur.com (if needed)
    p = Participant(user=user, art_url=art_url, original_email=original_email)
    # Assuming an imgur.com URL, the preview URL is "....s.jpg/png"
    p.art_preview_url = art_url[:-4] + 's' + art_url[-4:]
    self.participants.append(p)
    self.put()

class ArtBattleState(ndb.Model):
  current_battle = ndb.KeyProperty(kind='ArtBattle')


#################################### Editor ####################################

class ABCreateHandler(webapp2.RequestHandler):
  def post(self, *args):
    param_date = self.request.get('date')
    try:
      date = datetime.strptime(param_date, '%Y-%m-%d').date()
      if ArtBattle.query(ArtBattle.date==date, ancestor=ArtBattle.ANCESTOR_KEY).get():
        logging.warn("Art-Battle already exists at date '%s'" % date)
      else:
        ArtBattle(parent=ArtBattle.ANCESTOR_KEY, date=date).put()
        logging.info("Created Art-Battle on '%s'" % date)
    except ValueError:
      logging.warn("Couldn't parse date '%s'" % param_date)
    self.redirect('/artbattle-edit?date=%s' % param_date)

class ABEditorHandler(webapp2.RequestHandler):
  def get(self, *args):
    template = JINJA_ENVIRONMENT.get_template('art-battle-edit.html')
    template_values = {}
    # Read list of dates:
    dates = ArtBattle.query(ancestor=ArtBattle.ANCESTOR_KEY).order(ArtBattle.date).fetch(projection=ArtBattle.date)
    template_values['dates'] = dates
    # Read request date:
    param_date = self.request.get('date')
    try:
      date = datetime.strptime(param_date, '%Y-%m-%d').date()
      ab = ArtBattle.query(ArtBattle.date==date, ancestor=ArtBattle.ANCESTOR_KEY).get()
      if ab:
        template_values['date'] = date
        template_values['artbattle'] = ab
      else:
        logging.warn('No Art-Battle found for date %s' % date)
    except ValueError:
      logging.warn("Couldn't parse date '%s'" % param_date)
    self.response.write(template.render(template_values))


##################################### Misc #####################################
  
class HelloHandler(webapp2.RequestHandler):
  def get(self):
    self.response.write("Hi! I'm minihorse.")


app = webapp2.WSGIApplication([
  ('/', HelloHandler),
  ('/inbox', InboxHandler),
  EmailHandler.mapping(),
  ('/artbattle-create', ABCreateHandler),
  ('/artbattle-edit', ABEditorHandler),
  # ('/artbattle/announce', announce),
  # ('/artbattle/set_theme', set_theme),
  # ('/artbattle/create_poll', create_poll),
  # ('/artbattle/count_votes', count_votes),
], debug=True)
