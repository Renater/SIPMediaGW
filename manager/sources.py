"""
The external HTTP APIs the back end calls: the proxyAPI, and nothing else
for now. The front never sees these URLs or tokens; every call to one of
them goes through proxyapi.py, which reads its entry here. The reporting
database is not one of them: db.py holds it.
"""

import os

SOURCES = {
    "proxyapi": {
        # Plain HTTP by design: TLS, when needed, is handled by an
        # optional shared reverse proxy in front of the whole stack.
        "base_url": os.getenv("PROXYAPI_URL", "http://127.0.0.1:80").rstrip("/"),
        # What a browser opens (the "Control" link): behind a reverse proxy
        # it is the proxy's public name, not the address the back reads from.
        "public_url": os.getenv("PROXYAPI_PUBLIC_URL",
                                os.getenv("PROXYAPI_URL", "http://127.0.0.1:80")).rstrip("/"),
        # Admin token, held server-side only. It never reaches the
        # browser — this is the point of the FastAPI back replacing the
        # Traefik header-injection middleware.
        "token": os.getenv("PROXYAPI_ADMIN_TOKEN", ""),
    },
}


def source(name: str) -> dict:
    return SOURCES[name]
