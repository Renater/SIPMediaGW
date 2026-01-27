#!/usr/bin/env python
import math
import datetime as dt
import dateutil.parser as du
import json


def getSeconds(stringHMS):
   timedeltaObj = dt.datetime.strptime(stringHMS, "%H:%M:%S") - dt.datetime(1900,1,1)
   return timedeltaObj.total_seconds()

class Scaler:
    def __init__(self, cspObj):
        self.csp = cspObj

    def configure(self, configFile):
        f = open(configFile)
        self.config = json.load(f)
        f.close()

    # Upscale function
    def upScale(self, numCPU):
        # cpuRange values must be multiples of 4
        cpuRange = list(self.csp.instType.keys())
        cpuRange.sort(reverse=True)
        for cpu in cpuRange:
            instNum = numCPU//int(cpu)
            numCPU = numCPU%int(cpu)
            for i in range(instNum):
                self.csp.createInstance(cpu, self.config['gw_name_prefix'])
        if numCPU != 0:
            self.csp.createInstance(cpu, self.config['gw_name_prefix'])

    # Downscale function
    def downScale(self, numGW):
       pass

    # Cleanup stale instances
    def cleanup(self):
        instList = self.csp.enumerateInstances()
        runningCpuCount = 0
        for inst in instList:
            if inst in self.config['cleaner_blacklist']:
                continue
            runningCpuCount+= inst['cpu_count']
            if not inst['addr']['pub']:
                now = dt.datetime.now(dt.timezone.utc)
                start = du.parse(inst['start'])
                if (now-start).total_seconds() > 600:
                    self.csp.destroyInstances([inst['addr']['priv']])
        print('Number of running CPUs: {} \n'.format(runningCpuCount), flush=True)

    # Get current available capacity
    def getCurrentCapacity(self):
       pass

    # Get Ready to run capacity
    def getReadyToRunCapacity(self):
        pass

    # Scaling logic based on current load and time of the day
    def scale(self, scaleTime=None, incallsNum=None):
        thresholdTimeLine = self.config['auto_scale_threshold']
        if not scaleTime:
            scaleTime = dt.datetime.now().strftime("%H:%M:%S")
        th = min([ i for i in list(thresholdTimeLine.keys()) if i <= scaleTime],
                key=lambda x:abs(getSeconds(x)-getSeconds(scaleTime)))

        # Get current capacity and ready to run capacity
        currentCapacity = self.getCurrentCapacity()
        readyToRunNum  = self.getReadyToRunCapacity()


        inCallNum = incallsNum if incallsNum else (currentCapacity - readyToRunNum )
        minCapacity = thresholdTimeLine[th]['unlockedMin'] + inCallNum
        if readyToRunNum < thresholdTimeLine[th]['unlockedMin']:
            self.upScale(math.ceil(self.config['cpu_per_gw']*
                                        (thresholdTimeLine[th]['unlockedMin'] - readyToRunNum)))
            currentCapacity = thresholdTimeLine[th]['unlockedMin'] + inCallNum

        targetCapacity = max(minCapacity, inCallNum/thresholdTimeLine[th]['loadMax'])
        capacityIncrease = math.ceil(targetCapacity - currentCapacity)

        if capacityIncrease > 0:
            # Upscale
            self.upScale(math.ceil(capacityIncrease*self.config['cpu_per_gw']))
        if capacityIncrease < 0:
            # Downscale
            self.downScale(abs(capacityIncrease))
        return 0
