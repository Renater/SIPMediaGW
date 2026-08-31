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
                self.csp.createInstance(cpu, '{}'.format(self.config['ram_per_gw']), self.config['gw_name_prefix'])
        if numCPU != 0:
            self.csp.createInstance(cpu, '{}'.format(self.config['ram_per_gw']), self.config['gw_name_prefix'])

    # Downscale function
    def downScale(self, numGW):
       pass

    # Cleanup stale instances
    def cleanup(self):
        instList = self.csp.enumerateInstances()
        runningCpuCount = 0
        if instList :
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

    def _scaleMethod(self):
        method = self.config.get('scale_method') or 'buffer'
        if isinstance(method, str):
            method = method.strip().lower()
        else:
            method = 'buffer'
        if method not in ('buffer', 'floor'):
            print('Unknown scale_method={}, using buffer'.format(method), flush=True)
            return 'buffer'
        return method

    def _currentSlot(self, scaleTime=None):
        weekday = dt.datetime.now().strftime('%A').lower()  # e.g. 'monday', 'saturday'
        thresholdConfig = self.config['auto_scale_threshold']
        if weekday in thresholdConfig:
            thresholdTimeLine = thresholdConfig[weekday]
        else:
            thresholdTimeLine = thresholdConfig['default']

        if not scaleTime:
            scaleTime = dt.datetime.now().strftime("%H:%M:%S")
        th = min([ i for i in list(thresholdTimeLine.keys()) if i <= scaleTime],
                key=lambda x:abs(getSeconds(x)-getSeconds(scaleTime)))
        return thresholdTimeLine, th, scaleTime

    # Scaling logic based on current load and time of the day
    def scale(self, scaleTime=None, incallsNum=None):
        if self._scaleMethod() == 'floor':
            return self._scaleFloor(scaleTime, incallsNum)
        return self._scaleBuffer(scaleTime, incallsNum)

    def _scaleBuffer(self, scaleTime=None, incallsNum=None):
        # unlockedMin is a buffer of ready (idle) gateways — historical formula.
        thresholdTimeLine, th, scaleTime = self._currentSlot(scaleTime)

        # Get current capacity and ready to run capacity
        currentCapacity = self.getCurrentCapacity()
        readyToRunNum  = self.getReadyToRunCapacity()


        inCallNum = incallsNum if incallsNum else (currentCapacity - readyToRunNum )
        minCapacity = thresholdTimeLine[th]['unlockedMin'] + inCallNum
        if readyToRunNum < thresholdTimeLine[th]['unlockedMin']:
            targetCapacity = min((currentCapacity + thresholdTimeLine[th]['unlockedMin']
                                  - readyToRunNum),
                                  thresholdTimeLine[th]['maxGw'])
            capacityIncrease = math.ceil(targetCapacity - currentCapacity)
            if capacityIncrease > 0:
                self.upScale(math.ceil(capacityIncrease*self.config['cpu_per_gw']))
                currentCapacity = currentCapacity + capacityIncrease

        targetCapacity = min(thresholdTimeLine[th]['maxGw'],
                             max(minCapacity, inCallNum/thresholdTimeLine[th]['loadMax']))
        capacityIncrease = math.ceil(targetCapacity - currentCapacity)

        if capacityIncrease > 0:
            # Upscale
            self.upScale(math.ceil(capacityIncrease*self.config['cpu_per_gw']))
        if capacityIncrease < 0:
            # Downscale
            self.downScale(abs(capacityIncrease))
        return 0

    def _scaleFloor(self, scaleTime=None, incallsNum=None):
        # unlockedMin is a floor on total gateway count.
        thresholdTimeLine, th, scaleTime = self._currentSlot(scaleTime)
        unlockedMin = thresholdTimeLine[th]['unlockedMin']
        loadMax = thresholdTimeLine[th]['loadMax']
        maxGw = thresholdTimeLine[th]['maxGw']

        currentCapacity = self.getCurrentCapacity()
        readyToRunNum = self.getReadyToRunCapacity()
        inCallNum = incallsNum if incallsNum else (currentCapacity - readyToRunNum)
        loadRatio = (inCallNum / currentCapacity) if currentCapacity > 0 else 0.0

        if currentCapacity < unlockedMin:
            floorTarget = min(unlockedMin, maxGw)
            capacityIncrease = math.ceil(floorTarget - currentCapacity)
            if capacityIncrease > 0:
                self.upScale(math.ceil(capacityIncrease*self.config['cpu_per_gw']))
                currentCapacity = currentCapacity + capacityIncrease

        if currentCapacity > 0 and loadRatio > loadMax:
            loadTarget = min(maxGw, math.ceil(inCallNum / loadMax))
            capacityIncrease = math.ceil(loadTarget - currentCapacity)
            if capacityIncrease > 0:
                self.upScale(math.ceil(capacityIncrease*self.config['cpu_per_gw']))
                currentCapacity = currentCapacity + capacityIncrease

        if inCallNum > 0:
            sustainTarget = max(unlockedMin, math.ceil(inCallNum / loadMax))
        else:
            sustainTarget = unlockedMin
        sustainTarget = min(sustainTarget, maxGw)
        capacityDecrease = currentCapacity - sustainTarget
        if capacityDecrease > 0:
            self.downScale(capacityDecrease)
        return 0
