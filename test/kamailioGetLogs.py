#!/usr/bin/env python
import sqlite3
import configparser

dbPath = '/usr/local/etc/kamailio/kamailio.sqlite'
congiFile = "/etc/sipmediagw.cfg"

config = configparser.ConfigParser()
config.read(congiFile)
gwNamePart = config['mediagw']['sipUaNamePart'].replace('"',"").replace("'", "")

dbCon = sqlite3.connect(dbPath)

with dbCon as con:
    cursor = con.cursor()

    cursor.execute('''SELECT contact, username FROM location
                      WHERE
                          username LIKE '%'||?||'%'
                          ;''',(gwNamePart,))
    contactList = cursor.fetchall()
    print('Number of registered SIPMediaGWs: {}'.format(len(contactList)), flush=True)

    cursor.execute('''SELECT contact, username FROM location
                      WHERE
                          locked = 1 AND
                          username LIKE '%'||?||'%'
                          ;''',(gwNamePart,))
    contactList = cursor.fetchall()
    print('Number of busy SIPMediaGWs: {}'.format(len(contactList)), flush=True)

    cursor.execute('''SELECT contact, username FROM location
                      WHERE
                          locked = 0 AND
                          username LIKE '%'||?||'%' AND
                          NOT EXISTS (
                             SELECT callee_contact
                             FROM dialog
                             WHERE callee_contact LIKE '%'||location.contact||'%'
                          );''',(gwNamePart,))
    contactList = cursor.fetchall()
    print('Number of available SIPMediaGWs: {}'.format(len(contactList)), flush=True)


