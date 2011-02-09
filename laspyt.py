#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from optparse import OptionParser
from configparser import RawConfigParser
from http.client import HTTPConnection
from xml.etree import ElementTree
from os.path import expanduser
from hashlib import md5
from urllib.parse import urlencode

API_KEY = 'f93b732314fb490801795e8f4062c205'
API_SECRET = '7f3f480915d7fcb1d11e42bc2ea71da4'
AUDIOSCROBBLER_LINE = "#AUDIOSCROBBLER/1.1\n"
CONFIG_FILE = expanduser('~/.laspyt.cfg')
OK_MSG = '\033[92m[OK] \033[0m'
FAIL_MSG = '\033[91m[FAIL] \033[0m'
OPTIONS = None
CONFIG = None
FILE = None
TIMEDELAY = 0

def loadOptions():
  global OPTIONS
  p = OptionParser()
  p.add_option('--file', '-f', help='path to scrobbler.log', metavar='FILE', default=CONFIG.get('DEFAULT', 'file'))
  p.add_option('--user', '-u', help='last.fm login', default=CONFIG.get('DEFAULT', 'user'))
  p.add_option('--password', '-p', help='last.fm password', default='')
  p.add_option('--timezone', '-t', help='timezone: 0 (for UTC+0) +5 (for UTC+5), -3 (for UTC-3)', default=CONFIG.get('DEFAULT', 'timezone'))
  p.add_option('--clear', '-c', help='clear scrobbler.log after scrobbling without asking', dest="clearing", action="store_const", const="y")
  p.add_option('--leave', '-l', help='don\'t clear scrobbler.log after scrobbling without asking', dest="clearing", action="store_const", const="n")
  p.add_option('--save', '-s', help='save current options as default, but doesn\'t make scrobbling', action="store_true", default=False)
  OPTIONS, args = p.parse_args()
  if OPTIONS.password:
    OPTIONS.password = md5(OPTIONS.password.encode('utf-8')).hexdigest()
  else:
    OPTIONS.password = CONFIG.get('DEFAULT', 'password')
  OPTIONS.timezone = int(OPTIONS.timezone)
  if (OPTIONS.timezone > 14 or OPTIONS.timezone < -12):
    if (OPTIONS.timezone >= 0):
      opts.timezone = "+"+str(OPTIONS.timezone)
      print("Non-existent timezone UTC%s" % OPTIONS.timezone)
      quit()

def loadConfig():
  global CONFIG
  CONFIG = RawConfigParser()
  CONFIG.read(CONFIG_FILE)
  if not CONFIG.has_option('DEFAULT', 'file'):
    CONFIG.set('DEFAULT', 'file', '.scrobbler.log')
  if not CONFIG.has_option('DEFAULT', 'user'):
    CONFIG.set('DEFAULT', 'user', '')
  if not CONFIG.has_option('DEFAULT', 'password'):
    CONFIG.set('DEFAULT', 'password', '')
  if not CONFIG.has_option('DEFAULT', 'timezone'):
    CONFIG.set('DEFAULT', 'timezone', '0')

def saveConfig():
  global CONFIG
  if OPTIONS.save:
    CONFIG.set('DEFAULT', 'file', OPTIONS.file)
    CONFIG.set('DEFAULT', 'user', OPTIONS.user)
    CONFIG.set('DEFAULT', 'password', OPTIONS.password)
    CONFIG.set('DEFAULT', 'timezone', OPTIONS.timezone)
    with open(CONFIG_FILE, 'w') as configfile:
      CONFIG.write(configfile)
      print("Configuration file was updated")
      quit()

def openLog():
  global FILE, TZ_LINE, CLIENT_LINE
  try:
    FILE = open(OPTIONS.file, "r")
  except IOError:
    print("Can't open file %s" % OPTIONS.file)
    quit()
  if (FILE.readline() != AUDIOSCROBBLER_LINE):
    print("Unknown scrobbler.log format")
    FILE.close()
    quit()
  TZ_LINE = FILE.readline()
  if (TZ_LINE == "#TZ/UTC\n"):
    OPTIONS.timezone = 0
  CLIENT_LINE = FILE.readline()
  
def readLog():
  global FILE, TIMEDELAY
  TIMEDELAY = -3600*OPTIONS.timezone
  oks = 0
  fails = 0
  conn = HTTPConnection("ws.audioscrobbler.com")
  print("Scrobbling started")
  for line in FILE:
    track = line.split("\t")
    error = submitTrack(track)
    track = "%s - %s" % (track[0], track[2])
    if (error):
      fails+=1
      print(FAIL_MSG + "%s - %s" % (track, error))
    else:
      oks+=1
      print(OK_MSG + "%s" % (track))
  FILE.close()
  print("%i tracks submitted.\n%i failed submissions." % (oks, fails))

def clearLog():
  global FILE
  try:
    FILE = open(OPTIONS.file, "w")
    FILE.write(AUDIOSCROBBLER_LINE)
    FILE.write(TZ_LINE)
    FILE.write(CLIENT_LINE)
    FILE.close()
    print("File %s cleared" % OPTIONS.file)
  except IOError:
    print("Can't clear file %s" % OPTIONS.file)

def makeQueryBody(params):
  params['api_key'] = API_KEY
  api_sig = ''
  q = {}
  for key in sorted(params):
    api_sig += key + params[key]
    q[key] = params[key]
  api_sig += API_SECRET
  api_sig = md5(api_sig.encode('utf-8')).hexdigest()
  q['api_sig'] = api_sig
  q = urlencode(q)
  return q

def createSession():
  global SESSION_KEY
  token = md5((OPTIONS.user + OPTIONS.password).encode('utf-8')).hexdigest()
  conn = HTTPConnection("ws.audioscrobbler.com")
  conn.request("GET", "/2.0/?%s" % makeQueryBody({'authToken': token, 'method': 'auth.getMobileSession', 'username': OPTIONS.user}))
  response = conn.getresponse()
  conn.close()
  if (response.status != 200 and response.status != 403):
    print("Can't connect to last.fm")
    FILE.close()
    quit()
  data = ElementTree.fromstring(response.read())
  if (data.attrib['status'] != "ok"):
    print("Last.fm error: %s" % data.find("error").text)
    FILE.close()
    quit()
  SESSION_KEY = data.find("session").find("key").text
  
def submitTrack(track):
  error = False
  if (track[5] == "L"):
    conn = HTTPConnection("ws.audioscrobbler.com")
    body = makeQueryBody({'track[0]': track[2], 'timestamp[0]': str(int(track[6])+TIMEDELAY), 'artist[0]': track[0], 'album[0]': track[1], 'trackNumber[0]': track[3], 'duration[0]': track[4], 'sk': SESSION_KEY, 'method': 'track.scrobble'})
    conn.request("POST", "/2.0/", body, {"Content-type": "application/x-www-form-urlencoded"})
    response =  conn.getresponse()
    conn.close()
    if (response.status != 200):
      error = "%s error" % response.status
    else:
      data = ElementTree.fromstring(response.read())
      if (data.attrib['status'] != "ok"):
        error = data.find("error").text
      else:
        data = data.find("scrobbles").find("scrobble").find("ignoredMessage")
        if (data.attrib['code'] != 0):
          error = data.text
  return error
      
loadConfig()
loadOptions()
saveConfig()
openLog()
createSession()
readLog()

clearing = OPTIONS.clearing
while (clearing != "y" and clearing != "n"):
  clearing = input("Clear scrobbler.log? [y/n]: ")
if (clearing == "y"):
  clearLog()