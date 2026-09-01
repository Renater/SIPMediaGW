#!/usr/bin/env python
"""OpenStack implementation of the scaler's cloud provider interface."""

import json
import logging
import time
import datetime as dt
from collections import defaultdict
from ipaddress import ip_address
from concurrent.futures import ThreadPoolExecutor, as_completed

import dateutil.parser as du
import openstack

from manageInstance import ManageInstance

from . import networking
from . import volumes

logger = logging.getLogger(__name__)

_MAX_PARALLEL_WORKERS = 10
_DEFAULT_CREATE_TIMEOUT = 300
_POLL_INTERVAL = 5

# Statuses of a server that already counts as capacity: one that is still
# building is on its way to becoming a gateway, and the scaler has to know about
# it or it would order the very same instance again on the next iteration.
_COUNTED_STATUSES = ("ACTIVE", "BUILD")


class OpenstackProvider(ManageInstance):

    def __init__(self, profile):
        self.profile = profile
        self.conn = None
        self.instName = None
        self.gwNamePrefix = None
        self._warnedMissingInstName = False
        self.instType = {}
        self.ami = None
        self.network = None
        self.subnet = None
        self._primarySubnetCidr = None
        # Interface selection for the "primary" NIC.
        # Values can be either Neutron network names or subnet names.
        # If `interface_1.priv` is set -> VM fixed IP comes from this.
        # If `interface_1.pub` is set -> floating IP is allocated from this.
        self.interface1PubRef = None
        self.interface1PrivRef = None
        self.secuGrp = {}
        self.keyPair = None
        self.userData = ""
        self._flavorVcpuCache = {}
        self.deleteVolumesOnDestroy = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _connect(self, profileCfg):
        cfg = profileCfg if profileCfg else {}

        if cfg.get("client_id") and cfg.get("client_secret"):
            return openstack.connection.Connection(
                auth={
                    "auth_url": cfg.get("auth_url"),
                    "application_credential_id": cfg.get("client_id"),
                    "application_credential_secret": cfg.get("client_secret"),
                },
                auth_type="v3applicationcredential",
                region_name=cfg.get("region"),
                identity_interface=cfg.get("interface", "public"),
            )

        auth = {}
        for key in [
            "auth_url",
            "username",
            "password",
            "project_name",
            "project_id",
            "user_domain_name",
            "user_domain_id",
            "project_domain_name",
            "project_domain_id",
        ]:
            if cfg.get(key) is not None:
                auth[key] = cfg.get(key)

        kwargs = {
            "auth": auth if auth else None,
            "region_name": cfg.get("region"),
            "identity_interface": cfg.get("interface", "public"),
        }
        return openstack.connection.Connection(**{k: v for k, v in kwargs.items() if v is not None})

    def close(self):
        if self.conn is None:
            return
        try:
            self.conn.close()
        except Exception as exc:
            logger.warning("Failed to close the OpenStack connection: %s", exc)
        finally:
            self.conn = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configureInstance(self, configFile, initData):
        with open(configFile) as f:
            instConfig = json.load(f)

        # Presence is not enough: an empty "name" would make _isManagedServer
        # match every server in the project. Refuse blank values up front.
        required = ["name", "instance_image", "instance_type_by_cpu_num"]
        missing = [k for k in required if k not in instConfig]
        if missing:
            raise ValueError("Missing required config keys: {}".format(missing))

        name = instConfig["name"]
        image = instConfig["instance_image"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("'name' must be a non-empty string (instance name prefix)")
        if not isinstance(image, str) or not image.strip():
            raise ValueError("'instance_image' must be a non-empty string")
        if not isinstance(instConfig["instance_type_by_cpu_num"], dict):
            raise ValueError("'instance_type_by_cpu_num' must be a non-empty mapping")
        if not instConfig["instance_type_by_cpu_num"]:
            raise ValueError("'instance_type_by_cpu_num' must be a non-empty mapping")

        if self.conn is None:
            profileCfg = instConfig.get("profile", {}).get(self.profile, {})
            self.conn = self._connect(profileCfg)

        self.instName = name.strip()
        self._warnedMissingInstName = False
        # Narrow ownership to "<name>.<gw_name_prefix>..." (e.g. GW.mediagw-0),
        # not every server that merely starts with "GW".
        rawGwPrefix = initData.get("gw_name_prefix") if isinstance(initData, dict) else None
        if isinstance(rawGwPrefix, str) and rawGwPrefix.strip():
            self.gwNamePrefix = rawGwPrefix.strip()
        else:
            self.gwNamePrefix = None
            logger.warning(
                "gw_name_prefix missing from initData; no server will be treated as managed"
            )
        self.instType = instConfig["instance_type_by_cpu_num"]
        self.ami = image.strip()
        self.network = instConfig.get("network")
        self.subnet = instConfig.get("subnet")
        iface1 = instConfig.get("interface_1", {}) or {}
        self.interface1PrivRef = iface1.get("priv") or iface1.get("priv_subnet")
        self.interface1PubRef = iface1.get("pub") or iface1.get("pub_subnet")
        self.secuGrp = instConfig.get("security_group", {})
        self.keyPair = instConfig.get("key_pair")
        self.deleteVolumesOnDestroy = bool(instConfig.get("delete_volumes_on_destroy", False))
        self.userData = ""
        self._primarySubnetCidr = None
        logger.info(
            "Volume deletion on destroy is %s",
            "ENABLED" if self.deleteVolumesOnDestroy else "DISABLED",
        )

        self._resolvePrimarySubnetCidr()
        self._buildUserData(instConfig, initData)

    def _buildUserData(self, instConfig, initData):
        """Render the cloud-init script from the config and the per-action data."""
        scriptCfg = instConfig.get("user_data", {}).get("script", {})
        self.userData = "\n".join(scriptCfg.get("common", []))

        if "sip" in initData:
            sipCfg = instConfig.get("user_data", {})
            for initKey, cfgKey in (
                ("registrar", "sip_registrar"),
                ("proxy", "outbound_proxy"),
                ("turn", "turn_server"),
            ):
                if initKey in initData["sip"]:
                    continue
                entry = sipCfg.get(cfgKey)
                initData["sip"][initKey] = (
                    (entry.get("priv") or entry.get("pub")) if entry else None
                )

        for act in initData:
            if not isinstance(initData.get(act), dict):
                continue
            actionScript = scriptCfg.get(act, [])
            if not actionScript:
                continue
            self.userData += "\n"
            try:
                self.userData += "\n".join(actionScript).format_map(
                    defaultdict(str, initData[act])
                )
            except (KeyError, ValueError, IndexError) as exc:
                logger.error(
                    "Failed to render user_data script for action '%s': %s", act, exc
                )
                raise

    # ------------------------------------------------------------------
    # Network resolution
    # ------------------------------------------------------------------

    def _resolvePrimarySubnetCidr(self):
        """Best-effort: derive the subnet CIDR for the primary fixed IP."""
        primaryRef = self.interface1PrivRef or self.interface1PubRef
        if primaryRef:
            subnet = networking.findSubnet(self.conn, primaryRef)
            if subnet is not None and getattr(subnet, "cidr", None):
                self._primarySubnetCidr = subnet.cidr
                return

            if not self.network:
                network = networking.findNetwork(self.conn, primaryRef)
                if network is not None:
                    self.network = getattr(network, "name", None) or primaryRef

        if self._primarySubnetCidr is None and self.subnet:
            subnet = networking.findSubnet(self.conn, self.subnet)
            if subnet is not None and getattr(subnet, "cidr", None):
                self._primarySubnetCidr = subnet.cidr

    def _resolveFloatingNetworkId(self):
        """Best-effort: find the Neutron network floating IPs are allocated from."""
        if self.interface1PubRef:
            subnet, network = networking.resolveNetworkRef(self.conn, self.interface1PubRef)
            if subnet is not None:
                return subnet.network_id
            if network is not None:
                return network.id

        subnet = networking.findSubnet(self.conn, self.subnet)
        if subnet is not None:
            return subnet.network_id

        network = networking.findNetwork(self.conn, self.network)
        if network is not None:
            return network.id

        logger.warning(
            "No floating IP network could be resolved from interface_1.pub='%s', "
            "subnet='%s' or network='%s'",
            self.interface1PubRef, self.subnet, self.network,
        )
        return None

    def _buildPrimaryNic(self):
        """
        Build the NIC list for the primary interface.
        Preference:
          1) interface_1.priv (fixed IP)
          2) interface_1.pub (if priv is missing)
          3) legacy network/subnet
        Returns a list of one OpenStack networks entry for `create_server()`.
        """
        primaryRef = self.interface1PrivRef or self.interface1PubRef

        if primaryRef:
            subnet, network = networking.resolveNetworkRef(self.conn, primaryRef)
            if subnet is not None:
                return [{"net-id": subnet.network_id, "v4-fixed-ip": None}]
            if network is not None:
                return [{"uuid": network.id}]

        subnet = networking.findSubnet(self.conn, self.subnet)
        if subnet is not None:
            return [{"net-id": subnet.network_id, "v4-fixed-ip": None}]

        network = networking.findNetwork(self.conn, self.network)
        if network is not None:
            return [{"uuid": network.id}]

        return []

    def _getServerIps(self, server):
        return networking.extractServerIps(server, self._primarySubnetCidr, self.network)

    # ------------------------------------------------------------------
    # Instance enumeration
    # ------------------------------------------------------------------

    def _getServerVcpus(self, server):
        flavorInfo = getattr(server, "flavor", None) or {}
        if not flavorInfo:
            return 0

        # Some OpenStack versions (microversion 2.47+) embed vcpus in the
        # server detail response, so we can skip the extra API call.
        if flavorInfo.get("vcpus"):
            return int(flavorInfo["vcpus"])

        flavorRef = flavorInfo.get("id") or flavorInfo.get("original_name")
        if not flavorRef:
            return 0

        if flavorRef not in self._flavorVcpuCache:
            try:
                flv = self.conn.compute.find_flavor(flavorRef)
                self._flavorVcpuCache[flavorRef] = int(getattr(flv, "vcpus", 0) or 0) if flv else 0
            except Exception as exc:
                logger.warning("Cannot resolve vCPUs for flavor '%s': %s", flavorRef, exc)
                self._flavorVcpuCache[flavorRef] = 0
        return self._flavorVcpuCache[flavorRef]

    @staticmethod
    def _serverAgeSeconds(server):
        """Seconds since the server was created, or None when Nova did not say."""
        created = getattr(server, "created_at", None) or getattr(server, "created", None)
        if not created:
            return None
        try:
            start = du.parse(created)
        except (ValueError, OverflowError, TypeError) as exc:
            logger.debug("Cannot parse creation date '%s': %s", created, exc)
            return None
        if start.tzinfo is None:
            start = start.replace(tzinfo=dt.timezone.utc)
        return (dt.datetime.now(dt.timezone.utc) - start).total_seconds()

    def _managedNamePrefix(self):
        """
        Full name prefix of servers this scaler owns: "<instName>.<gwNamePrefix>".

        Creations are named "{instName}.{gwNamePrefix}-{index}", so ownership must
        require both parts. Matching on instName alone would also catch unrelated
        VMs such as "GW.other".
        """
        if not self.instName or not self.gwNamePrefix:
            return None
        return "{}.{}".format(self.instName, self.gwNamePrefix)

    def _isManagedServer(self, server):
        """
        Return True if the server was created by this scaler (name prefix match).

        Fail closed when the composed prefix is unknown: matching every server in
        the project would let cleanup or destroy touch unrelated VMs.
        """
        managedPrefix = self._managedNamePrefix()
        if not managedPrefix:
            if not getattr(self, "_warnedMissingInstName", False):
                logger.warning(
                    "Managed name prefix unset (name=%r gw_name_prefix=%r); "
                    "treating no server as managed",
                    self.instName, self.gwNamePrefix,
                )
                self._warnedMissingInstName = True
            return False
        serverName = getattr(server, "name", None) or ""
        return serverName.startswith(managedPrefix)

    def enumerateInstances(self):
        if not self.conn:
            return []

        appSg = self.secuGrp.get("app") if isinstance(self.secuGrp, dict) else None
        instDict = []
        for server in self.conn.compute.servers(details=True):
            try:
                if (server.status or "").upper() not in _COUNTED_STATUSES:
                    continue

                if not self._isManagedServer(server):
                    continue

                if appSg:
                    sgNames = set()
                    for sg in server.security_groups or []:
                        if isinstance(sg, dict):
                            sgNames.add(sg.get("name"))
                        else:
                            sgNames.add(sg)
                    if appSg not in sgNames:
                        continue

                privIp, pubIp = self._getServerIps(server)
                startTime = getattr(server, "created_at", None) or getattr(server, "created", None)
                cpuCnt = self._getServerVcpus(server)

                instDict.append(
                    {
                        "start": startTime,
                        "addr": {"priv": privIp, "pub": pubIp},
                        "cpu_count": int(cpuCnt),
                    }
                )
            except Exception as exc:
                logger.warning("Skipping server %s during enumeration: %s", getattr(server, "id", "?"), exc)
        return instDict

    def _buildServersByIpIndex(self):
        """Load all servers once and build an IP -> server lookup dict (managed VMs only)."""
        index = {}
        for server in self.conn.compute.servers(details=True):
            if not self._isManagedServer(server):
                continue
            for addrs in (server.addresses or {}).values():
                for addr in addrs:
                    ipAddr = addr.get("addr") or addr.get("address")
                    if ipAddr:
                        index[ipAddr] = server
        return index

    # ------------------------------------------------------------------
    # Floating IPs
    # ------------------------------------------------------------------

    def _allocateFloatingIp(self, server, privIp):
        """Allocate a new floating IP and bind it to `server`. Returns it or None."""
        fipNetId = self._resolveFloatingNetworkId()
        if not fipNetId:
            return None

        portId = networking.resolvePortIdForFixedIp(self.conn, server, privIp)
        if portId:
            fip = self.conn.network.create_ip(floating_network_id=fipNetId, port_id=portId)
            return getattr(fip, "floating_ip_address", None)

        # No port resolved: allocate the address detached, then let Nova bind it.
        fip = self.conn.network.create_ip(floating_network_id=fipNetId)
        pubIp = getattr(fip, "floating_ip_address", None)
        if pubIp:
            self.conn.compute.add_floating_ip_to_server(server, pubIp)
        return pubIp

    def _attachExistingFloatingIp(self, server, privIp, pubIp):
        """Bind an already allocated floating IP to `server`. Always returns `pubIp`."""
        portId = networking.resolvePortIdForFixedIp(self.conn, server, privIp) if privIp else None
        if not portId:
            return pubIp

        try:
            fip = self.conn.network.find_ip(pubIp)
            if fip:
                self.conn.network.update_ip(fip, port_id=portId)
        except Exception as exc:
            logger.warning("Failed to attach FIP %s via port update, falling back: %s", pubIp, exc)
            try:
                self.conn.compute.add_floating_ip_to_server(server, pubIp)
            except Exception as exc2:
                logger.error("Failed to attach FIP %s via legacy API: %s", pubIp, exc2)
        return pubIp

    def _ensureFloatingIp(self, server, privIp, requestedPubIp=None):
        """
        Ensure `server` ends up with a floating IP, and return it, or None.

        When `requestedPubIp` is set, that already allocated address is bound to
        the server; otherwise the floating IP the server already carries is
        reused, and a new one is allocated only as a last resort.
        This never raises: callers get None when no address could be obtained.
        """
        if not server:
            return None

        if requestedPubIp:
            return self._attachExistingFloatingIp(server, privIp, requestedPubIp)

        _, actualPubIp = self._getServerIps(server)
        if actualPubIp:
            return actualPubIp

        try:
            return self._allocateFloatingIp(server, privIp)
        except Exception as exc:
            logger.warning(
                "Failed to allocate a floating IP for server %s: %s",
                getattr(server, "id", "?"), exc,
            )
            return None

    # ------------------------------------------------------------------
    # Instance creation
    # ------------------------------------------------------------------

    def _resolveServerSpec(self, numCPU, gigaRAM):
        """
        Resolve the flavor, image, NIC and security groups shared by a batch.

        Done once up front rather than inside each worker: it turns N identical
        lookups into a single one, and leaves the threads with nothing to do but
        issue their own create request.
        """
        flavorName = self.instType.get(str(numCPU), {}).get(str(gigaRAM))
        if not flavorName:
            raise RuntimeError("No instance type for {} vCPU / {} GiB".format(numCPU, gigaRAM))

        flavor = self.conn.compute.find_flavor(flavorName)
        if not flavor:
            raise RuntimeError("Flavor not found: {}".format(flavorName))

        image = self.conn.compute.find_image(self.ami)
        if not image:
            raise RuntimeError("Image not found: {}".format(self.ami))

        nics = self._buildPrimaryNic()
        if not nics:
            raise RuntimeError("No primary NIC could be built (check interface_1/ network/ subnet config)")

        secGroups = []
        if isinstance(self.secuGrp, dict):
            for key in ["admin", "app"]:
                sg = self.secuGrp.get(key)
                if sg:
                    secGroups.append({"name": sg})

        return {
            "image_id": image.id,
            "flavor_id": flavor.id,
            "networks": nics,
            "security_groups": secGroups if secGroups else None,
            "key_name": self.keyPair,
            "user_data": self.userData,
            "metadata": {"cpu_count": str(numCPU)},
        }

    def _createServerOnly(self, serverSpec, name=None):
        """Send one create request, without waiting for ACTIVE. Runs in a worker thread."""
        serverName = "{}.{}".format(self.instName, name) if name else self.instName
        server = self.conn.compute.create_server(name=serverName, **serverSpec)
        return server.id

    def _deleteServerQuietly(self, serverId, reason):
        """Delete a server, reporting but never propagating a failure."""
        try:
            self.conn.compute.delete_server(serverId, ignore_missing=True)
            logger.info("Server %s deleted %s", serverId, reason)
        except Exception as exc:
            logger.error("Failed to delete server %s %s: %s", serverId, reason, exc)

    def _submitServerCreations(self, serverNames, serverSpec):
        """
        Fire every create request in parallel, without waiting for the servers.
        Returns a (createdIds, failures, firstError) triple.
        """
        maxWorkers = min(max(1, len(serverNames)), _MAX_PARALLEL_WORKERS)
        createdIds = []
        failures = 0
        firstError = None

        with ThreadPoolExecutor(max_workers=maxWorkers) as executor:
            futures = [
                executor.submit(self._createServerOnly, serverSpec, serverName)
                for serverName in serverNames
            ]
            for fut in as_completed(futures):
                try:
                    createdIds.append(fut.result())
                except Exception as err:
                    failures += 1
                    if firstError is None:
                        firstError = err
                    logger.error("Create request failed: %s", err)

        return createdIds, failures, firstError

    def _pollServers(self, serverIds):
        """Fetch the current state of `serverIds` with a single list call."""
        try:
            return {
                server.id: server
                for server in self.conn.compute.servers(details=True)
                if server.id in serverIds
            }
        except Exception as exc:
            logger.warning("Cannot poll server states, will retry: %s", exc)
            return {}

    def _awaitServers(self, createdIds, numCPU, gigaRAM, timeout, requestedIp=None):
        """
        Wait for the servers to reach ACTIVE and give each one a floating IP.
        Servers that end up in ERROR or exceed `timeout` are deleted.
        Returns a (results, failures) pair.
        """
        results = []
        failures = 0
        pending = set(createdIds)
        startTime = time.time()

        while pending and (time.time() - startTime) < timeout:
            for serverId, server in self._pollServers(pending).items():
                status = (getattr(server, "status", "") or "").upper()

                if status == "ACTIVE":
                    pending.discard(serverId)
                    privIp, actualPubIp = self._getServerIps(server)
                    pubIp = requestedIp or actualPubIp
                    if not pubIp or (requestedIp and requestedIp != actualPubIp):
                        pubIp = self._ensureFloatingIp(server, privIp, requestedIp)
                    logger.info(
                        "Created Instance: %s, %s, %s, %sVCPUs, %sG",
                        serverId, privIp, pubIp, numCPU, gigaRAM,
                    )
                    results.append({"id": serverId, "ip": pubIp})

                elif status == "ERROR":
                    pending.discard(serverId)
                    failures += 1
                    logger.error("Server %s in ERROR state", serverId)
                    self._deleteServerQuietly(serverId, "after ERROR state")

            if pending:
                time.sleep(_POLL_INTERVAL)

        for serverId in pending:
            failures += 1
            logger.warning("Server %s creation timed out after %ss", serverId, timeout)
            self._deleteServerQuietly(serverId, "after creation timeout")

        return results, failures

    def _createInstances(self, serverNames, numCPU, gigaRAM, timeoutSeconds=None,
                         requestedIp=None, wait=True):
        """
        Create one server per entry in `serverNames`.

        With `wait`, the servers are polled until they are usable and `results`
        holds one {id, ip} dict per server that reached ACTIVE. Without it, the
        call returns as soon as the requests are accepted and the addresses are
        not known yet; reconcile() finishes the job on a later iteration.

        Returns a (results, firstError) pair.
        """
        if not self.conn:
            raise RuntimeError("Provider not configured")
        if not serverNames:
            return [], None

        timeout = int(
            timeoutSeconds if timeoutSeconds is not None else _DEFAULT_CREATE_TIMEOUT
        )
        try:
            serverSpec = self._resolveServerSpec(numCPU, gigaRAM)
        except Exception as err:
            # Reported like a create failure so the batch path keeps returning an
            # empty list while createInstance() can still re-raise the cause.
            logger.error("Cannot resolve the server specification: %s", err)
            return [], err

        createdIds, failures, firstError = self._submitServerCreations(
            serverNames, serverSpec
        )

        if not wait:
            logger.info(
                "OpenStack batch create submitted: requested=%s, started=%s, failed=%s",
                len(serverNames), len(createdIds), failures,
            )
            return [{"id": serverId, "ip": None} for serverId in createdIds], firstError

        results = []
        if createdIds:
            results, waitFailures = self._awaitServers(
                createdIds, numCPU, gigaRAM, timeout, requestedIp
            )
            failures += waitFailures

        logger.info(
            "OpenStack batch create done: requested=%s, started=%s, active=%s, failed=%s",
            len(serverNames), len(createdIds), len(results), failures,
        )
        return results, firstError

    def createInstance(self, numCPU, gigaRAM, name=None, ip=None):
        results, firstError = self._createInstances(
            [name], numCPU, gigaRAM, requestedIp=ip
        )
        if results:
            return results[0]
        if firstError is not None:
            raise firstError
        raise RuntimeError(
            "Instance {} never reached ACTIVE state".format(name or self.instName)
        )

    def createInstancesParallel(self, count, numCPU, gigaRAM, name=None, timeoutSeconds=None):
        """
        Fire the creations and return without waiting for the servers to boot.

        Waiting here used to freeze every scaling decision for as long as the
        slowest instance took to appear, so a single stuck creation blinded the
        scaler for minutes. What the requests leave behind, floating IPs to
        attach and servers that will never boot, is settled by reconcile().
        """
        serverNames = [
            "{}-{}".format(name, i) if name else None
            for i in range(max(0, int(count)))
        ]
        results, _ = self._createInstances(serverNames, numCPU, gigaRAM, wait=False)
        return results

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    def reconcile(self, timeoutSeconds=None):
        """
        Finish what fire-and-forget creation left pending.

        Servers that have become ACTIVE are given the floating IP that the
        creation path no longer waits around to attach, and those that will never
        make it, in ERROR or still building past the timeout, are removed so they
        stop holding quota.
        """
        if not self.conn:
            return

        timeout = int(
            timeoutSeconds if timeoutSeconds is not None else _DEFAULT_CREATE_TIMEOUT
        )
        try:
            servers = list(self.conn.compute.servers(details=True))
        except Exception as exc:
            logger.warning("Cannot list servers for reconciliation: %s", exc)
            return

        attached = 0
        removed = 0

        for server in servers:
            if not self._isManagedServer(server):
                continue
            status = (getattr(server, "status", "") or "").upper()

            if status == "ERROR":
                self._deleteServerQuietly(server.id, "after ERROR state")
                removed += 1
                continue

            if status == "BUILD":
                age = self._serverAgeSeconds(server)
                if age is not None and age > timeout:
                    logger.warning(
                        "Server %s still building after %ss, removing it",
                        server.id, int(age),
                    )
                    self._deleteServerQuietly(server.id, "after creation timeout")
                    removed += 1
                continue

            if status != "ACTIVE":
                continue

            privIp, pubIp = self._getServerIps(server)
            if pubIp or not privIp:
                continue

            try:
                newIp = self._ensureFloatingIp(server, privIp)
            except Exception as exc:
                logger.error("Cannot give server %s a floating IP: %s", server.id, exc)
                continue
            if newIp:
                logger.info("Attached floating IP %s to server %s", newIp, server.id)
                attached += 1

        if attached or removed:
            logger.info(
                "Reconciliation done: floating_ips_attached=%s, servers_removed=%s",
                attached, removed,
            )

    # ------------------------------------------------------------------
    # Instance destruction
    # ------------------------------------------------------------------

    def _releaseFloatingIp(self, pubIp):
        """Return a floating IP to the pool, best-effort."""
        try:
            fip = self.conn.network.find_ip(pubIp)
            if fip:
                self.conn.network.delete_ip(fip)
        except Exception as exc:
            logger.warning("Failed to release floating IP %s: %s", pubIp, exc)

    def destroyInstances(self, ipList):
        if not self.conn:
            return

        serversByIp = self._buildServersByIpIndex()
        pendingVolumeIds = []
        logger.info(
            "Destroy requested for %s IP(s); managed servers indexed=%s; volume deletion=%s",
            len(ipList or []),
            len(serversByIp),
            "ENABLED" if self.deleteVolumesOnDestroy else "DISABLED",
        )

        for ip in ipList:
            if not ip:
                logger.warning("destroyInstances called with None/empty IP, skipping")
                continue

            server = serversByIp.get(ip)
            if not server:
                logger.warning("No server found for IP %s, skipping", ip)
                continue

            instanceId = server.id
            privIp, pubIp = self._getServerIps(server)

            try:
                isPrivate = ip_address(ip).is_private
            except (ValueError, TypeError):
                isPrivate = False

            if isPrivate:
                privIp = ip
            else:
                pubIp = ip

            if self.deleteVolumesOnDestroy:
                volumeIds = volumes.getServerVolumeIds(self.conn, server)
                pendingVolumeIds.extend(volumeIds)
                logger.info(
                    "Collected %s volume(s) for server %s before deletion: %s",
                    len(volumeIds), instanceId, volumeIds,
                )

            if pubIp:
                try:
                    self.conn.compute.remove_floating_ip_from_server(server, pubIp)
                except Exception as exc:
                    logger.debug("Failed to disassociate FIP %s from server %s: %s", pubIp, instanceId, exc)

            try:
                self.conn.compute.delete_server(server, ignore_missing=True)
            except Exception as exc:
                logger.error("Failed to delete server %s: %s", instanceId, exc)

            if pubIp:
                self._releaseFloatingIp(pubIp)

            logger.info("Deleted Instance: %s, %s, %s", instanceId, privIp, pubIp)

        if not self.deleteVolumesOnDestroy:
            logger.info("Volume deletion skipped because delete_volumes_on_destroy is disabled")
        elif pendingVolumeIds:
            volumes.deleteVolumes(self.conn, pendingVolumeIds)
        else:
            logger.info("Volume deletion enabled but no attached volumes were collected")
