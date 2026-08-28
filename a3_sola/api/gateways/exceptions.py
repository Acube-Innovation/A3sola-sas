# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Typed gateway errors.

A raw `requests` exception must never escape the wrapper. Callers need to know whether to
retry, to alert an operator, or to tell the customer something - and a bare
ConnectionError does not distinguish those.
"""


class GatewayError(Exception):
	"""Base for anything the gateway layer raises."""

	def __init__(self, message, code=None, detail=None):
		super().__init__(message)
		self.code = code
		self.detail = detail


class GatewayConfigError(GatewayError):
	"""Credentials or mode are missing or inconsistent. An operator must fix this."""


class GatewayAuthError(GatewayError):
	"""The gateway rejected our credentials. Never retry - retrying will not help."""


class GatewayValidationError(GatewayError):
	"""The gateway rejected the request itself (4xx). Never retry; the request is wrong."""


class GatewayNetworkError(GatewayError):
	"""Timeout, connection failure or a 5xx. Retried within the wrapper, then raised."""


class GatewaySignatureError(GatewayError):
	"""A signature did not verify. Treat as hostile until proven otherwise."""
