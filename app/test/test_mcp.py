import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

URL = os.getenv(
    "POSTGRES_MCP_URL",
    "http://localhost:8001/mcp"
)



async def main():
    async with streamablehttp_client(URL) as (
        read_stream,
        write_stream,
        _
    ):
        async with ClientSession(read_stream, write_stream) as session:

            await session.initialize()

            # 1. List available MCP tools
            tools = await session.list_tools()
            print("\n=== AVAILABLE TOOLS ===")
            print([tool.name for tool in tools.tools])

            # 2. List database schemas
            print("\n=== SCHEMAS ===")
            result = await session.call_tool(
                "list_schemas",
                {}
            )
            print(result.content)

            # 3. List objects in public schema
            print("\n=== PUBLIC OBJECTS ===")
            result = await session.call_tool(
                "list_objects",
                {"schema_name": "public"}
            )
            print(result.content)

            # 4. Get employees table metadata
            print("\n=== EMPLOYEES METADATA ===")
            result = await session.call_tool(
                "get_object_details",
                {
                    "schema_name": "public",
                    "object_name": "employees",
                    "object_type": "table"
                }
            )
            print(result.content)

            # 5. Execute a simple analytical query
            print("\n=== EMPLOYEE COUNT ===")
            result = await session.call_tool(
                "execute_sql",
                {
                    "sql": "SELECT COUNT(*) AS employee_count FROM public.employees"
                }
            )
            print(result.content)


if __name__ == "__main__":
    asyncio.run(main())