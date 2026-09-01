# Scaler — documentation

Summary
- Scaler is a Python class that manages auto-scaling of gateways (GW).
- It relies on a cloud provider interface (self.csp) and databases to decide when to create or destroy instances.

- The SIP sclaler monitors Kamailio registrations to determine load and capacity.
- The Media scaler uses Redis to track gateway states and room assignments.


Prerequisites
- Python 3.x
- Python packages: mysql-connector-python, python-dateutil
- Network access to the Kamailio database
- A Redis server for Media scaler
- A CSP object implementing ManageInstance (`src/manageInstance.py`):
  - configureInstance, enumerateInstances, createInstance, destroyInstances
  - Optional overrides: createInstancesParallel, reconcile, close
- Providers: Outscale (`CSP_NAME=outscale`) or OpenStack (`CSP_NAME=openstackProvider`)

Location
- Source: deploy/scaler/Scaler.py
- This doc: deploy/scaler/README.md

Example configuration (JSON)
```json
{
  "gw_name_prefix": "gw-",
  "sip_db": {
    "host": "127.0.0.1",
    "root_password": "secret"
  },
  "cpu_per_gw": 4,
  "auto_scale_threshold": {
    "default": {
      "00:00:00": {"unlockedMin": 2, "loadMax": 0.7},
      "08:00:00": {"unlockedMin": 10, "loadMax": 0.75}
    },
    "saturday": {
      "00:00:00": {"unlockedMin": 1, "maxGw": 1, "loadMax": 1.0}
    },
    "sunday": {
      "00:00:00": {"unlockedMin": 1, "maxGw": 1, "loadMax": 1.0}
    }
  }
}
```

Public methods
- configure(configFile)
  - Load JSON config into self.config.
- upScale(numCPU)
  - Create instances to allocate the requested number of CPUs using self.csp.instType.
- downScale(numGW)
  - Mark SIP registrations (locked=1, to_stop=1) and destroy instances when safe.
- cleanup()
  - Destroy instances marked to_stop=1 and remove instances without a public IP after a timeout.
- scale(scaleTime=None, incallsNum=None)
  - Compute current and target capacity using database queries and thresholds, then call upScale/downScale.

Important notes and known issues
- configure currently opens files without using a context manager — consider with open(...) for safety.
- upScale assumes self.csp.instType contains usable keys and may raise an error if empty.
- downScale defines ipList inside the try block — an exception before definition will cause an UnboundLocalError.
- SQL fragments are concatenated into queries; this is fragile and reduces readability.
- cursor.rowcount may behave differently depending on the MySQL driver.
- Replace print() calls with logging for production use.


Recommended improvements
- Use with open(...) to load JSON safely.
- Initialize ipList before the try block.
- Handle empty instType (cpuRange) in upScale.
- Refactor SQL queries to avoid fragile concatenation and improve clarity.
- Add unit tests for capacity calculation and scaling decisions.

OpenStack provider
- Package: `src/providers/openstackProvider/` (provider, networking, volumes, errors).
- Copy `config/sipmediagw.json.example` to `sipmediagw.json` (gitignored) and fill credentials.
- Set `CSP_NAME=openstackProvider`, `CSP_CONFIG_FILE=sipmediagw.json`, `CSP_PROFILE` to a key under `profile`.
- `initData["gw_name_prefix"]` (from `scaler.json`) is required: only servers named
  `<provider name>.<gw_name_prefix>...` are managed (fail-closed if missing).
- `createInstance` waits for a public IP (manual `?up`). Batch create is available on
  the provider as `createInstancesParallel`; `reconcile()` attaches missing floating
  IPs and drops `ERROR` / stuck `BUILD` servers. The default `scale()` path still
  calls `createInstance` one by one.

Contact
- Refer to the repo owner or infra team for implementation-specific questions.