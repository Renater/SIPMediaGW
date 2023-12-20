import base64
import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import urllib.parse
from dataclasses import InitVar, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, Union, cast

import defusedxml.ElementTree as ET
import fire
import requests
import xmltodict
from requests.models import Request, Response
from typing_extensions import TypedDict

CANONICAL_URI = "/"
CONFIGURATION_FILE = "config.json"
CONFIGURATION_FOLDER = ".osc"
CONFIGURATION_FOLDER_DEPRECATED = ".osc_sdk"
CONF_PATHS: List[Path] = [
    Path.home() / CONFIGURATION_FOLDER / CONFIGURATION_FILE,
    Path.home() / CONFIGURATION_FOLDER_DEPRECATED / CONFIGURATION_FILE,
]
DEFAULT_METHOD = "POST"
DEFAULT_PROFILE = "default"
DEFAULT_REGION = "eu-west-2"
DEFAULT_VERSION = datetime.date.today().strftime("%Y-%m-%d")

DEFAULT_HOST = "outscale.com"

METHODS_SUPPORTED = {"GET", "POST"}
SDK_VERSION = "1.11.0"
SSL_VERIFY = True
SUCCESS_CODES = {200, 201, 202, 203, 204}
USER_AGENT = "osc_sdk/" + SDK_VERSION

logger = logging.getLogger("osc_sdk")


CallParameters = Dict[str, Any]
EncodedCallParameters = Optional[str]
Headers = Tuple[str, str, Dict[str, str]]
# This is a workaround avoiding Fire to parse password option as python
# See #238
PASSWORD_ARG = None

NO_AUTH_CALLS: Dict[str, Set[str]] = {
    "api": {
        "ReadFlexibleGpuCatalog",
        "ReadLocations",
        "ReadNetAccessPointServices",
        "ReadProductTypes",
        "ReadPublicIpRanges",
        "ReadRegions",
        "ReadVmTypes",
        "ResetAccountPassword",
        "SendResetPasswordEmail",
        "ReadPublicCatalog",
    },
    "icu": {
        "AuthenticateAccount",
        "ResetAccountPassword",
        "SendResetPasswordEmail",
        "ReadPublicCatalog",
        "CheckSignature",
    },
    "fcu": {
        "DescribeRegions",
        "ReadPublicIpRanges",
    },
}

dir_path = os.path.join(os.path.dirname(__file__))
BASH_COMPLETION_PATH = os.path.abspath("{}/osc-cli-completion.bash".format(dir_path))


class Configuration(TypedDict):
    method: str
    access_key: str
    secret_key: str
    version: str
    https: bool
    region_name: str
    ssl_verify: bool
    client_certificate: str
    endpoint: str
    host: str


DEFAULT_CONF = cast(
    Configuration,
    {
        "method": "POST",
        "https": True,
        "region_name": DEFAULT_REGION,
        "ssl_verify": True,
        "version": DEFAULT_VERSION,
        "host": DEFAULT_HOST,
    },
)


class PasswordParams(TypedDict, total=False):
    AuthenticationMethod: str
    Login: Optional[str]
    Password: Optional[str]


class ResponseContent(Dict):
    requestid: str


class Tag(TypedDict):
    Name: str
    Values: List[str]


