#!/usr/bin/env python

import os
import json
from dataclasses import dataclass
from json2html import *
import importlib
import inspect
import mysql.connector as mysqlcon
import queue
import ipaddress
from ...manageInstance import ManageInstance

class Fakescale(ManageInstance):

    def __init__(self):
        self.freeIpAddr = queue.Queue()
        for addr in range(167772160,167779160):
            self.freeIpAddr.put(str(ipaddress.ip_address(addr)))

    def configureInstance(self, configFile):
        f = open(configFile)
        instConfig = json.load(f)
        f.close()

        # Image configuration
        self.instName = instConfig['name']
        self.instType = instConfig['instance_type_by_cpu_num']
        self.ami = instConfig['instance_image']
        self.subNet = instConfig['subnet']
        self.secuGrp = instConfig['security_group']
        self.userData = ""

        # User Data
        sipDomain = None
        if 'sip_domain' in instConfig['user_data']:
            if instConfig['user_data']['sip_domain']['priv']:
                sipDomain = instConfig['user_data']['sip_domain']['priv']
            else:
                sipDomain = instConfig['user_data']['sip_domain']['pub']
                pubIp = instConfig['user_data']['sip_domain']['pub']

    def createInstance(self, numCPU, gigaRAM="4", name=None, ip=None):
        return self.freeIpAddr.get()

    def destroyInstances(self, ipList):
        for ip in ipList:
            self.freeIpAddr.put(ip)
