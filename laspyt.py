#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from optparse import OptionParser
from configparser import RawConfigParser
from os.path import expanduser
from time import time
from hashlib import md5
from http.client import HTTPConnection
from urllib.parse import urlencode
from urllib.parse import urlparse
from xml.etree import ElementTree

#Base constants----------------------------------------
APP_NAME = 'pyt'
APP_VERSION = '1.1'
API_KEY = 'f93b732314fb490801795e8f4062c205'
API_SECRET = '7f3f480915d7fcb1d11e42bc2ea71da4'
AUDIOSCROBBLER_LINE = "#AUDIOSCROBBLER/1.1\n"
CONFIG = expanduser('~/.laspyt.cfg')
OK_MSG = '\033[92m[OK] \033[0m'
FAIL_MSG = '\033[91m[FAIL] \033[0m'
#------------------------------------------------------

#Read configuration------------------------------------
config = RawConfigParser()
config.read(CONFIG)
if not config.has_option('DEFAULT', 'file'):
  config.set('DEFAULT', 'file', '.scrobbler.log')
if not config.has_option('DEFAULT', 'user'):
  config.set('DEFAULT', 'user', '')
if not config.has_option('DEFAULT', 'password'):
  config.set('DEFAULT', 'password', '')
if not config.has_option('DEFAULT', 'timezone'):
  config.set('DEFAULT', 'timezone', '0')
#------------------------------------------------------

#CLI---------------------------------------------------
p = OptionParser()
p.add_option('--file', '-f', help='path to scrobbler.log', metavar='FILE', default=config.get('DEFAULT', 'file'))
p.add_option('--user', '-u', help='last.fm login', default=config.get('DEFAULT', 'user'))
p.add_option('--password', '-p', help='last.fm password', default='')
p.add_option('--timezone', '-t', help='timezone: 0 (for UTC+0) +5 (for UTC+5), -3 (for UTC-3)', default=config.get('DEFAULT', 'timezone'))
p.add_option('--clear', '-c', help='clear scrobbler.log after scrobbling without asking', dest="clearing", action="store_const", const="y")
p.add_option('--leave', '-l', help='don\'t clear scrobbler.log after scrobbling without asking', dest="clearing", action="store_const", const="n")
p.add_option('--save', '-s', help='save current options as default, but doesn\'t make scrobbling', action="store_true", default=False)
opts, args = p.parse_args()
clearing = opts.clearing
if opts.password:
  opts.password = md5(opts.password.encode('utf-8')).hexdigest()
else:
  opts.password = config.get('DEFAULT', 'password')
opts.timezone = int(opts.timezone)
if (opts.timezone > 14 or opts.timezone < -12):
  if (opts.timezone >= 0):
    opts.timezone = "+"+str(opts.timezone)
    print("Non-existent timezone UTC%s" % opts.timezone)
    quit()
#------------------------------------------------------

#Save configuration------------------------------------
if opts.save:
  config.set('DEFAULT', 'file', opts.file)
  config.set('DEFAULT', 'user', opts.user)
  config.set('DEFAULT', 'password', opts.password)
  config.set('DEFAULT', 'timezone', opts.timezone)
  with open(CONFIG, 'w') as configfile:
    config.write(configfile)
    print("Configuration file was updated")
    quit()
#------------------------------------------------------

#Parsing log's header----------------------------------
try:
  fl = open(opts.file, "r")
except IOError:
  print("Can't open file %s" % opts.file)
  quit()
if (fl.readline() != AUDIOSCROBBLER_LINE):
  print("Unknown scrobbler.log format")
  fl.close()
  quit()
TZ_LINE = fl.readline()
if (TZ_LINE == "#TZ/UTC\n"):
  opts.timezone = 0
CLIENT_LINE = fl.readline()
#------------------------------------------------------

def query(params):
  params['api_key'] = API_KEY
  api_sig = ""
  q = {}
  for key in sorted(params):
    api_sig += key + params[key]
    q[key] = params[key]
  api_sig += API_SECRET
  api_sig = md5(api_sig.encode('utf-8')).hexdigest()
  q['api_sig'] = api_sig
  q = urlencode(q)
  return q

#Create session----------------------------------------
token = md5((opts.user + opts.password).encode('utf-8')).hexdigest()
conn = HTTPConnection("ws.audioscrobbler.com")
conn.request("GET", "/2.0/?%s" % query({'authToken': token, 'method': 'auth.getMobileSession', 'username': opts.user}))
response = conn.getresponse()
conn.close()
if (response.status != 200 and response.status != 403):
  print("Can't connect to last.fm")
  fl.close()
  quit()
data = ElementTree.fromstring(response.read())
if (data.attrib['status'] != "ok"):
  print("Last.fm error: %s" % data.find("error").text)
  fl.close()
  quit()
SESSION_KEY = data.find("session").find("key").text
##------------------------------------------------------

#Scrobbling--------------------------------------------
timedelay = -3600*opts.timezone
oks = 0
fails = 0
conn = HTTPConnection("ws.audioscrobbler.com")
print("Scrobbling started")
for line in fl:
  track = line.split("\t")
  if (track[5] == "L"):
    #({'s': SESSION_ID, 'a[0]': data[0], 't[0]': data[2], 'i[0]': int(data[6])+timedelay, 'o[0]': 'P', 'r[0]': '', 'l[0]': data[4], 'b[0]': data[1], 'n[0]': data[3], 'm[0]': data[7]})
    body = query({'track[0]': track[2], 'timestamp[0]': str(int(track[6])+timedelay), 'artist[0]': track[0], 'album[0]': track[1], 'trackNumber[0]': track[3], 'duration[0]': track[4], 'sk': SESSION_KEY, 'method': 'track.scrobble'})
    conn.request("POST", "/2.0/", body, {"Content-type": "application/x-www-form-urlencoded"})
    response =  conn.getresponse()
    conn.close()
    error = False
    if (response.status != 200):
      error = "% error" % response.status
    else:
      data = ElementTree.fromstring(response.read())
      if (data.attrib['status'] != "ok"):
        error = data.find("error").text
      else:
        data = data.find("scrobbles").find("scrobble").find("ignoredMessage")
        if (data.attrib['code'] != 0):
          error = data.text
    track = "%s - %s" % (track[0], track[2])
    if (error):
      fails+=1
      print(FAIL_MSG+"%s - %s" % (track, error))
    else:
      oks+=1
      print(OK_MSG+"%s" % (track))
fl.close()
print("%i tracks submitted.\n%i failed submissions." % (oks, fails))
#------------------------------------------------------

#Log clearing------------------------------------------
while (clearing != "y" and clearing != "n"):
  clearing = input("Clear scrobbler.log? [y/n]: ")
if (clearing == "y"):
  try:
    fl = open(opts.file, "w")
    fl.write(AUDIOSCROBBLER_LINE)
    fl.write(TZ_LINE)
    fl.write(CLIENT_LINE)
    fl.close()
    print("File %s cleared" % opts.file)
  except IOError:
    print("Can't clear file %s" % opts.file)
#------------------------------------------------------
