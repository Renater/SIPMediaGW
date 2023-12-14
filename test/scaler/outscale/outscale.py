#!/usr/bin/env python

import os
import json
from dataclasses import dataclass
import importlib
import inspect
import base64
from ipaddress import ip_address
from manageInstance import ManageInstance

class Outscale(ManageInstance):

    def __init__(self, profile):
        self.sdk= importlib.import_module('sdk')
        self.profile = profile
        self.version = '2016-09-15'

    def configureInstance(self, configFile):
        f = open(configFile)
        instConfig = json.load(f)
        f.close()

        #OSC profile configuration
        self.fcu = self.sdk.FcuCall(
            access_key=instConfig['profile'][self.profile]['access_key'],
            secret_key=instConfig['profile'][self.profile]['secret_key'],
            endpoint='fcu.{}.outscale.com'.format(instConfig['profile'][self.profile]['region']),
            region_name=instConfig['profile'][self.profile]['region']
        )

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

        stunSrv = None
        if 'turn_server' in instConfig['user_data']:
            pubIp = instConfig['user_data']['turn_server']['pub']
            if instConfig['user_data']['turn_server']['priv']:
                stunSrv = instConfig['user_data']['turn_server']['priv']
            else:
                stunSrv = instConfig['user_data']['turn_server']['pub']
        dockerImg = instConfig['user_data']['docker_image']
        self.userData = "\n".join(instConfig['user_data']['script']).format(docker=dockerImg, sip=sipDomain, stun=stunSrv, pub=pubIp )

    def enumerateInstances(self):
        gnFilt = {'Name':'group-id', 'Value' : [self.secuGrp['app']]}
        subNetFilt={'Name':'subnet-id', 'Value' : [self.subNet]}
        self.fcu.make_request("DescribeInstances", Profile=self.profile, Version=self.version,
                              Filter=[gnFilt, subNetFilt])
        if (self.fcu.response['DescribeInstancesResponse']['reservationSet'] and
            'item' in self.fcu.response['DescribeInstancesResponse']['reservationSet']):
            items = self.fcu.response['DescribeInstancesResponse']['reservationSet']['item']
        else:
            return
        items = items if isinstance(items, list) else [items]
        instDict = []
        for it in items:
            if 'privateIpAddress' in it['instancesSet']['item']:
                privIpAddress = it['instancesSet']['item']['privateIpAddress']
            if 'launchTime' in it['instancesSet']['item']:
                launchTime = it['instancesSet']['item']['launchTime']
            instDict.append({'start':launchTime, 'addr':privIpAddress})
        return instDict

    def runInstance(self, numCPU):
            bdm = [{ "Ebs": {"DeleteOnTemination": True, "VolumeSize": 10, "VolumeType": "gp2"},
                    "DeviceName": "/dev/sda1" }]
            self.fcu.make_request("RunInstances", 
                            Profile=self.profile, Version=self.version,
                            BlockDeviceMapping=bdm,
                            MinCount=1, MaxCount=1,
                            DryRun=False,
                            ImageId=self.ami,
                            KeyName="Visio-DEV",
                            InstanceInitiatedShutdownBehavior="stop",
                            InstanceType=self.instType[numCPU],
                            SubnetId=self.subNet,
                            SecurityGroupId=[self.secuGrp['admin'],self.secuGrp['app']],
                            UserData=base64.b64encode(self.userData.encode('ascii')).decode("utf-8"))
            return self.fcu.response['RunInstancesResponse']['instancesSet']['item']

    def createInstance(self, numCPU, name=None, ip=None):
        res = self.runInstance(numCPU)
        if 'instanceId' in res:
            instanceId = res['instanceId']
            instName = res['privateDnsName']
            privIp = res['privateIpAddress']
        instName = "{}.{}.{}".format(instName.split('.')[0], self.instName,name)
        if not ip:
            res = self.fcu.make_request("AllocateAddress", Profile=self.profile, Version=self.version)
            pubIp = self.fcu.response['AllocateAddressResponse']['publicIp']
        else:
            pubIp=ip
        res = self.fcu.make_request("AssociateAddress", Profile=self.profile, Version=self.version,
                            InstanceId=instanceId,
                            PublicIp=pubIp)
        res = self.fcu.make_request("CreateTags", Profile=self.profile, Version=self.version,
                            ResourceId=instanceId,
                            Tag=[{"Key": "name", "Value":"{}".format(instName)}])
        print('Created Instance: {}, {}, {}, {}VCPUs'.format(instanceId, privIp, pubIp, numCPU), flush=True)

        return { "id":instanceId, "ip":pubIp}

    def destroyInstances(self, ipList):
        for ip in ipList:
            pubIp = None
            privIp = None
            if ip_address(ip).is_private:
                privIp = ip
                gnFilt = {'Name':'group-id', 'Value' : self.secuGrp['app']}
                subNetFilt={'Name':'subnet-id', 'Value' : [self.subNet]}
                privateIpFilt={'Name':'private-ip-address',
                               'Value': [ip]}
                self.fcu.make_request("DescribeInstances", Profile=self.profile, Version=self.version,
                                       Filter=[gnFilt, subNetFilt, privateIpFilt])
                if 'item' in self.fcu.response['DescribeInstancesResponse']['reservationSet']:
                    it = self.fcu.response['DescribeInstancesResponse']['reservationSet']['item']
                    instanceId = it['instancesSet']['item']['instanceId']
                    if 'ipAddress' in it['instancesSet']['item']:
                        pubIp = it['instancesSet']['item']['ipAddress']
            else:
                pubIp=ip
                self.fcu.make_request("DescribeAddresses", Profile=self.profile, Version=self.version,
                                       PublicIp=pubIp)
                if 'instanceId' in self.fcu.response['DescribeAddressesResponse']['addressesSet']['item']:
                    instanceId = self.fcu.response['DescribeAddressesResponse']['addressesSet']['item']['instanceId']
            if instanceId:
                if pubIp:
                    self.fcu.make_request("DisassociateAddress", Profile=self.profile, Version=self.version, PublicIp=pubIp)
                self.fcu.make_request("TerminateInstances", Profile=self.profile, Version=self.version, InstanceId=instanceId)
            if pubIp:
                self.fcu.make_request("ReleaseAddress", Profile=self.profile, Version=self.version, PublicIp=pubIp)
            print('Deleted Instance: {}, {}, {}'.format(instanceId, privIp, pubIp), flush=True)
