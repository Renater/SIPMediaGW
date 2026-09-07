#!/usr/bin/env python
"""Contract between the scaler and the cloud provider it drives."""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ManageInstance(ABC):
    """
    Interface a cloud provider must satisfy to be usable by the scaler.

    The four abstract methods have to be implemented; a provider that misses
    one cannot be instantiated at all, which surfaces the gap at startup
    instead of on the first scaling iteration. `createInstancesParallel` and
    `close` ship with working defaults, so a provider only overrides them when
    it has something better to offer than the generic behaviour.
    """

    @abstractmethod
    def configureInstance(self, configFile, initData):
        """
        Load the provider configuration from `configFile`.

        `initData` carries the per-scaler-type data injected into the instances
        at boot, keyed by scaler type ("sip" or "media").
        """

    @abstractmethod
    def enumerateInstances(self):
        """
        Return the instances managed by this provider.

        Each entry is a dict shaped as follows, which is what `Scaler.cleanup`
        expects:

            {
                "start": "<ISO-8601 creation date>",
                "addr": {"priv": "<private ip>", "pub": "<public ip or None>"},
                "cpu_count": <int>,
            }
        """

    @abstractmethod
    def createInstance(self, numCPU, gigaRAM, name=None, ip=None):
        """
        Create a single instance and return a dict describing it.

        `ip` requests a specific public address; when it is None the provider
        allocates one. Raises when the instance cannot be created.
        """

    @abstractmethod
    def destroyInstances(self, ipList):
        """Destroy the instances owning the given IP addresses."""

    def createInstancesParallel(self, count, numCPU, gigaRAM, name=None,
                                timeoutSeconds=None):
        """
        Create `count` instances and return those that were actually created.

        The returned list is shorter than `count` when some creations failed,
        which is how the scaler learns its real capacity gain. This default
        creates them one after another and ignores `timeoutSeconds`, which is
        only meaningful to providers that submit the creations concurrently.
        """
        created = []
        for _ in range(max(0, int(count))):
            try:
                created.append(self.createInstance(numCPU, gigaRAM, name=name))
            except Exception as error:
                logger.error("Instance creation failed: %s", error)
        return created

    def reconcile(self, timeoutSeconds=None):
        """
        Bring the fleet in line with what previous creations left behind.

        Called once per scaling iteration, before any decision is taken. A
        provider that creates instances asynchronously uses this to finish the
        job and to drop the ones that will never boot; the default does nothing,
        which is correct for a provider whose createInstance already returns a
        fully usable instance.
        """

    def close(self):
        """Release the provider resources. No-op unless the provider holds any."""
