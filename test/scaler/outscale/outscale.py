#!/usr/bin/env python

import os
import json
from dataclasses import dataclass
from json2html import *
import importlib
import inspect
import base64


class Outscale(ManageInstance):

    def __init__(self):
        self.sdk= importlib.import_module('sdk')
        self.profile = 'visio-dev'
        self.version = '2016-09-15'

        f = open("{}/.osc/config.json".format(os.getenv("HOME")))
        oscConfig = json.load(f)[self.profile]
        f.close()

        self.fcu = self.sdk.FcuCall(
            access_key=oscConfig['access_key'],
            secret_key=oscConfig['secret_key'],
            endpoint='fcu.{}.outscale.com'.format(oscConfig['region']),
            region_name=oscConfig['region']
        )

    def configureInstance(self, configFile):
        f = open(configFile)
        instConfig = json.load(f)
        f.close()

        # Image configuration
        self.instName = instConfig['name']
        self.instType = instConfig['instance_type']
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

        stunSrv = None
        if 'turn_server' in instConfig['user_data']:
            pubIp = instConfig['user_data']['turn_server']['pub']
            if instConfig['user_data']['turn_server']['priv']:
                stunSrv = instConfig['user_data']['turn_server']['priv']
            else:
                stunSrv = instConfig['user_data']['turn_server']['pub']
        dockerImg = instConfig['user_data']['docker_image']
        self.userData = "\n".join(instConfig['user_data']['script']).format(docker=dockerImg, sip=sipDomain, stun=stunSrv, pub=pubIp )

    def runInstance(self):
            bdm = [{ "Ebs": {"DeleteOnTemination": True, "VolumeSize": 10, "VolumeType": "gp2"},
                    "DeviceName": "/dev/sda1" }]
            self.fcu.make_request("RunInstances", 
                            Profile=self.profile, Version=self.version,
                            BlockDeviceMapping=bdm,
                            MinCount=1, MaxCount=1,
                            DryRun=False,
                            ImageId=self.imgId,
                            KeyName="Visio-DEV",
                            InstanceInitiatedShutdownBehavior="stop",
                            InstanceType=self.instType,
                            SubnetId=self.subNetId,
                            SecurityGroupId=self.securityGroupId,
                            UserData=base64.b64encode(self.userData).decode("utf-8"))
            return self.fcu.response

    def createInstance(self, name=None, ip=None):
        res = self.runInstance()
        instanceId = self.fcu.response['RunInstancesResponse']['instancesSet']['item']['instanceId']
        instName = name if name else self.fcu.response['RunInstancesResponse']['instancesSet']['item']['privateDnsName']
        if not ip:
            res = self.fcu.make_request("AllocateAddress", Profile=self.profile, Version=self.version)
            pubIP = self.fcu.response['AllocateAddressResponse']['publicIp']
        else:
            pubIP=ip
        res = self.fcu.make_request("AssociateAddress", Profile=self.profile, Version=self.version,
                            InstanceId=instanceId,
                            PublicIp=pubIP)
        res = self.fcu.make_request("CreateTags", Profile=self.profile, Version=self.version,
                            ResourceId=instanceId,
                            Tag=[{"Key": "name", "Value":"{}".format(instName)}])
        print('Created Instance: {:<16}{:<10}'.format(instanceId, pubIP))

    def destroyInstances(self, pubIPs):
        for ip in pubIPs:
            res = self.fcu.make_request("DescribeAddresses", Profile=self.profile, Version=self.version,
                                        PublicIp=ip)
            if 'instanceId' in self.fcu.response['DescribeAddressesResponse']['addressesSet']['item']:
                instanceId = self.fcu.response['DescribeAddressesResponse']['addressesSet']['item']['instanceId']
                if instanceId:
                    self.fcu.make_request("DisassociateAddress", Profile=self.profile, Version=self.version, PublicIp=ip)
                    self.fcu.make_request("TerminateInstances", Profile=self.profile, Version=self.version, InstanceId=instanceId)
                self.fcu.make_request("ReleaseAddress", Profile=self.profile, Version=self.version, PublicIp=ip)
