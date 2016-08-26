#!/usr/bin/python

import pwd
import json
import urllib
import httplib
import urllib2

_debug = False

# defaults
#default_capath  = "/etc/grid-security/certificates/"
default_certpath = "/etc/grid-security/hostcert.pem"
default_keypath  = "/etc/grid-security/hostkey.pem"

# curl example:
# curl --capath /etc/grid-security/certificates/ --cert /etc/grid-security/hostcert.pem --key /etc/grid-security/hostkey.pem 'https://fermicloud331.fnal.gov:8443/gums/json/getOsgVoUserMap?hostname=test.cs.wisc.edu'

# see: http://stackoverflow.com/questions/1875052/using-paired-certificates-with-urllib2
class HTTPSClientAuthHandler(urllib2.HTTPSHandler):
    def __init__(self, certpath, keypath):
        urllib2.HTTPSHandler.__init__(self)
        self.certpath = certpath
        self.keypath = keypath

    def https_open(self, req):
        return self.do_open(self.get_connection, req)

    # wrapper for HTTPSConnection constructor with cert files
    def get_connection(self, host, timeout=60):
        return httplib.HTTPSConnection(host, key_file=self.keypath,
                                             cert_file=self.certpath,
                                             timeout=timeout)

def certurlopen(url, certpath, keypath):
    handler = HTTPSClientAuthHandler(certpath, keypath)
    opener  = urllib2.build_opener(handler)
    return opener.open(url)

def gums_json_map(gumshost, command, params, certpath, keypath):
    params = urllib.urlencode(params)
    url = 'https://%s/gums/json/%s?%s' % (gumshost, command, jsonpath, params)
    handle = certurlopen(url, certpath, keypath)
    return json.load(handle)

def user_exists(user):
    try:
        pwd.getpwnam(user)
        return True
    except KeyError:
        return False

def supported_vos_for_vo_users(vo_users):
    def any_vo_user_exists(vo):
        return any( user_exists(user) for user in vo_users[vo] )

    return sorted(filter(any_vo_user_exists, vo_users))

def gums_json_vo_user_map(gumshost, targethost, certpath=default_certpath,
                                                keypath=default_keypath):
    json_cmd = "getOsgVoUserMap"
    params   = {'hostname': targethost}
    json_map = gums_json_map(gumshost, json_cmd, params, certpath, keypath)

    if _debug:
        print json_map

    if 'result' not in json_map:
        raise Exception("'result' not in returned json")
    if json_map['result'] != 'OK':
        raise Exception("%s: %s" % (json_map.get('result', "Fail"),
                                    json_map.get('message', "(no message)")))
    if 'map' not in json_map:
        raise Exception("Missing 'map' object")

    vo_users = json_map['map']

    if type(vo_users) is not dict:
        raise Exception("'map' object not of type dict")

    return vo_users

def gums_supported_vos(gumshost, targethost, certpath=default_certpath,
                                             keypath=default_keypath):
    vo_users = gums_json_vo_user_map(gumshost, targethost, certpath, keypath)
    return supported_vos_for_vo_users(vo_users)

