"""
Minimal test to validate Ollama / Qwen tool calling.

This test does NOT use MCP yet.
It verifies that the model can:
1. Receive a tool definition.
2. Decide to call the tool.
3. Generate the correct arguments.
4. Receive the tool result.
5. Produce a final answer.
"""

import sys
from pathlib import Path

from ollama_client import OllamaClient


# ---------------------------------------------------------------------
# Fake tool
# ---------------------------------------------------------------------

def get_employee_count(department: str):
    """
    Simulates a database query.
    """

    fake_data = {
        "Sales": 1250,
        "Engineering": 2340,
        "Human Resources": 320
    }

    return {
        "department": department,
        "employee_count": fake_data.get(department, 0)
    }


# ---------------------------------------------------------------------
# Tool definition exposed to the LLM
# ---------------------------------------------------------------------

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_employee_count",
            "description": (
                "Returns the number of employees "
                "in a specific department."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {
                        "type": "string",
                        "description": (
                            "The department whose employee "
                            "count should be retrieved."
                        )
                    }
                },
                "required": ["department"]
            }
        }
    }
]


# ---------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------

llm = OllamaClient()

messages = [
    {
        "role": "system",
        "content": (
            "You are a data analyst. "
            "Use the available tools when data is required. "
            "Do not invent data."
        )
    },
    {
        "role": "user",
        "content": (
            "How many employees work in the Engineering department?"
        )
    }
]


# ---------------------------------------------------------------------
# First model call
# ---------------------------------------------------------------------

print("\n--- FIRST MODEL CALL ---")

response = llm.chat(
    messages=messages,
    tools=tools
)

assistant_message = response.message

print("Content:")
print(assistant_message.content)

print("\nTool calls:")
print(assistant_message.tool_calls)


# ---------------------------------------------------------------------
# Execute tool call
# ---------------------------------------------------------------------

if assistant_message.tool_calls:

    # Add the assistant message containing the tool call
    # to the conversation history.
    messages.append(assistant_message)

    for tool_call in assistant_message.tool_calls:

        function_name = tool_call.function.name
        arguments = tool_call.function.arguments

        print("\n--- TOOL REQUESTED BY MODEL ---")
        print("Tool:", function_name)
        print("Arguments:", arguments)

        if function_name == "get_employee_count":

            result = get_employee_count(
                department=arguments["department"]
            )

            print("\n--- TOOL RESULT ---")
            print(result)

            # Return the tool result to the model.
            messages.append(
                {
                    "role": "tool",
                    "tool_name": function_name,
                    "content": str(result)
                }
            )


    # -----------------------------------------------------------------
    # Second model call
    # -----------------------------------------------------------------

    print("\n--- SECOND MODEL CALL ---")

    final_response = llm.chat(
        messages=messages,
        tools=tools
    )

    print(final_response.message.content)

else:

    print("\nThe model did not request a tool.")