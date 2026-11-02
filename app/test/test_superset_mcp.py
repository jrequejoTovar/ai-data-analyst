import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")



MCP_URL = os.getenv(
    "SUPERSET_MCP_URL",
    "http://localhost:8001/mcp"
)


async def main():
    async with streamable_http_client(
        MCP_URL
    ) as (read, write, _):

        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "search_tools",
                arguments={"query": "execute_sql"}
            )

            for item in result.content:
                if hasattr(item, "text"):
                    data = json.loads(item.text)

                    for tool in data:
                        if tool.get("name") == "execute_sql":
                            print(json.dumps(
                                tool,
                                indent=2,
                                ensure_ascii=False
                            ))


asyncio.run(main())