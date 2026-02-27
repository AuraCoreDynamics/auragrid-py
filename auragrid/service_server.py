"""Embedded HTTP server for receiving inbound service method invocations.

When a Python MAS exposes ``@auragrid_service`` decorated classes, this server
starts on an ephemeral port and accepts ``POST /invoke/{method_name}`` requests
forwarded by the ProxyWorker's ``ExternalServiceDispatcher``.

The server authenticates requests using the ``X-AuraGrid-IPC-Token`` header
and dispatches to the appropriate ``@auragrid_method`` on the service instance.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import signal
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any, Callable, Optional

logger = logging.getLogger("auragrid.service_server")


def _find_service_classes() -> list[type]:
    """Discover all imported classes decorated with ``@auragrid_service``."""
    import gc

    result: list[type] = []
    for obj in gc.get_objects():
        if isinstance(obj, type) and hasattr(obj, "_auragrid_service_meta"):
            result.append(obj)
    return result


def _get_methods(instance: object) -> dict[str, Callable[..., Any]]:
    """Extract ``@auragrid_method`` decorated methods from a service instance."""
    methods: dict[str, Callable[..., Any]] = {}
    for name in dir(instance):
        if name.startswith("_"):
            continue
        attr = getattr(instance, name, None)
        if callable(attr) and hasattr(attr, "_auragrid_method_meta"):
            meta = attr._auragrid_method_meta
            method_name = meta.get("name", name)
            methods[method_name] = attr
    return methods


def _allocate_ephemeral_port() -> int:
    """Bind to port 0 to get an OS-assigned ephemeral port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServiceRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for inbound service method invocations."""

    # Set by ServiceServer before starting
    ipc_token: str = ""
    service_methods: dict[str, Callable[..., Any]] = {}

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(format, *args)

    def do_POST(self) -> None:
        # Always read the request body first to avoid connection resets
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        # Authenticate
        token = self.headers.get("X-AuraGrid-IPC-Token", "")
        if token != self.ipc_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Invalid IPC token"})
            return

        # Parse path: /invoke/{method_name}
        path = self.path.rstrip("/")
        if not path.startswith("/invoke/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown route: {self.path}"})
            return

        method_name = path[len("/invoke/"):]
        if not method_name:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Missing method name"})
            return

        method = self.service_methods.get(method_name)
        if method is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": f"Method '{method_name}' not found"},
            )
            return

        # Parse JSON parameters
        params: dict[str, Any] = {}
        if body:
            try:
                params = json.loads(body)
            except json.JSONDecodeError as e:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": f"Invalid JSON: {e}"},
                )
                return

        # Invoke method
        try:
            sig = inspect.signature(method)
            bound_params: dict[str, Any] = {}
            for param_name, param in sig.parameters.items():
                if param_name in params:
                    bound_params[param_name] = params[param_name]
                elif param.default is not inspect.Parameter.empty:
                    bound_params[param_name] = param.default

            result = method(**bound_params)

            # Await if async
            if inspect.isawaitable(result):
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(result)
                finally:
                    loop.close()

            self._send_json(HTTPStatus.OK, result)

        except TypeError as e:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": f"Parameter binding error: {e}"},
            )
        except Exception as e:
            logger.warning("Method '%s' raised: %s", method_name, e)
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": str(e)},
            )

    def _send_json(self, status: HTTPStatus, data: Any) -> None:
        body = json.dumps(data).encode("utf-8") if data is not None else b"null"
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ServiceServer:
    """Lightweight embedded HTTP server for receiving service invocations.

    Starts on an ephemeral port and authenticates via ``X-AuraGrid-IPC-Token``.
    Reports its port back to the ProxyWorker via the outbound IPC channel.
    """

    def __init__(
        self,
        service_instance: object,
        ipc_token: str,
        port: int = 0,
    ) -> None:
        self._service_instance = service_instance
        self._ipc_token = ipc_token
        self._methods = _get_methods(service_instance)
        self._port = port or _allocate_ephemeral_port()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[Thread] = None

    @property
    def port(self) -> int:
        """The port the server is listening on."""
        return self._port

    @property
    def service_name(self) -> str:
        """The service name from the ``@auragrid_service`` decorator."""
        meta = getattr(self._service_instance.__class__, "_auragrid_service_meta", {})
        return meta.get("name", self._service_instance.__class__.__name__)

    @property
    def method_names(self) -> list[str]:
        """Names of all registered methods."""
        return list(self._methods.keys())

    def start(self) -> None:
        """Start the embedded server in a background thread."""
        # Configure the handler class with our state
        handler_class = type(
            "ConfiguredHandler",
            (ServiceRequestHandler,),
            {
                "ipc_token": self._ipc_token,
                "service_methods": self._methods,
            },
        )

        self._server = HTTPServer(("127.0.0.1", self._port), handler_class)
        self._port = self._server.server_address[1]

        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        logger.info(
            "Service server started on port %d for service '%s' (%d methods)",
            self._port,
            self.service_name,
            len(self._methods),
        )

    def stop(self) -> None:
        """Gracefully shut down the server."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        logger.info("Service server stopped for service '%s'", self.service_name)
