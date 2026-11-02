import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_client import MCPClient
from ollama_client import OllamaClient


async def main():

    print("\n--- MCP TEST ---")

    mcp = MCPClient()

    tools = await mcp.get_tools()

    print("Tools exposed to agent:")

    for tool in tools:
        print(f" - {tool.name}")


    print("\n--- OLLAMA TEST ---")

    llm = OllamaClient()

    response = llm.chat(
        messages=[
            {
                "role": "user",
                "content": "Say only: Ollama connection OK"
            }
        ]
    )

    print(response.message.content)


if __name__ == "__main__":
    asyncio.run(main())