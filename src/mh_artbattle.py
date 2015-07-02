#!/usr/bin/env python
# -*- coding: utf-8 -*-

import fix_libs
import tabun_api as api

from mh_models import *

import logging

LOGIN = 'minihorse'
PASSWORD = 'tabunminihorsebot'

BLOG_ID = 40151 # Blog test539

def announce(request, *args, **kwargs):
  logging.info("Announcing battle")
  user = api.User(LOGIN, PASSWORD)
  user.add_post(BLOG_ID, u'Анонс арт-баттла', u'Текст анонса', 'test')