"""MCP connectivity for AI Data Analyst: PG Airman and Apache Superset.

Superset SQL is constrained to one SELECT statement. A read-only database
account is still required as the authoritative enforcement layer.
"""

import json
from copy import deepcopy

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MCP_URL = os.getenv(
    "POSTGRES_MCP_URL",
    "http://localhost:8001/mcp"
)

SUPERSET_MCP_URL = os.getenv(
    "SUPERSET_MCP_URL",
    "http://localhost:5008/mcp"
)

MCP_SERVERS = {
    "postgres": MCP_URL,
    "superset": SUPERSET_MCP_URL
}

POSTGRES_TOOLS = {"list_schemas", "list_objects", "get_object_details", "execute_sql"}
SUPERSET_TOOLS = {"get_instance_info", "health_check", "search_tools", "call_tool"}
ALLOWED_TOOLS = POSTGRES_TOOLS
SUPERSET_READ_TOOLS = {
    "list_datasets", "get_dataset_info", "get_schema", "list_databases",
    "list_charts", "get_database_info", "get_dashboard_info", "execute_sql",
}
# Configure explicitly for each deployment; this is the verified Superset database.
SUPERSET_ALLOWED_DATABASE_IDS = {2}


def _validate_read_only_sql(sql):
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError as exc:
        raise RuntimeError("Superset SQL validation requires: pip install sqlglot") from exc
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("SQL must be a non-empty string.")
    if any(token in sql for token in ("{{", "{%", "{#")):
        raise ValueError("SQL templates are not permitted.")
    try:
        statements = sqlglot.parse(sql, error_level="RAISE")
    except Exception as exc:
        raise ValueError(f"Invalid SQL: {exc}") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError("Only one SELECT statement is permitted.")
    forbidden = (
        exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop,
        exp.Alter, exp.Command, exp.Merge, exp.Into,
    )
    if any(isinstance(node, forbidden) for node in statements[0].walk()):
        raise ValueError("SQL contains a write or administrative operation.")
    return sql.strip()


def _check_result(result):
    if getattr(result, "isError", False):
        raise RuntimeError("MCP tool returned an error: " + " ".join(
            item.text for item in result.content if hasattr(item, "text")
        )[:1000])
    for item in getattr(result, "content", []):
        if not hasattr(item, "text"):
            continue
        value = item.text.strip()
        if value.startswith("Error: "):
            raise RuntimeError(value[:1000])
        try:
            payload = json.loads(value)
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError(str(payload.get("error") or "Superset tool failed")[:1000])
    return result


class MCPClient:
    def __init__(self, url=None, source="postgres"):
        if source not in MCP_SERVERS:
            raise ValueError(f"Unknown MCP source: {source!r}")
        self.source = source
        self.url = url if url is not None else MCP_SERVERS[source]

    async def get_tools(self):
        allowed = POSTGRES_TOOLS if self.source == "postgres" else SUPERSET_TOOLS
        async with streamable_http_client(self.url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [tool for tool in result.tools if tool.name in allowed]

    async def call_tool(self, tool_name, arguments):
        allowed = POSTGRES_TOOLS if self.source == "postgres" else SUPERSET_TOOLS
        if tool_name not in allowed:
            raise ValueError(f"Tool {tool_name!r} is not allowed for {self.source}.")
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a dictionary.")
        arguments = deepcopy(arguments)

        if self.source == "superset" and tool_name == "call_tool":
            target = arguments.get("name")
            if target not in SUPERSET_READ_TOOLS:
                raise ValueError(f"Superset tool {target!r} is not allowed.")
            payload = arguments.get("arguments") or {}
            if not isinstance(payload, dict):
                raise ValueError("Superset tool arguments must be an object.")
            # Require the exact nesting verified against Superset MCP.
            if set(payload) != {"request"} or not isinstance(payload["request"], dict):
                raise ValueError("Superset tool requires exactly an 'arguments.request' object.")
            if target == "execute_sql":
                request = payload["request"]
                if set(request) - {"database_id", "sql", "limit", "timeout", "dry_run", "force_refresh"}:
                    raise ValueError("Unsupported execute_sql request fields.")
                dbid = request.get("database_id")
                if type(dbid) is not int or dbid not in SUPERSET_ALLOWED_DATABASE_IDS:
                    raise ValueError("Superset database_id is not authorized.")
                sql = _validate_read_only_sql(request.get("sql"))
                if request.get("dry_run", False) is not False or request.get("force_refresh", False) is not False:
                    raise ValueError("dry_run and force_refresh must be false.")
                limit = request.get("limit", 1000)
                timeout = request.get("timeout", 30)
                if type(limit) is not int or not 1 <= limit <= 1000:
                    raise ValueError("limit must be an integer between 1 and 1000.")
                if type(timeout) is not int or not 1 <= timeout <= 30:
                    raise ValueError("timeout must be an integer between 1 and 30.")
                arguments = {"name": target, "arguments": {"request": {
                    "database_id": dbid, "sql": sql, "limit": limit,
                    "timeout": timeout, "dry_run": False, "force_refresh": False,
                }}}

        async with streamable_http_client(self.url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
                return _check_result(result)
