"""
Test Qwen tool calling with an external Python tool.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ollama_client import OllamaClient
from tools import (
    get_external_tool_declarations,
    execute_external_tool
)


def main():

    llm = OllamaClient()

    tools = get_external_tool_declarations()

    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI assistant. "
                "Use the available tools whenever external "
                "information is required. "
                "Do not invent tool results."
            )
        },
        {
            "role": "user",
            "content": (
                "What are the public holidays in Spain "
                "in 2026?"
            )
        }
    ]

    # ------------------------------------------------------------
    # FIRST MODEL CALL
    # ------------------------------------------------------------

    response = llm.chat(
        messages=messages,
        tools=tools
    )

    assistant_message = response.message

    print("\n--- FIRST MODEL CALL ---")
    print("Content:")
    print(assistant_message.content)

    print("\nTool calls:")
    print(assistant_message.tool_calls)

    messages.append(assistant_message)

    # ------------------------------------------------------------
    # EXECUTE REQUESTED TOOLS
    # ------------------------------------------------------------

    if not assistant_message.tool_calls:
        print("\nThe model did not request any tool.")
        return

    for tool_call in assistant_message.tool_calls:

        tool_name = tool_call.function.name
        arguments = tool_call.function.arguments

        print("\n--- TOOL REQUESTED BY MODEL ---")
        print("Tool:", tool_name)
        print("Arguments:", arguments)

        result = execute_external_tool(
            tool_name,
            arguments
        )

        print("\n--- TOOL RESULT ---")
        print(result)

        messages.append(
            {
                "role": "tool",
                "tool_name": tool_name,
                "content": str(result)
            }
        )

    # ------------------------------------------------------------
    # SECOND MODEL CALL
    # ------------------------------------------------------------

    final_response = llm.chat(
        messages=messages,
        tools=tools
    )

    print("\n--- FINAL MODEL ANSWER ---")
    print(final_response.message.content)


if __name__ == "__main__":
    main()