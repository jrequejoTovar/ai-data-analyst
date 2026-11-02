"""
Ollama client for the AI Data Analyst application.

This module isolates all communication with the local
Ollama server.
"""

import ollama
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST_URL",
    "http://localhost:11434"
)


DEFAULT_MODEL = os.getenv(
    "OLLAMA_DEFAULT_MODEL",
    "qwen3:8b"
)


class OllamaClient:

    def __init__(
        self,
        model=DEFAULT_MODEL,
        host=OLLAMA_HOST
    ):
        self.model = model

        self.client = ollama.Client(
            host=host
        )

    def chat(
        self,
        messages,
        tools=None,
        temperature=0.2
    ):
        """
        Send a conversation to the model.

        The response may contain either:
        - a normal assistant response
        - one or more tool calls
        """

        options = {
            "temperature": temperature
        }

        response = self.client.chat(
            model=self.model,
            messages=messages,
            tools=tools,
            options=options,
            stream=False
        )

        return response