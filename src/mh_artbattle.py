#!/usr/bin/env python
# -*- coding: utf-8 -*-

import fix_libs
import tabun_api as api

from mh_models import *

import logging

LOGIN = 'minihorse'
PASSWORD = 'tabunminihorsebot'

BLOG_ID = 40151 # Blog test539
POST_ID = 134954 # Test post #2

def get_user():
  return api.User(LOGIN, PASSWORD)

def announce(*args, **kwargs):
  logging.info("Announcing battle")
  user = get_user()
  user.add_post(BLOG_ID, u'Анонс арт-баттла', u'Текст анонса', 'test')

def set_theme(*args, **kwargs):
  logging.info("Setting theme")
  user = get_user()
  user.edit_post(POST_ID, BLOG_ID, u'Обновленный анонс арт-баттла', u'Обновленный текст анонса!', 'test, test2')
