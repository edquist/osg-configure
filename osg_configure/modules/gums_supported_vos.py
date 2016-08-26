#!/usr/bin/python

import os
import re
import pwd
import json
import urllib
import httplib
import urllib2
import optparse

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

def get_json_map(gumshost, targethost, certpath, keypath):
    jsonpath = "/gums/json/getOsgVoUserMap"
    params = urllib.urlencode({'hostname': targethost})
    url = 'https://%s%s?%s' % (gumshost, jsonpath, params)
    handle = certurlopen(url, certpath, keypath)
    return json.load(handle)

_valid_users = {}
def user_exists(user):
    if user in _valid_users:
        return _valid_users[user]
    try:
        pwd.getpwnam(user)
        valid = True
    except KeyError:
        valid = False
    _valid_users[user] = valid
    return valid

def supported_vos_for_vo_users(vo_users):
    def any_vo_user_exists(vo):
        return any( user_exists(user) for user in vo_users[vo] )

    return sorted(filter(any_vo_user_exists, vo_users))

def parse_opts():
    parser = optparse.OptionParser(usage="%prog [options] gumshost targethost")
#   parser.add_option("--capath", help="Path to certificates directory; "
#       "defaults to " + default_capath, dest="capath",
#       default=default_capath)
    parser.add_option("--cert", help="Path to user/hostcert file; "
        "defaults to " + default_certpath, dest="certpath",
        default=default_certpath)
    parser.add_option("--key", help="Path to user/hostkey file; "
        "defaults to " + default_keypath, dest="keypath",
        default=default_keypath)

    opts, args = parser.parse_args()

    if len(args) != 2:
         raise Exception("must specify gumshost and targethost")
    gumshost, targethost = args
    m = re.search(r'^(?:https://)?([^:]+)(?::(\d+))?$', gumshost)
    if m is None:
        raise Exception("Bad gums host: '%s'" % gumshost)
    host, port = m.groups()
    gumshost = "%s:%s" % (host, (port or 8443))
    opts = dict(vars(opts), gumshost=gumshost, targethost=targethost)
    return opts

def get_json_vo_user_map(gumshost, targethost, certpath=default_certpath,
                                               keypath=default_keypath):
    json_map = get_json_map(gumshost, targethost, certpath, keypath)

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

def get_supported_vos(gumshost, targethost, certpath=default_certpath,
                                            keypath=default_keypath):
    vo_users = get_json_vo_user_map(gumshost, targethost, certpath, keypath)
    return supported_vos_for_vo_users(vo_users)

def main():
    opts = parse_opts()

    supported_vos = get_supported_vos(**opts)
    if supported_vos:
        print "Supported VOs on this server:"
        for vo in supported_vos:
            print "  " + vo
    else:
        print "No supported VOs on this server."

if __name__ == '__main__':
    main()

