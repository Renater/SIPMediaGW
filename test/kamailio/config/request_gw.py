#!/usr/bin/env python3

import sys
import Router.Logger as Logger
import KSR as KSR
import httplib2
import json
import configparser
import os
import mysql.connector as mysqlcon
import datetime
from contextlib import closing
from configparser import ConfigParser

parser = ConfigParser()
parser.optionxform = str
with open("/etc/kamailio/kamctlrc") as stream:
    parser.read_string("[kamctlrc]\n" + stream.read())
kamctlrc = dict(parser.items("kamctlrc"))


class RequestGw:
    def __init__(self):
        Logger.LM_ERR('RequestGw.__init__\n')
        sipSecret=os.environ.get('SIP_SECRET').replace('"',"").replace("'", "")
        self.sipDomain=os.environ.get('SIP_DOMAIN').replace('"',"").replace("'", "")
        self.publicIP=os.environ.get('PUBLIC_IP').replace('"',"").replace("'", "")
        self.gwNamePart = os.environ.get('GW_NAME_PREFIX').replace('"',"").replace("'", "")
        KSR.pv.sets("$var(secret)", sipSecret)

    def child_init(self, y):
        Logger.LM_ERR('RequestGwchild_init(%d)\n' % y)
        return 0

    def lockGw (self):
        res=''
        with closing(mysqlcon.connect(host=kamctlrc['DBHOST'],
                                      user=kamctlrc['DBRWUSER'],
                                      password=kamctlrc['DBRWPW'],
                                      database=kamctlrc['DBNAME'])) as con:
            with closing(con.cursor()) as cursor:
                cursor.execute('''SELECT contact, username, socket,
                                         SUBSTRING_INDEX(SUBSTRING_INDEX(received,'sip:',-1),':',1) AS vm,
                                         COUNT(username) as count FROM location
                                  WHERE
                                      locked = 0 AND
                                      username LIKE CONCAT('%',%s,'%') AND
                                      EXISTS (
                                          SELECT  callee_contact
                                          FROM dialog
                                          WHERE SUBSTRING_INDEX(SUBSTRING_INDEX(callee_contact,'alias=',-1),'~',1) =
                                                SUBSTRING_INDEX(SUBSTRING_INDEX(location.received,'sip:',-1),':',1)
                                      )
                                  GROUP BY vm
                                  ORDER BY count ASC;''',(self.gwNamePart,))
                contactList = cursor.fetchall()
                if len(contactList) == 0:
                    cursor.execute('''SELECT contact, username, socket,
                                            SUBSTRING_INDEX(SUBSTRING_INDEX(received,'sip:',-1),':',1) AS vm,
                                            COUNT(username) as count FROM location
                                    WHERE
                                        locked = 0 AND
                                        username LIKE CONCAT('%',%s,'%') AND
                                        NOT EXISTS (
                                            SELECT  callee_contact
                                            FROM dialog
                                            WHERE SUBSTRING_INDEX(SUBSTRING_INDEX(callee_contact,'alias=',-1),'~',1) =
                                                    SUBSTRING_INDEX(SUBSTRING_INDEX(location.received,'sip:',-1),':',1)
                                        )
                                    GROUP BY vm
                                    ORDER BY count ASC;''',(self.gwNamePart,))
                    contactList = cursor.fetchall()
                    if len(contactList) == 0:
                        return
                for contact in contactList:
                    cursor.execute('''UPDATE location SET locked = 1
                                      WHERE
                                          location.contact = %s AND
                                          locked = 0 AND
                                          NOT EXISTS (
                                             SELECT callee_contact
                                             FROM dialog
                                             WHERE callee_contact LIKE CONCAT('%',%s,'%')
                                          );''',(contact[0], contact[1],))
                    res = con.commit()
                    if cursor.rowcount > 0:
                        return contact
        return

    def handler(self, msg, args):
        Logger.LM_ERR("Loggers.py:      LM_ERR: msg: %s" % str(args))
        Logger.LM_ERR('RequestGw.handler(%s, %s)\n' % (msg.Type, str(args)))
        if (msg.Type == 'SIP_REQUEST' and
            ((msg.RURI).find(self.sipDomain) != -1 or
             (msg.RURI).find(self.publicIP) != -1)):
            if msg.Method == 'INVITE' and (msg.RURI).find(self.gwNamePart) == -1:
                Logger.LM_ERR('SIP request, method = %s, RURI = %s, From = %s\n' % (msg.Method, msg.RURI, msg.getHeader('from')))
                uri = msg.RURI
                room = (uri.split(":", 1)[1]).split('@')[0]
                displayName = ""
                if "<" in msg.getHeader('from'):
                    displayName = (msg.getHeader('from').split('<')[0])
                Logger.LM_ERR('Room Name %s\n' % room )
                gwRes = self.lockGw()
                if gwRes:
                    gwUri = gwRes[1]
                    gwSocket = gwRes[2].split(':')[1]
                    Logger.LM_ERR('Returned Gateway: %s\n' % gwUri)
                    msg.rewrite_ruri("sip:%s@%s" % (gwUri, gwSocket))
                    displayNameWRoom = '"%s-%s%s"' % (str(len(room)), room, displayName.replace('"',''))
                    KSR.uac.uac_replace_from(displayNameWRoom, "")
                    Logger.LM_ERR('########## SIP request, method = %s, RURI = %s, From = %s\n' % (msg.Method, msg.RURI, msg.getHeader('from')))

        return 1

def mod_init():
    return RequestGw()
