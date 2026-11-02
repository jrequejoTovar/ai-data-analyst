"""
External tools available to the AI Data Analyst.

These tools provide information that does not come from the
organization's internal PostgreSQL database.

Each tool has:

1. A Python implementation.
2. An Ollama-compatible function declaration.
3. A registry entry used by the agent.
"""

import requests


# ================================================================
# PUBLIC HOLIDAYS
# ================================================================

def get_public_holidays(
    country_code: str,
    year: int
) -> dict:
    """
    Retrieve official public holidays from Nager.Date.
    """

    country_code = country_code.upper().strip()

    url = (
        f"https://date.nager.at/api/v3/"
        f"PublicHolidays/{year}/{country_code}"
    )

    try:

        response = requests.get(
            url,
            timeout=5
        )

        response.raise_for_status()

        holidays = response.json()

        compact_holidays = [
            {
                "date": holiday.get("date"),
                "local_name": holiday.get("localName"),
                "name": holiday.get("name"),
                "global": holiday.get("global"),
                "counties": holiday.get("counties")
            }
            for holiday in holidays
        ]

        return {
            "status": "success",
            "country": country_code,
            "year": year,
            "holidays": compact_holidays
        }

    except requests.RequestException as exc:

        return {
            "status": "error",
            "message": str(exc)
        }


# ================================================================
# OLLAMA TOOL DECLARATION
# ================================================================

PUBLIC_HOLIDAYS_TOOL = {
    "type": "function",

    "function": {

        "name": "get_public_holidays",

        "description": (
            "Retrieves official national and regional public "
            "holidays for a given country and year. "
            "Use this tool when a question requires information "
            "about public holidays or non-working days."
        ),

        "parameters": {

            "type": "object",

            "properties": {

                "country_code": {
                    "type": "string",
                    "description": (
                        "ISO 2-letter country code, for example "
                        "ES, GB, FR or US."
                    )
                },

                "year": {
                    "type": "integer",
                    "description": (
                        "Four-digit year, for example 2026."
                    )
                }
            },

            "required": [
                "country_code",
                "year"
            ]
        }
    }
}


# ================================================================
# EXTERNAL TOOL REGISTRY
# ================================================================

EXTERNAL_TOOLS = {

    "get_public_holidays": {
        "function": get_public_holidays,
        "declaration": PUBLIC_HOLIDAYS_TOOL
    }

}


# ================================================================
# PUBLIC FUNCTIONS USED BY THE AGENT
# ================================================================

def get_external_tool_declarations():
    """
    Return all external tool declarations in Ollama format.
    """

    return [
        tool["declaration"]
        for tool in EXTERNAL_TOOLS.values()
    ]


def execute_external_tool(
    tool_name: str,
    arguments: dict
):
    """
    Execute an external tool by name.
    """

    if tool_name not in EXTERNAL_TOOLS:

        raise ValueError(
            f"External tool '{tool_name}' is not allowed."
        )

    function = EXTERNAL_TOOLS[
        tool_name
    ]["function"]

    return function(**arguments)


def is_external_tool(tool_name: str) -> bool:
    """
    Check whether a tool belongs to the external tool registry.
    """

    return tool_name in EXTERNAL_TOOLS