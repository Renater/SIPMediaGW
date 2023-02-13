#!/usr/bin/env python3
import sqlite3
import os
from contextlib import closing

dbPath = '/usr/local/etc/kamailio/kamailio.sqlite'

gwNamePart = os.environ.get('GW_NAME_PREFIX').replace('"',"").replace("'", "")

with closing(sqlite3.connect(dbPath)) as con:
    with closing(con.cursor()) as cursor:
        cursor = con.cursor()

        cursor.execute('''SELECT contact, username FROM location
                          WHERE
                              username LIKE '%'||?||'%'
                              ;''',(gwNamePart,))
        contactList = cursor.fetchall()
        print('Number of registered SIPMediaGWs: {}'.format(len(contactList)), flush=True)

        cursor.execute('''SELECT callee_contact FROM dialog
                          WHERE
                              callee_contact LIKE '%'||?||'%'
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
                                 WHERE callee_contact LIKE '%'||location.username||'%'
                              );''',(gwNamePart,))
        contactList = cursor.fetchall()
        print('Number of available SIPMediaGWs: {}'.format(len(contactList)), flush=True)