@dataclass
class OscApiException(Exception):
    http_response: InitVar[Response]

    status_code: int = field(init=False)
    error_code: Optional[str] = field(default=None, init=False)
    message: Optional[str] = field(default=None, init=False)
    code_type: Optional[str] = field(default=None, init=False)
    request_id: Optional[str] = field(default=None, init=False)

    def __post_init__(self, http_response: Response):
        super().__init__()
        self.status_code = http_response.status_code
        # Set error details
        self._set(http_response)

    def __str__(self) -> str:
        return (
            f"Error --> status = {self.status_code}, "
            f"code = {self.error_code}, "
            f'{"code_type = " if self.code_type is not None else ""}'
            f'{self.code_type + ", " if self.code_type is not None else ""}'
            f"Reason = {self.message}, "
            f"request_id = {self.request_id}"
        )

    def _set(self, http_response: Response):
        content = http_response.content.decode()
        # In case it is JSON error format
        try:
            error = json.loads(content)
        except json.JSONDecodeError:
            pass
        else:
            if "__type" in error:
                self.error_code = error.get("__type")
                self.message = error.get("message")
                self.request_id = http_response.headers.get("x-amz-requestid")
            else:
                self.request_id = (error.get("ResponseContext") or {}).get("RequestId")
                errors = error.get("Errors")
                if errors:
                    error = errors[0]
                    self.error_code = error.get("Code")
                    self.message = error.get("Type")
                    if error.get("Details"):
                        self.code_type = self.message
                        self.message = error.get("Details")
                    else:
                        self.code_type = None
            return

        # In case it is XML format
        try:
            error = ET.fromstring(content)
        except ET.ParseError:
            return
        else:
            for key, attr in [
                ("Code", "error_code"),
                ("Message", "message"),
                ("RequestId", "request_id"),
                ("RequestID", "request_id"),
            ]:
                value = next(
                    (x.text for x in error.iter() if x.tag.endswith(key)), None
                )
                if value:
                    setattr(self, attr, value)


