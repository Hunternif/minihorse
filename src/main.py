#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from datetime import datetime, tzinfo, timedelta

from google.appengine.api.mail import InboundEmailMessage
from google.appengine.ext import ndb
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler

import logging
import webapp2


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

#=================================== Email =====================================
class DBMail(ndb.Model):
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
    inbox = DBMail.query().order(-DBMail.time).fetch()
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
    msg_db = DBMail(parent = ndb.Key("Mail", "Inbox"),
                    subject = msg.subject,
                    sender = msg.sender,
                    to = msg.to,
                    body_html = body[1].decode(),
                    read = False)
    msg_db.put()

    
#================================ Art Battle ===================================
class ArtBattlePhase:
  idle = 0
  battle_on = 1
  vote_in_progress = 2

class ArtBattleInfo(ndb.Model):
  phase = ndb.IntegerProperty() # See ArtBattlePhase
  week = ndb.IntegerProperty() # Every odd week the wednesday battle is skipped

    
class HelloHandler(webapp2.RequestHandler):
  def get(self):
    self.response.write("Hi! I'm minihorse.")


app = webapp2.WSGIApplication([
  ('/', HelloHandler),
  ('/inbox', InboxHandler),
  EmailHandler.mapping()
], debug=True)
