#!/usr/bin/env python
# -*- coding: utf-8 -*-

from google.appengine.api import urlfetch

try:
  from PIL import Image
except ImportError:
  import Image

from StringIO import StringIO
from urllib import urlencode

import base64
import json

class ImgurError(Exception):
  pass

class ImgurUploader(object):
  def __init__(self):
    # 'imgur_credentials.txt' has to be a text file containing your OAuth data in JSON format:
    # {
    #    "client_id": YOUR CLIENT ID,
    #    "client_secret": YOUR CLIENT SECRET # Actually not used
    # }
    with open('imgur_credentials.txt', 'r') as f:
      credentials = json.loads(f.read())
    self.client_id = credentials['client_id']
    self.client_secret = credentials['client_secret']
  
  def upload(self, image):
    temp_str = StringIO()
    image.save(temp_str, format='JPEG', quality=95)
    b64 = base64.b64encode(temp_str.getvalue())
    temp_str.close()
    data = {
      'image': b64,
      'type': 'base64',
    }
    payload = urlencode(data)
    headers = {
      'Authorization': 'Client-ID %s' % self.client_id,
    }
    result = urlfetch.fetch(url='https://api.imgur.com/3/upload',
                   method=urlfetch.POST,
                   headers = headers,
                   payload = payload)
    if result.status_code != 200:
      raise ImgurError('Failed to upload image to Imgur: %s' % result.content)
    j = json.loads(result.content)
    return j['data']['link']