@dataclass
class ApiCall:
    profile: str = DEFAULT_PROFILE
    login: Optional[str] = None
    password: Optional[str] = None
    authentication_method: Optional[str] = None

    API_NAME: str = field(default="", init=False)
    CONTENT_TYPE = "application/x-www-form-urlencoded"
    REQUEST_TYPE = "aws4_request"
    SIG_ALGORITHM = "AWS4-HMAC-SHA256"
    SIG_TYPE = "AWS4"

    response: Optional[ResponseContent] = field(default=None, init=False)
    date: Optional[str] = field(default=None, init=False)
    datestamp: Optional[str] = field(default=None, init=False)

    endpoint: Optional[str] = None
    method: str = DEFAULT_METHOD
    host: str = ""
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    version: str = DEFAULT_VERSION
    https: bool = True
    protocol: str = ""
    region_name: str = DEFAULT_REGION
    ssl_verify: bool = SSL_VERIFY
    client_certificate: Optional[str] = None

    def __post_init__(self):
        if not self.API_NAME:
            raise RuntimeError("API_NAME is required and should not be empty")

        if self.method not in METHODS_SUPPORTED:
            raise Exception(
                f"Wrong method {self.method}. Supported: {METHODS_SUPPORTED}."
            )

        self.protocol = "https" if self.https else "http"

        if self.host and not self.endpoint:
            self.endpoint = ".".join([self.API_NAME, self.region_name, self.host])

        if not self.endpoint:
            raise RuntimeError("No endpoint found")

        parsed_url = urllib.parse.urlparse(self.endpoint)
        if parsed_url.scheme:
            self.host = parsed_url.netloc
        else:
            self.host = str(self.endpoint)
            self.endpoint = f"{self.protocol}://{self.endpoint}"

    def check_authentication_options(self):
        if self.authentication_method not in {"accesskey", "password", "none"}:
            raise RuntimeError(
                "Unsupported authentication method (accesskey, password or none)"
            )
        if self.authentication_method == "accesskey":
            if self.access_key is None:
                raise RuntimeError("Missing Access Key for authentication")
            if self.secret_key is None:
                raise RuntimeError("Missing Secret Key for authentication")
        if self.authentication_method == "password":
            if self.login is None:
                raise RuntimeError("Missing login for authentication")
            if self.password is None:
                raise RuntimeError("Missing password for authentication")

    def set_datestamp(self):
        date = datetime.datetime.utcnow()
        self.date = date.strftime("%Y%m%dT%H%M%SZ")
        self.datestamp = date.strftime("%Y%m%d")

    def get_url(
        self, call: str, encoded_request_params: EncodedCallParameters = None
    ) -> str:
        value = self.endpoint if self.endpoint else ""
        if self.method == "GET":
            value += f"?{encoded_request_params}"
        return value

    def get_canonical_uri(self, _: str) -> str:
        return CANONICAL_URI

    def get_authorization_header(
        self, canonical_request: str, signed_headers: str
    ) -> str:
        if self.date is None or self.datestamp is None:
            raise RuntimeError("Date has nos been set up")
        if not self.secret_key:
            raise RuntimeError("Secret key is needed to authorize call")

        credentials = [
            self.datestamp,
            self.region_name,
            self.API_NAME,
            self.REQUEST_TYPE,
        ]
        credential_scope = "/".join(credentials)
        string_to_sign = "\n".join(
            [
                self.SIG_ALGORITHM,
                self.date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        key = (self.SIG_TYPE + self.secret_key).encode("utf-8")
        for msg in credentials:
            key = hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
        signature = hmac.new(
            key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        return (
            f"{self.SIG_ALGORITHM} "
            f"Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

    def get_password_params(self) -> PasswordParams:
        return {
            "AuthenticationMethod": "password",
            "Login": self.login,
            "Password": self.password,
        }

    def get_response(self, http_response: Response):
        raise NotImplementedError

    def get_parameters(
        self, data: Union[CallParameters, List[CallParameters]], prefix: str = ""
    ) -> CallParameters:
        ret = {}
        if isinstance(data, list):
            if prefix:
                prefix += "."
            for i, value in enumerate(data, start=1):
                ret.update(self.get_parameters(value, prefix + str(i)))
            return ret
        if isinstance(data, dict):
            if prefix:
                prefix += "."
            for key, value in data.items():
                ret.update(self.get_parameters(value, prefix + key))
            return ret
        if data is not None:
            if data == "":
                return {prefix: ""}
            return {prefix: str(data)}
        else:
            raise RuntimeError("Parameters could not be None")

    def make_request(self, call: str, **kwargs: CallParameters):
        self.set_datestamp()

        # Calculate request params
        request_params = self.get_parameters(data=kwargs)

        if self.authentication_method is None:
            if call_need_auth(self.API_NAME, call):
                self.authentication_method = "accesskey"
            else:
                self.authentication_method = "none"

        self.check_authentication_options()

        if self.authentication_method == "password":
            request_params.update(self.get_password_params())

        request_params["Action"] = call
        if "Version" not in request_params:
            request_params["Version"] = self.version
        encoded_request_params = cast(
            EncodedCallParameters, urllib.parse.urlencode(request_params)
        )

        # Calculate URL before encoded_request_params value is modified
        url = self.get_url(call, encoded_request_params)

        if self.method == "GET":
            if encoded_request_params is None:
                raise RuntimeError("Encoded call parameters could not be None")
            headers = {
                "host": self.host,
                "x-amz-date": self.date,
            }
            payload_hash = hashlib.sha256("".encode("utf-8")).hexdigest()
            canonical_params = encoded_request_params
            encoded_request_params = None
        elif encoded_request_params is not None:
            headers = {
                "content-type": self.CONTENT_TYPE,
                "host": self.host,
                "x-amz-date": self.date,
                "x-amz-target": f'{self.API_NAME}_{datetime.date.today().strftime("%Y%m%d")}.{call}',
            }

            payload_hash = hashlib.sha256(
                encoded_request_params.encode("utf-8")
            ).hexdigest()
            canonical_params = ""
        else:
            raise RuntimeError("Encoded call parameters could not be None")

        canonical_headers = "".join(f"{k}:{v}\n" for k, v in headers.items())
        signed_headers = ";".join(headers)
        canonical_request = "\n".join(
            [
                self.method,
                self.get_canonical_uri(call),
                canonical_params,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        headers.update({"User-agent": USER_AGENT})
        if self.authentication_method == "accesskey":
            headers.update(
                {
                    "Authorization": self.get_authorization_header(
                        canonical_request,
                        signed_headers,
                    )
                }
            )

        self.response = self.get_response(
            requests.request(
                cert=self.client_certificate,
                data=encoded_request_params,
                headers=headers,
                method=self.method,
                url=url,
                verify=self.ssl_verify,
            )
        )


class XmlApiCall(ApiCall):
    def get_response(self, http_response: Response) -> Union[str, ResponseContent]:
        if http_response.status_code not in SUCCESS_CODES:
            raise OscApiException(http_response)
        try:
            return cast(ResponseContent, xmltodict.parse(http_response.content))
        except Exception:
            return f"Unable to parse response: '{http_response.text}'"


class FcuCall(XmlApiCall):
    API_NAME = "fcu"


class LbuCall(XmlApiCall):
    API_NAME = "lbu"

    def get_parameters(
        self, data: Union[CallParameters, List[CallParameters]], prefix: str = ""
    ) -> CallParameters:
        ret = {}
        if isinstance(data, list):
            if prefix:
                prefix += ".member."
            i = 1
            for value in data:
                ret.update(self.get_parameters(value, prefix + str(i)))
            return ret
        if isinstance(data, dict):
            if prefix:
                prefix += "."
            for key, value in data.items():
                ret.update(self.get_parameters(value, prefix + key))
            return ret
        if data is not None:
            if data == "":
                return {prefix: ""}
            return {prefix: str(data)}
        else:
            raise RuntimeError("Parameters could not be None")


class EimCall(XmlApiCall):
    API_NAME = "eim"

    def get_parameters(
        self, data: Union[CallParameters, List[CallParameters]], _: str = ""
    ) -> CallParameters:
        if isinstance(data, dict):
            policy_document = data.get("PolicyDocument")
            if policy_document:
                data["PolicyDocument"] = json.dumps(policy_document)
        return data  # type: ignore


class JsonApiCall(ApiCall):
    SERVICE = ""
    CONTENT_TYPE = "application/x-amz-json-1.1"

    def get_parameters(
        self, data: Union[CallParameters, List[CallParameters]], _: str = ""
    ) -> CallParameters:
        if not isinstance(data, dict):
            raise RuntimeError("Parameters lists are not supported")
        return data

    def get_response(self, http_response: Response) -> ResponseContent:
        if http_response.status_code not in SUCCESS_CODES:
            raise OscApiException(http_response)

        return json.loads(http_response.text)

    def build_headers(self, target: str, json_parameters: str) -> Headers:
        if self.date is None:
            raise RuntimeError("Date has nos been set up")

        signed_headers = "host;x-amz-date;x-amz-target"
        canonical_headers = (
            f"host:{self.host}\n" f"x-amz-date:{self.date}\n" f"x-amz-target:{target}\n"
        )
        headers = {
            "content-type": self.CONTENT_TYPE,
            "x-amz-date": self.date,
            "x-amz-target": target,
            "User-agent": USER_AGENT,
            "content-length": str(len(json_parameters)),
        }
        return signed_headers, canonical_headers, headers

    def make_request(self, call: str, **kwargs: CallParameters):
        self.set_datestamp()

        request_params = self.get_parameters(kwargs, call)

        if self.authentication_method is None:
            if call_need_auth(self.API_NAME, call):
                self.authentication_method = "accesskey"
            else:
                self.authentication_method = "none"

        self.check_authentication_options()

        if self.authentication_method == "password":
            request_params.update(self.get_password_params())

        json_params = json.dumps(request_params)

        target = ".".join([self.SERVICE, call])

        signed_headers, canonical_headers, headers = self.build_headers(
            target, json_params
        )

        canonical_request = "\n".join(
            [
                "POST",
                self.get_canonical_uri(call),
                "",
                canonical_headers,
                signed_headers,
                hashlib.sha256(json_params.encode("utf-8")).hexdigest(),
            ]
        )

        if self.authentication_method == "accesskey":
            headers["Authorization"] = self.get_authorization_header(
                canonical_request,
                signed_headers,
            )

        self.response = self.get_response(
            requests.request(
                cert=self.client_certificate,
                data=json_params,
                headers=headers,
                method=self.method,
                url=self.get_url(call),
                verify=self.ssl_verify,
            )
        )


class IcuCall(JsonApiCall):
    API_NAME = "icu"
    SERVICE = "TinaIcuService"
    FILTERS_NAME_PATTERN = re.compile("^Filters.([0-9]*).Name$")
    FILTERS_VALUES_STR = "^Filters.%s.Values.[0-9]*$"

    def get_parameters(
        self, data: Union[CallParameters, List[CallParameters]], prefix: str = ""
    ) -> CallParameters:
        if not isinstance(data, dict):
            raise RuntimeError("Parameters lists are not supported")

        if "AuthenticationMethod" in data:
            self.authentication_method = data["AuthenticationMethod"]
            if "Login" in data:
                self.login = data["Login"]
            if "Password" in data:
                self.password = data["Password"]
        # Specific to ICU
        if (
            self.authentication_method == "accesskey"
            or self.authentication_method == None
        ):
            data.update({"AuthenticationMethod": "accesskey"})

        filters = self.get_filters(data)
        data = {k: v for k, v in data.items() if not k.startswith("Filters.")}
        return {"Action": prefix, "Filters": filters, "Version": self.version, **data}

    def get_filters(self, data: CallParameters) -> List[Tag]:
        filters = []
        for k, v in data.items():
            match = re.search(self.FILTERS_NAME_PATTERN, k)
            if match:
                value_pattern = re.compile(self.FILTERS_VALUES_STR % match.group(1))
                values = [v for k, v in data.items() if re.match(value_pattern, k)]
                if values:
                    filters.append(
                        cast(
                            Tag,
                            {
                                "Name": v,
                                "Values": values,
                            },
                        )
                    )
        return filters


class DirectLinkCall(JsonApiCall):
    API_NAME = "directlink"
    SERVICE = "OvertureService"

    def get_response(self, http_response: Response) -> ResponseContent:
        if http_response.status_code not in SUCCESS_CODES:
            raise OscApiException(http_response)

        res = json.loads(http_response.text)
        res["requestid"] = http_response.headers["x-amz-requestid"]
        return res


class OKMSCall(JsonApiCall):
    API_NAME = "kms"
    SERVICE = "TrentService"


class OSCCall(JsonApiCall):
    API_NAME = "api"
    CONTENT_TYPE = "application/json"
    REQUEST_TYPE = "osc4_request"
    SIG_ALGORITHM = "OSC4-HMAC-SHA256"
    SIG_TYPE = "OSC4"
    SERVICE = "OutscaleService"

    def get_parameters(
        self, data: Union[CallParameters, List[CallParameters]], prefix: str = ""
    ) -> CallParameters:
        if not isinstance(data, dict):
            raise RuntimeError("Parameters lists are not supported")

        parameters = cast(CallParameters, {})  # type: ignore
        for k, v in data.items():
            self.format_data(parameters, k, v)
        return parameters

    def format_data(self, parameters: CallParameters, key: str, value: str):
        if "." in key:
            head_key, queue_key = key.split(".", 1)
            parameters.setdefault(head_key, {})
            self.format_data(parameters[head_key], queue_key, value)
        else:
            parameters[key] = (
                value[1:-1].split(",")
                if isinstance(value, str) and value.startswith("[")
                else value
            )

    def get_canonical_uri(self, call: str) -> str:
        return f"/{self.API_NAME}/latest/{call}"

    def get_url(
        self, call: str, encoded_request_params: EncodedCallParameters = None
    ) -> str:
        return "/".join([str(self.endpoint), self.get_canonical_uri(call)])

    def get_password_params(self) -> PasswordParams:
        # Don't put any auth parameters in body
        return {}

    def build_basic_auth(self) -> Dict[str, str]:
        if self.authentication_method == "password":
            creds = f"{self.login}:{self.password}"
            basic_auth = "Basic {}".format(
                base64.urlsafe_b64encode(creds.encode("utf-8")).decode("utf-8")
            )
            return {"Authorization": basic_auth}
        return {}

    def build_headers(self, target: str, _) -> Headers:
        if self.date is None:
            raise RuntimeError("Date has nos been set up")

        signed_headers = "host;x-osc-date;x-osc-target"
        canonical_headers = (
            f"host:{self.host}\n" f"x-osc-date:{self.date}\n" f"x-osc-target:{target}\n"
        )
        headers = {
            "Content-Type": self.CONTENT_TYPE,
            "User-agent": USER_AGENT,
            "X-Osc-Date": self.date,
            "x-osc-target": target,
        }

        headers.update(self.build_basic_auth())
        return signed_headers, canonical_headers, headers


def patch_conf(conf: Configuration, endpoint: Optional[str] = None) -> Configuration:
    if endpoint:
        conf["endpoint"] = endpoint
    return conf


def get_conf(profile: str) -> Configuration:
    # Check which conf_path is used.
    conf_path = next((path for path in CONF_PATHS if path.exists()), None)

    if not conf_path:
        return DEFAULT_CONF

    json_profiles = json.loads(conf_path.read_text())
    # convert region to region_name in json to fit Mapping
    for v in json_profiles:
        json_profile = json_profiles[v]
        if "region" in json_profile:

            # use default stuffs only when "region" is use
            # to keep region_name format retrocompatible
            if not "host" in json_profile and not "endpoint" in json_profile:
                json_profile["host"] = DEFAULT_HOST
            if not "https" in json_profile:
                json_profile["https"] = True

            if not "region_name" in json_profile:
                json_profile["region_name"] = json_profile["region"]
            del json_profile["region"]
    conf = cast(Mapping[str, Configuration], json_profiles)
    try:
        return conf[profile]
    except KeyError:
        return DEFAULT_CONF


def call_need_auth(service: str, call: str) -> bool:
    return call not in NO_AUTH_CALLS.get(service, set())


def api_connect(
    service: str,
    call: str,
    profile: str = DEFAULT_PROFILE,
    login: Optional[str] = None,
    endpoint: Optional[str] = None,
    password: Optional[str] = None,
    authentication_method: Optional[str] = None,
    bash_completion: bool = False,
    version: bool = False,
    config_path: Optional[str] = None,
    **kwargs: CallParameters,
):

    calls = {
        "api": OSCCall,
        "directlink": DirectLinkCall,
        "eim": EimCall,
        "fcu": FcuCall,
        "icu": IcuCall,
        "lbu": LbuCall,
        "okms": OKMSCall,
    }

    if config_path is not None:
        global CONF_PATHS
        path = Path(config_path)
        if path.exists() is False:
            print("cannot find ", path, " use default path")
        else:
            CONF_PATHS = [path]

    handler = calls[service](
        profile,
        login,
        PASSWORD_ARG,
        authentication_method,
        **patch_conf(get_conf(profile), endpoint),
    )

    handler.make_request(call, **kwargs)
    if handler.response:
        print(json.dumps(handler.response, indent=4))


def main():
    argc = len(sys.argv)
    argv = sys.argv

    if argc > 1:
        for i in range(1, argc):
            a = argv[i]
            if a == "--password" and i + 1 < argc:
                global PASSWORD_ARG
                PASSWORD_ARG = argv[i + 1]
            elif a == "--bash_completion":
                f = open(BASH_COMPLETION_PATH, "r")
                print(f.read())
                sys.exit()
                return 0
            elif a == "--version":
                print(SDK_VERSION)
                return 0

    global USER_AGENT
    USER_AGENT = "osc-cli/" + SDK_VERSION + " " + USER_AGENT
    logging.basicConfig(level=logging.ERROR)
    fire.Fire(api_connect)


if __name__ == "__main__":
    main()
