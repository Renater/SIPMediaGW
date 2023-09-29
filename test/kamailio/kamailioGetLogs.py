#!/usr/bin/env python3
import mysql.connector as mysqlcon
import os
from contextlib import closing
import mysql.connector as mysqlcon

db = {
  'host': os.environ.get('DBHOST'),
  'user': os.environ.get('DBRWUSER'),
  'pwd': os.environ.get('DBRWPW'),
  'name': os.environ.get('DBNAME')}

gwNamePart = os.environ.get('GW_NAME_PREFIX').replace('"',"").replace("'", "")

with closing(mysqlcon.connect(host=db['host'],
                              user=db['user'],
                              password=db['pwd'],
                              database=db['name'])) as con:
    with closing(con.cursor()) as cursor:
        cursor.execute('''SELECT contact, username FROM location
                          WHERE
                              username LIKE CONCAT('%',%s,'%')
                              ;''',(gwNamePart,))
        contactList = cursor.fetchall()
        print('Number of registered SIPMediaGWs: {}'.format(len(contactList)), flush=True)

        cursor.execute('''SELECT callee_contact FROM dialog
                          WHERE
                              callee_contact LIKE CONCAT('%',%s,'%')
                              ;''',(gwNamePart,))
        contactList = cursor.fetchall()
        print('Number of busy SIPMediaGWs: {}'.format(len(contactList)), flush=True)

        cursor.execute('''SELECT contact, username FROM location
                          WHERE
                              locked = 0 AND
                              username LIKE CONCAT('%',%s,'%') AND
                              NOT EXISTS (
                                 SELECT callee_contact
                                 FROM dialog
                                 WHERE callee_contact LIKE CONCAT('%',location.username,'%')
                              );''',(gwNamePart,))
        contactList = cursor.fetchall()
        print('Number of available SIPMediaGWs: {}'.format(len(contactList)), flush=True)
