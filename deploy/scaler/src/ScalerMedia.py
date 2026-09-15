#!/usr/bin/env python
import math
import datetime as dt
import dateutil.parser as du
import json
import redis

from contextlib import closing
from Scaler import Scaler

def gwLoad(raw):
   """Read a gateway entry, written by the proxy as JSON."""
   if not raw:
      return {}
   try:
      value = json.loads(raw)
   except (TypeError, ValueError):
      return {}
   return value if isinstance(value, dict) else {}


def gwDump(gw):
   """Write one back."""
   return json.dumps(gw)


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
          gw = gwLoad(value)
          gwIp = gw["gw_ip"].split(':', 1)[0]
          state = gw.get("gw_state")
          # created: never used; stopped: call over. Both are idle, so both
          # can be reclaimed.
          if state in ["created", "stopped"]:
                # No rooms assigned, can downscale
                ipList.append(gwIp)
                # Update gateway state to stopping
                gw["gw_state"] = "stopping"
                #update last status_update_time
                gw["start_time"] = dt.datetime.now().isoformat()

                self.redisClient.set(key, gwDump(gw))
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
            gw = gwLoad(value)
            gwIp = gw["gw_ip"]
            state = gw.get("gw_state")
            lastUpdateStr = gw.get("start_time")
            if state == "stopping" and lastUpdateStr:
                lastUpdate = du.parse(lastUpdateStr)
                if (now - lastUpdate).total_seconds() > thresholdSeconds:
                    ipList.append(gwIp)
        if ipList:
            print(f"Cleaning up stale gateways: {ipList}", flush=True)
            self.csp.destroyInstances(ipList)
        
        super().cleanup()

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
            gw = gwLoad(value)
            if gw.get("gw_state") in ("created", "stopped"):
                readyToRun += 1
        return readyToRun
