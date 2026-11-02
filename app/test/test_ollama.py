import ollama
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MODEL = "qwen3:8b"

response = ollama.chat(
    model=MODEL,
    messages=[
        {
            "role": "user",
            "content": "What is employee attrition?"
        }
    ]
)

print(response["message"]["content"])