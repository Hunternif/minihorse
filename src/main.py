#!/usr/bin/env python
# -*- coding: utf-8 -*-

from mh_email import *
from mh_models import *
from mh_artbattle import *

import webapp2

    
class HelloHandler(webapp2.RequestHandler):
  def get(self):
    self.response.write("Hi! I'm minihorse.")


app = webapp2.WSGIApplication([
  ('/', HelloHandler),
  ('/inbox', InboxHandler),
  EmailHandler.mapping(),
  ('/artbattle/announce', announce),
  ('/artbattle/set_theme', set_theme),
  ('/artbattle/create_poll', create_poll),
  ('/artbattle/count_votes', count_votes),
], debug=True)
