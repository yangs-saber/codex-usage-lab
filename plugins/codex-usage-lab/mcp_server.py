# Adapted from codex-usage-tracker v0.28.0, Copyright Douglas Monsky, MIT.
# Changes: application binding, identity, UI resource and thread entrypoint, tool annotations. See THIRD_PARTY_LICENSE.txt.
"""Small stdlib JSON-RPC stdio server for the six kernel MCP tools."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, BinaryIO

from plugin_api import __version__, KernelApplication, build_application, validate_input, TOOL_SPECS

MAX_MESSAGE_BYTES = 1_048_576
PROTOCOL_VERSION = "2025-06-18"


class McpServer:
    def __init__(self, application: KernelApplication) -> None:
        self._application = application

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        has_id = "id" in message
        request_id = message.get("id")
        if message.get("jsonrpc") != "2.0" or (
            has_id
            and (
                isinstance(request_id, bool)
                or not isinstance(request_id, (str, int, type(None)))
            )
        ):
            return _error(request_id if has_id else None, -32600, "Invalid Request")
        method = message.get("method")
        if not isinstance(method, str):
            return _error(request_id, -32600, "Invalid Request")
        if not has_id:
            return None
        if method == "initialize":
            parameters = message.get("params")
            if not isinstance(parameters, dict):
                return _error(request_id, -32602, "Invalid params")
            return _result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}, "resources": {"listChanged": False}},
                    "serverInfo": {
                        "name": "codex-usage-lab",
                        "version": __version__,
                    },
                },
            )
        if method in {"ping", "tools/list"} and not isinstance(
            message.get("params", {}),
            dict,
        ):
            return _error(request_id, -32602, "Invalid params")
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(
                request_id,
                {
                    "tools": [
                        {
                            "name": spec.name,
                            "description": spec.description,
                            "inputSchema": spec.input_schema,
                            "annotations": {"readOnlyHint": spec.name != "annotate_usage_turn", "destructiveHint": False, "openWorldHint": False},
                            **({"title": "实时用量", "_meta": {"ui": {"resourceUri": "ui://usage-lab/meter.html", "visibility": ["model", "app"]}, "openai/ui": {"entrypoints": [{"type": "thread"}]}, "openai/outputTemplate": "ui://usage-lab/meter.html", "openai/widgetAccessible": True}} if spec.name == "open_usage_dashboard" else {}),
                        }
                        for spec in TOOL_SPECS
                    ]
                },
            )
        if method == "resources/list":
            return _result(request_id, {"resources": [{"uri": "ui://usage-lab/meter.html", "name": "实时用量", "mimeType": "text/html;profile=mcp-app"}]})
        if method == "resources/read":
            if (message.get("params") or {}).get("uri") != "ui://usage-lab/meter.html":
                return _error(request_id, -32602, "Unknown resource")
            return _result(request_id, {"contents": [{"uri": "ui://usage-lab/meter.html", "mimeType": "text/html;profile=mcp-app", "text": (Path(__file__).parent / "meter.html").read_text(), "_meta": {"ui": {"prefersBorder": True}, "openai/ui": {"availableDisplayModes": ["inline", "fullscreen"], "preferredDisplayMode": "inline"}, "openai/widgetDescription": "Live local token and estimated credits meter. Refreshes through app tools without sending chat prompts."}}]})
        if method == "tools/call":
            return self._call(request_id, message.get("params"))
        return _error(request_id, -32601, "Method not found")

    def _call(self, request_id: Any, parameters: Any) -> dict[str, Any]:
        if not isinstance(parameters, dict):
            return _error(request_id, -32602, "Invalid params")
        name = parameters.get("name")
        arguments = parameters.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return _error(request_id, -32602, "Invalid params")
        try:
            validate_input(name, arguments)
            structured = self._application.dispatch(name, arguments)
        except sqlite3.Error:
            return _tool_error(request_id, "kernel cache is unavailable")
        except (OSError, RuntimeError, ValueError) as exc:
            return _tool_error(request_id, str(exc))
        return _result(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": "Kernel result is available in structuredContent.",
                    }
                ],
                "structuredContent": structured,
                "isError": False,
            },
        )


def _tool_error(request_id: Any, message: str) -> dict[str, Any]:
    return _result(
        request_id,
        {
            "content": [{"type": "text", "text": message}],
            "isError": True,
        },
    )


def run_stdio(
    application: KernelApplication | None = None,
    *,
    input_stream: BinaryIO | None = None,
    output_stream: BinaryIO | None = None,
) -> None:
    server = McpServer(application or build_application())
    source = input_stream or sys.stdin.buffer
    destination = output_stream or sys.stdout.buffer
    for line in source:
        response: dict[str, Any] | None
        if len(line) > MAX_MESSAGE_BYTES:
            response = _error(None, -32600, "Message too large")
        else:
            try:
                payload = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                response = _error(None, -32700, "Parse error")
            else:
                response = (
                    server.handle(payload)
                    if isinstance(payload, dict)
                    else _error(None, -32600, "Invalid Request")
                )
        if response is None:
            continue
        destination.write(
            json.dumps(
                response,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
            + b"\n"
        )
        destination.flush()


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(
    request_id: Any,
    code: int,
    message: str,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def main() -> None:
    run_stdio()


if __name__ == "__main__":
    main()
