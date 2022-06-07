#!/usr/bin/env python

import sys
#from Router import LM_ERR
import Router.Logger as Logger
import KSR as KSR
import httplib2
import json
import configparser
import os

congiFile = "/etc/sipmediagw.cfg"

class RequestGw:
    def __init__(self):
        Logger.LM_ERR('RequestGw.__init__\n')
        self.config = configparser.ConfigParser()
        self.config.read(congiFile)
        sipSecret=self.config['sip']['sipSecret'].replace('"',"").replace("'", "")
        KSR.pv.sets("$var(secret)", sipSecret)

    def child_init(self, y):
        Logger.LM_ERR('RequestGwchild_init(%d)\n' % y)
        return 0

    def handler(self, msg, args):
        Logger.LM_ERR("Loggers.py:      LM_ERR: msg: %s" % str(args))
        Logger.LM_ERR('RequestGw.handler(%s, %s)\n' % (msg.Type, str(args)))
        launcherAPIPath = self.config['mediagw']['launcherAPIPath'].replace('"',"").replace("'", "")
        if msg.Type == 'SIP_REQUEST':
            if msg.Method == 'INVITE' and (msg.RURI).find(self.config['mediagw']['sipUaNamePart']) == -1:
                Logger.LM_ERR('SIP request, method = %s, RURI = %s, From = %s\n' % (msg.Method, msg.RURI, msg.getHeader('from')))
                uri = msg.RURI
                room = (uri.split("sip:")[1]).split('@')[0]
                fromUri = (msg.getHeader('from').split('<')[1]).split('>')[0]
                Logger.LM_ERR('Room Name %s\n' % room )
                http = httplib2.Http(disable_ssl_certificate_validation=True)
                reqUrl = launcherAPIPath
                uaNamePrefix = (fromUri.split(':')[1]).replace(".", "").replace("@","")
                reqUrl = ("%s?room=%s&from=%s&prefix=%s" %(launcherAPIPath, room, fromUri, uaNamePrefix))
                Logger.LM_ERR('Launcher URL %s\n' % reqUrl )
                try:
                    content = http.request(reqUrl)
                except:
                    content = []

                if len(content) != 0 and content[0]['status']=="200":
                    launchRes=json.loads(content[1].decode("utf-8"))
                    if launchRes['res'] == 'ok':
                        gwUri = launchRes['uri']#.split('<')[1]).split('>')[0]
                        Logger.LM_ERR('Returned Gateway: %s\n' % gwUri)
                        msg.rewrite_ruri(gwUri)
                        Logger.LM_ERR('########## SIP request, method = %s, RURI = %s, From = %s\n' % (msg.Method, msg.RURI, msg.getHeader('from')))

        return 1

def mod_init():
    return RequestGw()
