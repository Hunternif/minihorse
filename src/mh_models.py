#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import tzinfo, timedelta

from google.appengine.ext import ndb


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


class TabunUser(ndb.Model):
  name = ndb.StringProperty()

class Participant(ndb.Model):
  number = ndb.IntegerProperty()
  user = ndb.KeyProperty(kind='TabunUser')
  art_url = ndb.StringProperty()
  art_preview_url = ndb.StringProperty()
  votes = ndb.IntegerProperty()
  original_email = ndb.KeyProperty(kind='Email') # will be None for manually added participants
  qualified = ndb.BooleanProperty()

class ArtBattle(ndb.Model):
  date = ndb.DateProperty() # No two Art-Battles may have the same date
  organizer = ndb.KeyProperty(kind='TabunUser')
  theme = ndb.StringProperty()
  participants = ndb.StructuredProperty(Participant, repeated=True)
  announcement_post_id = ndb.StringProperty()
  cover_art_url = ndb.StringProperty()
  cover_art_author = ndb.KeyProperty(kind='TabunUser') # used if cover art is custom-made by a user
  cover_art_source_url = ndb.StringProperty() # used if cover art is a placeholder
  poll_post_id = ndb.StringProperty()
  result_post_id = ndb.StringProperty()


class ArtBattleState(ndb.Model):
  # Phases:
  # 0 - Idle (results posted, awaiting announcement)
  # 1 - Pre-start (announcement made)
  # 2 - Battle on
  # 3 - Vote in progress
  phase = ndb.IntegerProperty()
  current_battle = ndb.KeyProperty(kind='ArtBattle')
  
