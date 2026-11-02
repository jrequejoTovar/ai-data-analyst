"""
End-to-end test for the AI Data Analyst INVESTIGATE mode.

This test uses the real components:

- Ollama / Qwen
- MCP
- PostgreSQL
- DataAnalystAgent
- Structured output validation

Expected final result:

{
    "mode": "investigate",
    "analysis": {
        "answer": "...",
        "facts": [...],
        "observations": [...],
        "hypotheses": [...],
        "recommendations": [...],
        "visualizations": [...]
    },
    "evidence": [...],
    "trace": [...]
}
"""

import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import DataAnalystAgent


QUESTION = """
Why are employees leaving the company?

Investigate the available data and identify the factors most strongly
associated with employee attrition.

Use evidence from the data to support your conclusions.

Do not assume causation.
""".strip()


async def main():

    print()
    print("========================================")
    print("AI DATA ANALYST - END-TO-END TEST")
    print("========================================")
    print()

    print("QUESTION")
    print("----------------------------------------")
    print(QUESTION)
    print()

    agent = DataAnalystAgent()

    print("Starting INVESTIGATE mode...")
    print()

    result = await agent.run(
        question=QUESTION,
        mode="investigate",
    )

    print()
    print("========================================")
    print("FINAL STRUCTURED RESPONSE")
    print("========================================")
    print()

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )

    print()
    print("========================================")
    print("BASIC VALIDATION")
    print("========================================")
    print()

    assert result["mode"] == "investigate"

    assert "analysis" in result
    assert "evidence" in result
    assert "trace" in result

    analysis = result["analysis"]

    assert "answer" in analysis
    assert "facts" in analysis
    assert "observations" in analysis
    assert "hypotheses" in analysis
    assert "recommendations" in analysis
    assert "visualizations" in analysis

    assert isinstance(analysis["answer"], str)
    assert isinstance(analysis["facts"], list)
    assert isinstance(analysis["observations"], list)
    assert isinstance(analysis["hypotheses"], list)
    assert isinstance(analysis["recommendations"], list)
    assert isinstance(analysis["visualizations"], list)

    assert isinstance(result["evidence"], list)
    assert isinstance(result["trace"], list)

    print("OK - mode")
    print("OK - analysis")
    print("OK - evidence")
    print("OK - trace")
    print()

    print("========================================")
    print("SUMMARY")
    print("========================================")
    print()

    print(
        f"Facts: {len(analysis['facts'])}"
    )

    print(
        f"Observations: {len(analysis['observations'])}"
    )

    print(
        f"Hypotheses: {len(analysis['hypotheses'])}"
    )

    print(
        f"Recommendations: {len(analysis['recommendations'])}"
    )

    print(
        f"Visualizations: {len(analysis['visualizations'])}"
    )

    print(
        f"Evidence items: {len(result['evidence'])}"
    )

    print(
        f"Trace entries: {len(result['trace'])}"
    )

    print()
    print("========================================")
    print("TEST COMPLETED SUCCESSFULLY")
    print("========================================")
    print()


if __name__ == "__main__":
    asyncio.run(main())
