#!/usr/bin/env python
# -*- coding: utf-8 -*-

from mh_models import Email

from google.appengine.api.mail import InboundEmailMessage
from google.appengine.ext import ndb
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler

import logging
import webapp2


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
