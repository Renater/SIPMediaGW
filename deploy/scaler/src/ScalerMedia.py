#!/usr/bin/env python
import math
import datetime as dt
import dateutil.parser as du
import json
import redis

from contextlib import closing
from Scaler import Scaler

def getSeconds(stringHMS):
   timedeltaObj = dt.datetime.strptime(stringHMS, "%H:%M:%S") - dt.datetime(1900,1,1)
   return timedeltaObj.total_seconds()

# Media Scaler class using Redis to track room assignments and gateway states



class ScalerMedia(Scaler):

    def __init__(self, cspObj):
        super().__init__(cspObj)

    def configure(self, configFile):
        super().configure(configFile)
        self.redisClient = redis.Redis(host=self.config["redis"]["host"], port=self.config["redis"]["port"], decode_responses=True)

    # Downscale function
    def downScale(self, numGW):
        ipList = []
        for key in self.redisClient.scan_iter(match="gateway:*"):
          if numGW <= 0:
              break
          value = self.redisClient.get(key)
          parts = value.split("|")
          gwIp = parts[0]
          state = parts[1] if len(parts) > 1 else None
          if state in ["started", "stopped"]:
                # No rooms assigned, can downscale
                ipList.append(gwIp)
                # Update gateway state to stopping
                parts[1] = "stopping"
                #update last status_update_time
                parts[4] = dt.datetime.now().isoformat()

                self.redisClient.set(key, "|".join(parts))
                numGW -= 1
        if ipList:
            print(f"Downscaling gateways: {ipList}", flush=True)
            self.csp.destroyInstances(ipList)

    # Cleanup stale instances
    def cleanup(self):
        # Check for gateways in 'stopping' state for more than threshold time
        thresholdSeconds = self.config.get('cleanup_threshold_seconds', 600)
        now = dt.datetime.now(dt.timezone.utc)
        ipList = []
        for key in self.redisClient.scan_iter(match="gateway:*"):
            value = self.redisClient.get(key)
            parts = value.split("|")
            gwIp = parts[0]
            state = parts[1] if len(parts) > 1 else None
            lastUpdateStr = parts[4] if len(parts) > 4 else None
            if state == "stopping" and lastUpdateStr:
                lastUpdate = du.parse(lastUpdateStr)
                if (now - lastUpdate).total_seconds() > thresholdSeconds:
                    ipList.append(gwIp)
        if ipList:
            print(f"Cleaning up stale gateways: {ipList}", flush=True)
            self.csp.destroyInstances(ipList)
        
        #Get running VM instances
        instList = self.csp.enumerateInstances()
        runningCpuCount = 0
        if instList:
            for inst in instList:
                runningCpuCount+= inst['cpu_count']
                if not inst['addr']['pub']:
                    now = dt.datetime.now(dt.timezone.utc)
                    start = du.parse(inst['start'])
                    if (now-start).total_seconds() > 600:
                        self.csp.destroyInstances([inst['addr']['priv']])
                        self.redisClient.delete(f"gateway:{inst['addr']['priv']}")
            print('Number of running CPUs: {} \n'.format(runningCpuCount), flush=True)

    # Get current available capacity
    def getCurrentCapacity(self):
        #Get number of available gateways from Redis
        registeredGateways = 0
        for _ in self.redisClient.scan_iter(match="gateway:*"):
                registeredGateways += 1
        return registeredGateways

    # Get Ready to run capacity
    def getReadyToRunCapacity(self):
        #Get number of available gateways from Redis
        readyToRun = 0
        for key in self.redisClient.scan_iter(match="gateway:*"):
            value = self.redisClient.get(key)
            parts = value.split("|")
            if len(parts) > 1 and parts[1] == "started":
                readyToRun += 1
        return readyToRun
