#!/usr/bin/env python

from mh_email import *
from mh_models import *

import webapp2

    
class HelloHandler(webapp2.RequestHandler):
  def get(self):
    self.response.write("Hi! I'm minihorse.")


app = webapp2.WSGIApplication([
  ('/', HelloHandler),
  ('/inbox', InboxHandler),
  EmailHandler.mapping(),
], debug=True)
