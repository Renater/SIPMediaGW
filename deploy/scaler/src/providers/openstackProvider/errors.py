#!/usr/bin/env python
"""Classification of the OpenStack errors the provider needs to react to."""

import openstack.exceptions

# openstacksdk renamed ResourceNotFound to NotFoundException and keeps the other
# name as an alias, so bind whichever the installed release actually exposes.
NOT_FOUND_EXCEPTIONS = tuple(
    {
        exc
        for exc in (
            getattr(openstack.exceptions, "NotFoundException", None),
            getattr(openstack.exceptions, "ResourceNotFound", None),
        )
        if exc is not None
    }
)


def isNotFoundError(exc):
    """True when `exc` reports an HTTP 404, whichever library raised it."""
    if NOT_FOUND_EXCEPTIONS and isinstance(exc, NOT_FOUND_EXCEPTIONS):
        return True
    # keystoneauth1 errors can surface unwrapped by the SDK; both libraries carry
    # the HTTP status as an attribute, so the message never needs to be parsed.
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    return status == 404
