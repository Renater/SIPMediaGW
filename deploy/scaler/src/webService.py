#!/usr/bin/env python
import importlib
import logging
import sys
import os
import inspect
import re
import web
import json
from manageInstance import ManageInstance
from ScalerSIP  import ScalerSIP
from ScalerMedia import ScalerMedia

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

scalerConfigFile = os.environ.get("SCALER_CONFIG_FILE", "scaler.json")
cspName =  os.environ.get("CSP_NAME", "outscale")
cspConfigFile = os.environ.get("CSP_CONFIG_FILE", "sipmediagw_sample.json")
cspProfile = os.environ.get("CSP_PROFILE", "visio-dev")

scalerType = os.environ.get("SCALER_TYPE", "SIP")


def _importCspModule():
    """Import the provider module named by CSP_NAME."""
    providersDir = "{}/providers".format(os.path.dirname(os.path.abspath(__file__)))
    if providersDir not in sys.path:
        sys.path.append(providersDir)

    # Legacy providers are plain modules sitting inside their own directory, and
    # some of them import siblings by bare name, so that directory must be on the
    # path too. Packages such as openstackProvider are found via providersDir.
    legacyDir = "{}/{}".format(providersDir, cspName)
    if os.path.isdir(legacyDir) and legacyDir not in sys.path:
        sys.path.append(legacyDir)

    return importlib.import_module(cspName)


def _findCspClass(mod):
    """Return the single ManageInstance subclass exported by a provider module."""
    candidates = [
        cls
        for _, cls in inspect.getmembers(mod, inspect.isclass)
        if issubclass(cls, ManageInstance) and cls is not ManageInstance
    ]
    if not candidates:
        raise RuntimeError(
            "Provider '{}' exports no ManageInstance subclass".format(cspName)
        )
    if len(candidates) > 1:
        raise RuntimeError(
            "Provider '{}' exports several ManageInstance subclasses: {}".format(
                cspName, [cls.__name__ for cls in candidates]
            )
        )
    return candidates[0]


def _buildScaler():
    # Build the CSP provider + Scaler once for the process lifetime. Rebuilding
    # them on every HTTP request leaks provider connections (OpenStack especially).
    mod = _importCspModule()
    cspObj = _findCspClass(mod)
    logger.info("Loaded CSP provider %s from '%s'", cspObj.__name__, cspName)

    csp = cspObj(cspProfile)

    if scalerType.upper() == "SIP":
        scaler = ScalerSIP(csp)
    else:
        scaler = ScalerMedia(csp)

    scaler.configure("config/{}".format(scalerConfigFile))
    return scaler


_scaler = _buildScaler()


def authorize(func):
    def inner(*args, **kwargs):
        try:
            token = args[0].scaler.config['api_token']
        except:
            return json.dumps({'Error': 'internal error'})
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        authReq = False
        if auth is None:
            authReq = True
        else:
            auth = re.sub('^Bearer ', '', auth)
            if auth != token:
                authReq = True
        if not authReq:
            return func(*args, **kwargs)
        else:
            web.header('WWW-Authenticate', 'Bearer error="invalid_token"')
            web.ctx.status = '401 Unauthorized'
            return json.dumps({'Error': 'authorization error'})
    return inner

class Scaling:
    def __init__(self) -> None:
        self.scaler = _scaler

    @authorize
    def GET(self, args=None):
        data = web.input()
        initData = { scalerType.lower() : {'main_app' : self.scaler.config['main_app'],
                                           'assets_url' : self.scaler.config['assets_url']},
                     'gw_name_prefix': self.scaler.config.get('gw_name_prefix')}
        self.scaler.csp.configureInstance("{}/providers/{}/config/{}".format(
            os.path.dirname(os.path.abspath(__file__)), cspName, cspConfigFile), initData)
        if 'auto' in data.keys():
            try:
                self.scaler.reconcile()
                self.scaler.cleanup()
                if self.scaler.scale() == 0:
                    web.ctx.status = '200 OK'
                    return json.dumps({"status": "success", "message": "The scaler iteration succeed"})
            except Exception as error:
                return "The scaler iteration failed: {}".format(error)
        if 'up' in data.keys():
            try:
                instRes = self.scaler.csp.createInstance(
                    '4','4', name=self.scaler.config.get('gw_name_prefix') or 'mediagw'
                )
                web.ctx.status = '200 OK'
                return json.dumps({"status": "success", "instance": instRes})
            except Exception as error:
                web.ctx.status = '500 Internal Server Error'
                return json.dumps({"Error": "Instance creation failed: {}".format(error)})



urls = ("/scale", "Scaling")

app = web.application(urls, globals())

if __name__ == "__main__":
    app.run()
