#!/usr/bin/env python

import sys
import Router.Logger as Logger
import KSR as KSR
import httplib2
import json
import configparser
import os
import sqlite3
import datetime

congiFile = "/etc/sipmediagw.cfg"

class RequestGw:
    def __init__(self):
        Logger.LM_ERR('RequestGw.__init__\n')
        self.config = configparser.ConfigParser()
        self.config.read(congiFile)
        sipSecret=self.config['sip']['sipSecret'].replace('"',"").replace("'", "")
        self.serverAddr=self.config['sip']['sipSrv'].replace('"',"").replace("'", "")
        self.gwNamePart = self.config['mediagw']['sipUaNamePart'].replace('"',"").replace("'", "")
        KSR.pv.sets("$var(secret)", sipSecret)
        self.con = sqlite3.connect('/usr/local/etc/kamailio/kamailio.sqlite')

    def child_init(self, y):
        Logger.LM_ERR('RequestGwchild_init(%d)\n' % y)
        return 0

    def lockGw (self):
        res=''
        with self.con as con:
            cursor = con.cursor()
            cursor.execute('''SELECT contact, username FROM location
                              WHERE
                                  locked = 0 AND
                                  username LIKE '%'||?||'%' AND
                                  NOT EXISTS (
                                     SELECT callee_contact
                                     FROM dialog
                                     WHERE callee_contact LIKE '%'||location.contact||'%'
                                  );''',(self.gwNamePart,))
            contactList = cursor.fetchall()
            if len(contactList) == 0:
                return
            for contact in contactList:
                cursor.execute('''UPDATE location SET locked = 1
                                  WHERE
                                      location.contact = ? AND
                                      locked = 0 AND
                                      NOT EXISTS (
                                         SELECT callee_contact
                                         FROM dialog
                                         WHERE callee_contact LIKE '%'||?||'%'
                                      );''',(contact[0], contact[0],))
                res = con.commit()
                if cursor.rowcount > 0:
                    return contact
        return

    def handler(self, msg, args):
        Logger.LM_ERR("Loggers.py:      LM_ERR: msg: %s" % str(args))
        Logger.LM_ERR('RequestGw.handler(%s, %s)\n' % (msg.Type, str(args)))
        if msg.Type == 'SIP_REQUEST':
            if msg.Method == 'INVITE' and (msg.RURI).find(self.gwNamePart) == -1:
                Logger.LM_ERR('SIP request, method = %s, RURI = %s, From = %s\n' % (msg.Method, msg.RURI, msg.getHeader('from')))
                uri = msg.RURI
                room = (uri.split("sip:")[1]).split('@')[0]
                displayName = (msg.getHeader('from').split('<')[0])
                fromUri = (msg.getHeader('from').split('<')[1]).split('>')[0]
                Logger.LM_ERR('Room Name %s\n' % room )
                gwRes = self.lockGw()
                if gwRes:
                    gwUri = gwRes[1]
                    Logger.LM_ERR('Returned Gateway: %s\n' % gwUri)
                    msg.rewrite_ruri("sip:%s@%s" % (gwUri, self.serverAddr))
                    displayNameWRoom = '"%s-%s%s"' % (str(len(room)), room, displayName.replace('"',''))
                    KSR.uac.uac_replace_from(displayNameWRoom, "")
                    Logger.LM_ERR('########## SIP request, method = %s, RURI = %s, From = %s\n' % (msg.Method, msg.RURI, msg.getHeader('from')))

        return 1

def mod_init():
    return RequestGw()
