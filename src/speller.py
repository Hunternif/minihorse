#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime

place_spelling_dict = {
  1: u'первое',
  2: u'второе',
  3: u'третье',
  4: u'четвертое',
  5: u'пятое',
  6: u'шестое',
  7: u'седьмое',
  8: u'восьмое',
  9: u'девятое',
  10: u'десятое',
  11: u'одинадцатое',
  12: u'двенадцатое',
  13: u'тринадцатое',
  14: u'четырнадцатое',
  15: u'пятнадцатое',
  16: u'шестнадцатое',
  17: u'семнадцатое',
  18: u'восемнадцатое',
  19: u'девятнадцатое',
  20: u'джвадцатое', # :^)
  30: u'тридцатое',
  40: u'сороковое',
  50: u'пятидесятое',
  60: u'шестидесятое',
  70: u'семидесятое',
  80: u'восьмидесятое',
  90: u'девяностое',
}
tens_spelling_dict = {
  2: u'джвадцать', # :^)
  3: u'тридцать',
  4: u'сорок',
  5: u'пятьдесят',
  6: u'шестьдесят',
  7: u'семьдесят',
  8: u'восемьдесят',
  9: u'девяносто',
}
def spell_place(place):
  """Jinja2 filter that converts numbers from 1 to 99 to words like 'Первое', 'Второе' etc."""
  try:
    place = int(place)
  except ValueError: # Not a number
    return place
  if place_spelling_dict.has_key(place):
    return place_spelling_dict[place]
  tens = place / 10
  right_digit = place % 10
  if tens_spelling_dict.has_key(tens) and place_spelling_dict.has_key(right_digit):
    return tens_spelling_dict[tens] + ' ' + place_spelling_dict[right_digit]
  else: # Unsupported number
    return place

weekday_spelling_dict = {
  0: u'понедельник',
  1: u'вторник',
  2: u'среду',
  3: u'четверг',
  4: u'пятницу',
  5: u'субботу',
  6: u'воскресенье',
}
def spell_weekday(weekday):
  """Accepts an integer from 0 to 6 and returns 'понедельник', ... 'субботу'"""
  if weekday_spelling_dict.has_key(weekday):
    return weekday_spelling_dict[weekday]
  else:
    return '???'

month_spelling_dict = {
  1: u'января',
  2: u'февраля',
  3: u'марта',
  4: u'апреля',
  5: u'мая',
  6: u'июня',
  7: u'июля',
  8: u'августа',
  9: u'сентября',
  10: u'октября',
  11: u'ноября',
  12: u'декабря',
}
def spell_month(month):
  """Accepts an integer from 1 to 12 and returns 'января' etc."""
  if month_spelling_dict.has_key(month):
    return month_spelling_dict[month]
  else:
    return str(month)

def spell_next_date(date):
  """Accepts datetime.date and formats it like this: 'субботу 4 июля'"""
  if isinstance(date, (datetime.datetime, datetime.date)):
    return spell_weekday(date.weekday()) + ' ' + str(date.day) + ' ' + spell_month(date.month)
  else:
    return str(date)
