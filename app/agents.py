"""

AI Data Analyst agent.
Supports:
- ASK: focused business questions.
- INVESTIGATE: staged evidence collection, evaluation and grounded synthesis.
Key safeguards in INVESTIGATE:
- duplicate tool calls are not re-executed;
- discovery calls already completed are not repeated in later evidence rounds;
- numerical variables should be bucketed or summarized, not grouped by raw values;
- final semantic analysis is grounded against an application-built evidence ledger;
- facts, observations and visualizations reference evidence IDs;
- causal language is explicitly prohibited for observational evidence.

"""
import asyncio
import json
import re
import time
from mcp_client import MCPClient
from ollama_client import OllamaClient
from prompts_store import (
    ANALYST_SYSTEM_PROMPT,
    INVESTIGATE_SYSTEM_PROMPT,
    TOOL_ERROR_RECOVERY_PROMPT,
    ROUTER_SYSTEM_PROMPT,
    ANALYTICAL_INTERPRETATION_GUARDRAILS,
    OUTPUT_LANGUAGE_PROMPT,
    ADDITIONAL_INVESTIGATION_RULES,
    TOOL_LIMIT_PROMPT,
    STRUCTURED_SYNTHESIS_PROMPT,
    STRUCTURED_REPAIR_PROMPT,
    EVIDENCE_EVALUATOR_PROMPT,
)
from tools import (
    get_external_tool_declarations,
    execute_external_tool,
    is_external_tool,
)
from structured_output import (
    parse_structured_analysis,
    build_final_response,
)
MAX_ASK_ITERATIONS = 10
# Maximum number of successful analytical evidence queries
# during the main investigation. Schema discovery does not
# consume this budget.
MAX_INVESTIGATE_ITERATIONS = 5
# Maximum number of successful targeted evidence queries
# requested after the evaluator identifies material gaps.
MAX_ADDITIONAL_EVIDENCE_ITERATIONS = 2
# Failed tool calls may be corrected without immediately
# exhausting the useful evidence budget.
MAX_TOOL_ERROR_RETRIES = 2
MAX_EVALUATION_ROUNDS = 1
DISCOVERY_TOOLS = {
    "list_schemas",
    "list_objects",
    "get_object_details",
    "list_databases",
    "list_datasets",
    "get_dataset_info",
}
EVIDENCE_TOOLS = {
    "execute_sql",
}
# ============================================================
# ROUTER AGENT
# ============================================================
class RouterAgent:
    """

    Selects the analytical workflow.
    The router has no tools and does not answer the business
    question. It only chooses ASK or INVESTIGATE.

    """
    def __init__(self):
        self.llm = OllamaClient()
    async def classify(self, question: str) -> dict:
        messages = [
            {
                "role": "system",
                "content": ROUTER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": question,
            },
        ]
        # OllamaClient.chat is synchronous. Run it in a worker thread
        # so the Flask async request is not blocked by the router call.
        response = await asyncio.to_thread(
            self.llm.chat,
            messages,
            None,
            0.0,
        )
        raw = (response.message.content or "").strip()
        decision = self._parse_decision(raw)
        return {
            "selected": decision["strategy"],
            "reason": decision["reason"],
        }
    @staticmethod
    def _parse_decision(raw: str) -> dict:
        text = raw.strip()
        # Defensive cleanup in case the model adds Markdown fences.
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(
                r"**\\{**.***\\}**",
                text,
                flags=re.DOTALL,
            )
            if not match:
                raise ValueError(
                    "Router returned invalid JSON: "

                    f"{raw}"
                )
            data = json.loads(match.group(0))
        strategy = str(
            data.get("strategy", "")
        ).lower().strip()
        reason = str(
            data.get("reason", "")
        ).strip()
        if strategy not in {
            "ask",
            "investigate",
        }:
            raise ValueError(
                "Router returned unsupported "

                f"strategy: {strategy}"
            )
        if not reason:
            reason = (
                "Focused evidence request."
                if strategy == "ask"
                else
                "Requires multi-evidence investigation."
            )
        return {
            "strategy": strategy,
            "reason": reason,
        }
class DataAnalystAgent:
    @staticmethod
    def _emit_progress(progress_callback, event):
        """

        Emit application-safe operational progress.
        Events describe phases, tool calls and tool results.
        They never expose private chain-of-thought.

        """
        if progress_callback:
            progress_callback(event)
    def __init__(self, source="postgres"):
        self.mcp = MCPClient(source=source)
        self.source = source
        self.llm = OllamaClient()
        self._schema_context_cache = ""
    # ============================================================
    # TOOL PREPARATION
    # ============================================================
    @staticmethod
    def _convert_mcp_tools_to_ollama(mcp_tools):
        ollama_tools = []
        for tool in mcp_tools:
            tool_description = tool.description or ""
            if tool.name == "execute_sql":
                tool_description = (
                    "Execute read-only PostgreSQL SQL against the connected "
                    "database. Generate PostgreSQL-compatible SQL only. "
                    + tool_description
                )
            ollama_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool_description,
                        "parameters": tool.inputSchema,
                    },
                }
            )
        return ollama_tools
    @staticmethod
    def _superset_agent_tools():
        """Expose concrete, read-only operations rather than the generic MCP call_tool."""
        def tool(name, description, properties, required=None):
            return {"type": "function", "function": {
                "name": name, "description": description,
                "parameters": {"type": "object", "properties": properties,
                               "required": required or [], "additionalProperties": False},
            }}
        return [
            tool("list_databases", "List Superset database connections.", {}),
            tool("list_datasets", "List Superset datasets, optionally filtered by name.", {
                "search": {"type": "string"},
                "page": {"type": "integer", "minimum": 1},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
            }),
            tool("get_dataset_info", "Get dataset columns and metadata by numeric dataset ID.", {
                "identifier": {"type": "integer", "minimum": 1},
            }, ["identifier"]),
            tool("execute_sql", "Run a single read-only SELECT on Superset database ID 2. "
                 "Use discovered dataset/table and column names; maximum 1000 rows.", {
                "sql": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            }, ["sql"]),
        ]
    async def _get_all_tools(self):
        mcp_tools = await self.mcp.get_tools()
        database_tools = (
            self._superset_agent_tools()
            if self.source == "superset"
            else self._convert_mcp_tools_to_ollama(mcp_tools)
        )
        external_tools = get_external_tool_declarations()
        return database_tools + external_tools
    # ============================================================
    # SERIALIZATION
    # ============================================================
    @staticmethod
    def _serialize_mcp_tool_result(result):
        if hasattr(result, "content"):
            contents = []
            for item in result.content:
                if hasattr(item, "text"):
                    contents.append(item.text)
                else:
                    contents.append(str(item))
            return "\n".join(contents)
        return str(result)
    @staticmethod
    def _serialize_external_tool_result(result):
        return json.dumps(
            result,
            ensure_ascii=False,
            default=str,
        )
    # ============================================================
    # TOOL EXECUTION
    # ============================================================
    async def _execute_tool(self, tool_name, arguments):
        if is_external_tool(tool_name):
            result = execute_external_tool(
                tool_name,
                arguments,
            )
            return (
                self._serialize_external_tool_result(result),
                "external",
            )
        if self.source == "superset":
            if tool_name not in {"list_databases", "list_datasets", "get_dataset_info", "execute_sql"}:
                raise ValueError(f"Superset agent tool not permitted: {tool_name}")
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object")
            request = dict(arguments)
            if tool_name == "execute_sql":
                if set(request) - {"sql", "limit"}:
                    raise ValueError("Unsupported Superset SQL arguments")
                request = {"database_id": 2, **request}
            result = await self.mcp.call_tool("call_tool", {
                "name": tool_name, "arguments": {"request": request},
            })
        else:
            result = await self.mcp.call_tool(
                tool_name,
                arguments,
            )
        if getattr(result, "isError", False):
            raise RuntimeError(self._serialize_mcp_tool_result(result))
        if self.source == "superset":
            payload = self._serialize_mcp_tool_result(result)
            if payload.lstrip().startswith("Error:"):
                raise RuntimeError(payload)
            try:
                parsed = json.loads(payload)
            except (ValueError, TypeError):
                raise RuntimeError("Superset returned a non-JSON tool response")
            if isinstance(parsed, dict) and (parsed.get("success") is False or parsed.get("error")):
                raise RuntimeError(f"Superset tool failed: {parsed.get('error', payload)}")
        return (
            self._serialize_mcp_tool_result(result),
            "mcp",
        )
    
    # ============================================================
    # TOOL CALL DEDUPLICATION
    # ============================================================
    @staticmethod
    def _tool_call_key(tool_name, arguments):
        """
        Create a stable identity for a tool call.
        For SQL, whitespace and a trailing semicolon are normalized so
        equivalent repeated queries are easier to detect.
        """
        clean_arguments = dict(arguments or {})
        if tool_name == "execute_sql":
            sql = str(clean_arguments.get("sql", ""))
            sql = re.sub(r"\s+", " ", sql).strip().rstrip(";")
            clean_arguments["sql"] = sql
        return (
            tool_name,
            json.dumps(
                clean_arguments,
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            ),
        )
    @classmethod
    def _trace_tool_keys(
        cls,
        trace,
        include_errors=True,
    ):
        """
        Return tool-call identities already attempted.
        Failed calls are included by default so the controller
        cannot execute exactly the same invalid SQL twice.
        This does not prevent the model from correcting a failed
        query. A corrected query has different arguments and
        therefore a different tool-call key.
        """
        keys = set()
        for item in trace:
            if item.get("skipped"):
                continue
            if (
                not include_errors
                and item.get("error")
            ):
                continue
            tool_name = item.get("tool")
            arguments = item.get(
                "arguments",
                {},
            )
            if tool_name:
                keys.add(
                    cls._tool_call_key(
                        tool_name,
                        arguments,
                    )
                )
        return keys
    @staticmethod
    def _completed_discovery_tools(trace):
        return {
            item.get("tool")
            for item in trace
            if (
                item.get("tool") in DISCOVERY_TOOLS
                and not item.get("error")
                and not item.get("skipped")
            )
        }
    @staticmethod
    def _tool_result_is_error(tool_result):
        """
        Some MCP servers return execution failures as normal text instead of
        raising an exception. Detect those results so they enter recovery,
        not the evidence ledger.
        """
        if not isinstance(tool_result, str):
            return False
        normalized = tool_result.strip().lower()
        return normalized.startswith(
            (
                "error:",
                "tool execution failed:",
            )
        )
    @staticmethod
    def _verified_schema_context(trace):
        """
        Return successful schema/object metadata already collected.
        This lets the agent recover from a schema-related SQL error without
        guessing column names or repeating discovery calls.
        """
        metadata = []
        for item in trace:
            if (
                item.get("tool") in DISCOVERY_TOOLS
                and not item.get("error")
                and not item.get("skipped")
                and item.get("result")
            ):
                metadata.append(
                    {
                        "tool": item.get("tool"),
                        "arguments": item.get("arguments", {}),
                        "result": item.get("result"),
                    }
                )
        if not metadata:
            return ""
        return json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    # ============================================================
    # GENERIC TOOL LOOP
    # ============================================================
    async def _tool_loop(
        self,
        messages,
        tools,
        trace,
        max_iterations,
        phase,
        progress_callback=None,
        discovery_outside_budget=False,
    ):
        """
        Execute an LLM/tool loop.
        Repeated calls are not re-executed. In additional evidence
        collection, discovery tools that already succeeded are also
        skipped.
        If the iteration limit is reached, the model gets one final
        call without tools and must summarize the evidence collected.
        """
        analytical_actions = 0
        error_retries = 0
        discovery_allowance = (
            len(DISCOVERY_TOOLS) + 2
            if discovery_outside_budget
            else 0
        )
        hard_limit = (
            max_iterations
            + discovery_allowance
            + MAX_TOOL_ERROR_RETRIES
        )
        budget_exhausted = False
        for iteration in range(hard_limit):
            print(
                f"\n--- {phase.upper()} "

                f"ITERATION {iteration + 1} ---"
            )
            self._emit_progress(
                progress_callback,
                {
                    "type": "phase",
                    "phase": phase,
                    "status": "running",
                    "title": (
                        "Answering the question"
                        if phase == "ask"
                        else "Investigating the data"
                        if phase == "investigation"
                        else "Collecting more evidence"
                    ),
                    "message": f"Analytical iteration {iteration + 1}.",
                },
            )
            llm_started = time.perf_counter()

            print(
                f"[LLM] START phase={phase} iteration={iteration + 1}",
                flush=True
            )

            response = self.llm.chat(
                messages=messages,
                tools=tools,
            )

            llm_duration = time.perf_counter() - llm_started

            print(
                f"[LLM] END phase={phase} "
                f"iteration={iteration + 1} "
                f"duration={llm_duration:.2f}s",
                flush=True
            )
            self._emit_progress(
                progress_callback,
                {
                    "type": "model",
                    "phase": phase,
                    "status": "complete",
                    "title": "Analytical decision",
                    "message": "The model selected the next analytical action.",
                    "duration_seconds": round(llm_duration, 2),
                },
            )
            assistant_message = response.message
            tool_calls = assistant_message.tool_calls
            if not tool_calls:
                messages.append(assistant_message)
                return assistant_message
            # Agent controller: execute at most one tool action per model turn.
            # This prevents a batch of dependent SQL calls from running before
            # the model has observed whether the first action succeeded.
            if len(tool_calls) > 1:
                tool_calls = tool_calls[:1]
                try:
                    assistant_message.tool_calls = tool_calls
                except Exception:
                    pass
            messages.append(assistant_message)
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                arguments = tool_call.function.arguments or {}
                if (
                    discovery_outside_budget
                    and tool_name not in DISCOVERY_TOOLS
                    and analytical_actions >= max_iterations
                ):
                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": tool_name,
                            "content": (
                                "ANALYTICAL BUDGET REACHED. Do not request more tools. "
                                "Summarize the evidence already collected."
                            ),
                        }
                    )
                    budget_exhausted = True
                    break
                self._emit_progress(
                    progress_callback,
                    {
                        "type": "tool",
                        "phase": phase,
                        "status": "running",
                        "title": f"Using {tool_name}",
                        "message": "Calling an approved analytical tool.",
                        "tool": tool_name,
                        "arguments": arguments,
                    },
                )
                print("\nTool requested:")
                print(tool_name)
                print("Arguments:")
                print(
                    json.dumps(
                        arguments,
                        indent=2,
                        ensure_ascii=False,
                        default=str,
                    )
                )
                call_key = self._tool_call_key(
                    tool_name,
                    arguments,
                )
                previous_keys = self._trace_tool_keys(
                    trace
                )
                completed_discovery = (
                    self._completed_discovery_tools(
                        trace
                    )
                )
                skip_reason = None
                if call_key in previous_keys:
                    skip_reason = (
                        "This exact tool call has already "
                        "been executed. Reuse the existing "
                        "evidence instead of repeating it."
                    )
                elif (
                    tool_name in DISCOVERY_TOOLS
                    and (
                        (
                            phase == "additional_evidence"
                            and tool_name in completed_discovery
                        )
                        or (
                            phase == "investigation"
                            and bool(self._schema_context_cache)
                        )
                    )
                ):
                    skip_reason = (
                        f"{tool_name} already succeeded "
                        "during the investigation. The "
                        "schema metadata is already known. "
                        "Use the existing metadata and "
                        "collect new analytical evidence."
                    )
                if skip_reason:
                    print("Tool call skipped:")
                    print(skip_reason)
                    self._emit_progress(
                        progress_callback,
                        {
                            "type": "tool",
                            "phase": phase,
                            "status": "skipped",
                            "title": f"Skipped {tool_name}",
                            "message": skip_reason,
                            "tool": tool_name,
                            "arguments": arguments,
                        },
                    )
                    trace.append(
                        {
                            "phase": phase,
                            "iteration": iteration + 1,
                            "tool": tool_name,
                            "arguments": arguments,
                            "skipped": True,
                            "reason": skip_reason,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": tool_name,
                            "content": (
                                "TOOL CALL NOT EXECUTED. "
                                + skip_reason
                            ),
                        }
                    )
                    continue
                # if discovery_outside_budget and tool_name not in DISCOVERY_TOOLS:
                #     analytical_actions += 1
                try:
                    tool_started = time.perf_counter()
                    (
                        tool_result,
                        tool_source,
                    ) = await self._execute_tool(
                        tool_name,
                        arguments,
                    )
                    tool_duration = time.perf_counter() - tool_started
                    print(
                        f"Tool source: {tool_source}"
                    )
                    print("Tool result:")
                    print(tool_result)
                    if self._tool_result_is_error(tool_result):
                        raise RuntimeError(tool_result)
                    if (
                        discovery_outside_budget
                        and tool_name not in DISCOVERY_TOOLS
                    ):
                        analytical_actions += 1
                    trace.append(
                        {
                            "phase": phase,
                            "iteration": iteration + 1,
                            "tool": tool_name,
                            "source": tool_source,
                            "arguments": arguments,
                            "result": tool_result,
                        }
                    )
                    self._emit_progress(
                        progress_callback,
                        {
                            "type": "tool",
                            "phase": phase,
                            "status": "complete",
                            "title": f"Completed {tool_name}",
                            "message": "Evidence returned by the tool.",
                            "tool": tool_name,
                            "source": tool_source,
                            "arguments": arguments,
                            "result": tool_result,
                            "duration_seconds": round(tool_duration, 2),
                        },
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": tool_name,
                            "content": tool_result,
                        }
                    )
                except Exception as exc:
                    import traceback

                    error_retries += 1

                    detailed_error = "".join(
                        traceback.format_exception(exc)
                    )

                    error_message = (
                        "Tool execution failed:\n"
                        + detailed_error
                    )

                    print(error_message)
                    self._emit_progress(
                        progress_callback,
                        {
                            "type": "tool",
                            "phase": phase,
                            "status": "error",
                            "title": f"{tool_name} failed",
                            "message": str(exc),
                            "tool": tool_name,
                            "arguments": arguments,
                        },
                    )
                    trace.append(
                        {
                            "phase": phase,
                            "iteration": iteration + 1,
                            "tool": tool_name,
                            "arguments": arguments,
                            "error": str(exc),
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": tool_name,
                            "content": error_message,
                        }
                    )
                    schema_context = self._verified_schema_context(
                        trace
                    )
                    recovery_content = (
                        TOOL_ERROR_RECOVERY_PROMPT
                        + """
                    The previous tool call FAILED.
                    Do not repeat the same tool call or the same SQL.
                    Correct the specific error before trying again.
                    For SQL:
                    - keep the correction focused;
                    - answer one analytical question per query;
                    - do not combine unrelated analyses with UNION merely to reduce tool calls;
                    - prefer a simple valid query over a large multi-purpose query.
                    A failed query is not evidence.
                    """
                    )
                    if schema_context:
                        recovery_content += (
                            "\n\nVERIFIED SCHEMA METADATA ALREADY COLLECTED\n\n"
                            + schema_context
                        )
                    messages.append(
                        {
                            "role": "system",
                            "content": recovery_content,
                        }
                    )
                    if error_retries >= MAX_TOOL_ERROR_RETRIES:
                        messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "The error-recovery allowance has been reached. "
                                    "Do not retry the failed analysis again. "
                                    "Continue using the valid evidence already collected, "
                                    "or choose a different simple analytical question if "
                                    "the evidence budget still allows it."
                                ),
                            }
                        )
            if budget_exhausted:
                break
        print(
            f"\n--- {phase.upper()} "

            f"TOOL LIMIT REACHED ---"
        )
        messages.append(
            {
                "role": "user",
                "content": TOOL_LIMIT_PROMPT,
            }
        )
        final_response = self.llm.chat(
            messages=messages,
            tools=None,
        )
        final_message = final_response.message
        messages.append(final_message)
        return final_message
    
    
    # ============================================================
    # EVIDENCE LEDGER
    # ============================================================
    @staticmethod
    def _is_evidence_bearing_trace_item(item):
        """
        Discovery belongs in trace, not in analytical evidence.
        SQL results and external API results are evidence-bearing.
        """
        if (
            item.get("error")
            or item.get("skipped")
            or "result" not in item
        ):
            return False
        result = item.get("result")
        # Some MCP servers return SQL failures as a normal textual
        # tool result instead of raising an exception. Those failures
        # belong in the operational trace, never in analytical evidence.
        if isinstance(result, str):
            normalized_result = result.strip().lower()
            error_prefixes = (
                "error:",
                "tool execution failed:",
            )
            if normalized_result.startswith(error_prefixes):
                return False
        if item.get("source") == "external":
            return True
        return item.get("tool") in EVIDENCE_TOOLS
    @classmethod
    def _build_evidence_from_trace(cls, trace):
        evidence = []
        for item in trace:
            if not cls._is_evidence_bearing_trace_item(
                item
            ):
                continue
            evidence.append(
                {
                    "id": f"ev_{len(evidence) + 1}",
                    "phase": item.get("phase"),
                    "source": item.get("source"),
                    "tool": item.get("tool"),
                    "arguments": item.get(
                        "arguments",
                        {},
                    ),
                    "result": item.get("result"),
                }
            )
        return evidence
    @staticmethod
    def _evidence_for_prompt(evidence):
        """
        Compact application-controlled evidence ledger for Qwen.
        This is deliberately built from actual tool results rather
        than from a previous model-written summary.
        """
        return json.dumps(
            evidence,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    # ============================================================
    # STRUCTURED ANALYSIS
    # ============================================================
    def _create_structured_analysis(
        self,
        question,
        evidence,
    ):
        evidence_json = self._evidence_for_prompt(
            evidence
        )
        messages = [
            {
                "role": "system",
                "content": STRUCTURED_SYNTHESIS_PROMPT,
            },
            {
                "role": "user",
                "content": f"""

Original business question:
{question}
Application-controlled evidence ledger:
{evidence_json}
Produce the final structured analysis now.
""",
            },
        ]
        response = self.llm.chat(
            messages=messages,
            tools=None,
            temperature=0.1,
        )
        raw = response.message.content
        try:
            return parse_structured_analysis(
                raw
            )
        except ValueError as exc:
            repair_messages = [
                {
                    "role": "system",
                    "content": STRUCTURED_REPAIR_PROMPT,
                },
                {
                    "role": "user",
                    "content": f"""

Validation error:
{exc}
Response to repair:
{raw}
""",
                },
            ]
            repair_response = self.llm.chat(
                messages=repair_messages,
                tools=None,
                temperature=0.0,
            )
            return parse_structured_analysis(
                repair_response.message.content
            )
    # ============================================================
    # POST-SYNTHESIS GROUNDING VALIDATION
    # ============================================================
    @staticmethod
    def _extract_evidence_ids(item):
        """
        Normalize harmless LLM formatting differences in evidence references.
        Accepted examples:
        - "ev_2"
        - "ev_2, ev_3"
        - ["ev_2", "ev_3"]
        - ["ev_2,ev_3"]
        This only splits/cleans references. The grounding validator still
        rejects every ID that does not exist in the application evidence ledger.
        """
        value = item.get("evidence", [])
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list):
            values = [
                evidence_id
                for evidence_id in value
                if isinstance(evidence_id, str)
            ]
        else:
            return []
        normalized = []
        for evidence_value in values:
            for evidence_id in evidence_value.split(","):
                evidence_id = evidence_id.strip()
                if evidence_id and evidence_id not in normalized:
                    normalized.append(evidence_id)
        return normalized
    @classmethod
    def _validate_grounding(
        cls,
        analysis,
        evidence,
    ):
        """Validate narrative and visualization grounding mechanically."""
        evidence_by_id = {item["id"]: item for item in evidence}
        valid_ids = set(evidence_by_id)
        for field in ("facts", "observations"):
            for item in analysis.get(field, []):
                ids = cls._extract_evidence_ids(item)
                if not ids:
                    raise ValueError(
                        f"Every {field[:-1]} must reference at least one evidence ID."
                    )
                invalid = [evidence_id for evidence_id in ids if evidence_id not in valid_ids]
                if invalid:
                    raise ValueError(
                        f"Invalid evidence reference in {field}: {invalid}"
                    )
        valid_visualizations = []
        for visualization in analysis.get("visualizations", []):
            raw_ref = visualization.get("evidence")
            candidates = []
            if isinstance(raw_ref, str):
                candidates = [part.strip() for part in raw_ref.split(",") if part.strip()]
            elif isinstance(raw_ref, list):
                for value in raw_ref:
                    if isinstance(value, str):
                        candidates.extend(
                            part.strip() for part in value.split(",") if part.strip()
                        )
            required_fields = []
            x_field = visualization.get("x")
            if isinstance(x_field, str) and x_field:
                required_fields.append(x_field)
            if visualization.get("type") == "combo":
                for series in visualization.get("series", []):
                    field = series.get("field")
                    if isinstance(field, str) and field:
                        required_fields.append(field)
            else:
                y_field = visualization.get("y")
                if isinstance(y_field, str) and y_field:
                    required_fields.append(y_field)
            selected_id = None
            for candidate in candidates:
                evidence_item = evidence_by_id.get(candidate)
                if not evidence_item:
                    continue
                evidence_result = str(evidence_item.get("result", ""))
                if all(field in evidence_result for field in required_fields):
                    selected_id = candidate
                    break
            if selected_id:
                visualization["evidence"] = selected_id
                valid_visualizations.append(visualization)
            # If no single evidence item can ground the chart, omit that chart.
            # The analysis itself remains valid and is not lost.
        analysis["visualizations"] = valid_visualizations
        for field in ("facts", "observations", "hypotheses", "recommendations"):
            for item in analysis.get(field, []):
                if isinstance(item, dict) and "evidence" in item:
                    item["evidence"] = cls._extract_evidence_ids(item)
        return analysis
    # ============================================================
    # PUBLIC ENTRY POINT
    # ============================================================
    async def run(
        self,
        question,
        mode="ask",
        progress_callback=None,
    ):
        mode = mode.lower().strip()
        if mode not in {
            "ask",
            "investigate",
        }:
            raise ValueError(
                f"Unsupported agent mode: {mode}"
            )
        tools = await self._get_all_tools()
        if mode == "ask":
            return await self._run_ask(
                question,
                tools,
                progress_callback,
            )
        return await self._run_investigation(
            question,
            tools,
            progress_callback,
        )
    # ============================================================
    # ASK MODE
    # ============================================================
    async def _run_ask(
        self,
        question,
        tools,
        progress_callback=None,
    ):
        trace = []
        messages = [
            {
                "role": "system",
                "content":
                    ANALYST_SYSTEM_PROMPT
                    + "\n\n"
                    + ANALYTICAL_INTERPRETATION_GUARDRAILS
                    + "\n\n"
                    + OUTPUT_LANGUAGE_PROMPT
                    + (
                        "\n\nSUPERSET SOURCE RULES:\n"
                        "You are connected to a live Apache Superset MCP server.\n"
                        "You MUST use the available MCP tools before answering "
                        "any question about the connected databases, datasets, "
                        "tables or their contents.\n"
                        "For questions about available databases, call list_databases.\n"
                        "For questions about datasets, call list_datasets.\n"
                        "Use get_dataset_info to inspect dataset metadata.\n"
                        "Use execute_sql for analytical questions requiring actual data.\n"
                        "Never answer from general knowledge when the question "
                        "concerns the connected Superset instance.\n"
                        "If no tool has been executed, do not claim that the "
                        "database or evidence ledger is empty.\n"
                        "The SQL database ID is fixed by the application.\n"
                        if self.source == "superset" else ""
                    ),
            },
            {
                "role": "user",
                "content":
                    question,
            },
        ]
        # Collect the focused evidence required to answer the question.
        await self._tool_loop(
            messages=messages,
            tools=tools,
            trace=trace,
            max_iterations=MAX_ASK_ITERATIONS,
            phase="ask",
            progress_callback=progress_callback,
        )
        evidence = self._build_evidence_from_trace(
            trace
        )

        # Include discovery metadata as evidence for ASK questions
        # when no analytical SQL evidence was collected.
        if not evidence:
            discovery_items = [
                item for item in trace
                if item.get("tool") in DISCOVERY_TOOLS
                and not item.get("error")
                and not item.get("skipped")
                and "result" in item
            ]

            evidence = [
                {
                    "id": f"ev_{i + 1}",
                    "phase": item.get("phase"),
                    "source": item.get("source"),
                    "tool": item.get("tool"),
                    "arguments": item.get("arguments", {}),
                    "result": item.get("result"),
                }
                for i, item in enumerate(discovery_items)
            ]


        self._emit_progress(
            progress_callback,
            {
                "type": "phase",
                "phase": "synthesis",
                "status": "running",
                "title": "Building the answer",
                "message": (
                    "Structuring the grounded answer and selecting "
                    "an appropriate visualization when useful."
                ),
            },
        )
        analysis = self._create_structured_analysis(
            question=question,
            evidence=evidence,
        )
        analysis = self._validate_grounding(
            analysis=analysis,
            evidence=evidence,
        )
        return build_final_response(
            mode="ask",
            analysis=analysis,
            evidence=evidence,
            trace=trace,
        )
   
    # ============================================================
    # INVESTIGATE MODE
    # ============================================================
    async def _run_investigation(
        self,
        question,
        tools,
        progress_callback=None,
    ):
        trace = []
        analysis_started = time.perf_counter()
        investigation_prompt = (
            ANALYST_SYSTEM_PROMPT
            + "\n\n"
            + INVESTIGATE_SYSTEM_PROMPT
            + "\n\n"
            + ADDITIONAL_INVESTIGATION_RULES
            + """
        ANALYTICAL QUERY DISCIPLINE
        Each analytical SQL query should normally answer ONE coherent
        analytical question.
        Examples of coherent analytical questions:
        - establish a baseline;
        - compare an outcome across one categorical dimension;
        - examine one numerical factor using meaningful ranges;
        - examine one temporal pattern.
        Do not combine unrelated analytical questions into one SQL statement
        merely to reduce the number of tool calls.
        In particular, do not UNION unrelated analyses that naturally return
        different schemas.
        Prefer several small, interpretable evidence queries over one large
        multi-purpose query.
        After every tool result, inspect the observation before deciding what
        to investigate next.
        """
        )
        if self.source == "superset":
            investigation_prompt += """
            SUPERSET SOURCE AND PHYSICAL SCHEMA VALIDATION

            You are connected to Apache Superset through MCP.
            The application fixes SQL database ID 2.

            IMPORTANT:
            Superset dataset metadata may include virtual or calculated
            columns that do not exist physically in PostgreSQL.

            Before executing analytical SQL:

            1. Discover the dataset using list_datasets and get_dataset_info.

            2. Verify the physical table columns using execute_sql:

            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
                AND table_name = '<actual_table_name>'
            ORDER BY ordinal_position

            3. Use only verified physical column names in subsequent SQL.

            4. Never assume that columns returned by get_dataset_info
            exist physically in PostgreSQL.

            5. Calculate derived metrics using SQL expressions.
            For example, revenue may be calculated as
            SUM("Quantity" * "Price").

            6. If SQL fails because a column does not exist,
            inspect the physical schema and reformulate the query.

            7. Never repeat a failed SQL query without correcting it.

            8. Do not invent percentages, totals or statistical relationships.
            Calculate them from actual SQL evidence.

            9. If the available evidence is insufficient, explicitly state
            the limitation instead of inventing conclusions.

            Use read-only SELECT queries.
            """
        if self._schema_context_cache:
            investigation_prompt += (
                "\n\nVERIFIED SCHEMA METADATA ALREADY DISCOVERED\n\n"
                + self._schema_context_cache
                + "\n\nReuse this verified schema metadata. "
                  "Do not call schema discovery tools again unless this metadata "
                  "is demonstrably insufficient."
            )
        self._emit_progress(
            progress_callback,
            {
                "type": "phase",
                "phase": "investigation",
                "status": "running",
                "title": "Understanding and investigating the data",
                "message": "Inspecting the available data, establishing a baseline and testing relevant factors.",
            },
        )
        print(
            "\n========================================"
        )
        print(
            "INVESTIGATION PHASE 1: "
            "PLANNING AND EVIDENCE COLLECTION"
        )
        print(
            "========================================"
        )
        investigation_messages = [
            {
                "role": "system",
                "content":
                    investigation_prompt,
            },
            {
                "role": "user",
                "content": f"""

Business question:
{question}
Conduct the investigation now.
Do not merely describe queries that could be executed.
Actually use the available tools to obtain the evidence.
First understand the available data.
Then establish the relevant baseline.
Then identify multiple plausible factors that can be tested.
Use the tools to investigate several of those factors.
For categorical factors, compare rates or percentages.
For numerical factors, use meaningful ranges, bins or summary
statistics rather than grouping by individual raw values.
Do not provide the final business conclusion yet.
When you believe enough initial evidence has been collected,
provide a concise evidence summary for the evaluator.
""",
            },
        ]
        initial_result = await self._tool_loop(
            messages=investigation_messages,
            tools=tools,
            trace=trace,
            max_iterations=MAX_INVESTIGATE_ITERATIONS,
            phase="investigation",
            progress_callback=progress_callback,
            discovery_outside_budget=True,
        )
        evidence_summary = (
            initial_result.content
        )
        verified_schema = self._verified_schema_context(trace)
        if verified_schema:
            self._schema_context_cache = verified_schema
        for evaluation_round in range(
            MAX_EVALUATION_ROUNDS
        ):
            print(
                "\n========================================"
            )
            print(
                f"EVIDENCE EVALUATION "

                f"{evaluation_round + 1}"
            )
            print(
                "========================================"
            )
            evidence = (
                self._build_evidence_from_trace(
                    trace
                )
            )
            evidence_ledger = (
                self._evidence_for_prompt(
                    evidence
                )
            )
            self._emit_progress(
                progress_callback,
                {
                    "type": "phase",
                    "phase": "evaluation",
                    "status": "running",
                    "title": "Evaluating the evidence",
                    "message": "Checking whether the collected evidence is sufficient for a responsible conclusion.",
                },
            )
            evaluation_messages = [
                {
                    "role": "system",
                    "content": (
                        EVIDENCE_EVALUATOR_PROMPT
                        + """
                    Evaluate sufficiency relative to the evidence and fields that are
                    actually available in the connected data source.
                    Do not mark the investigation INSUFFICIENT merely because an ideal
                    dataset could contain additional information that is not present.
                    Do not request unavailable qualitative feedback, surveys, interviews,
                    external benchmarks or other sources unless the available metadata
                    shows that such data exists.
                    A material gap must be testable using the currently available tools
                    and data.
                    Prioritize discriminative value over exhaustive coverage. The goal is
                    not to test every possible variable. The goal is to determine whether
                    the collected evidence supports a useful, responsible answer to the
                    business question.
                    If several independent pieces of evidence already reveal meaningful
                    differences, the investigation may be SUFFICIENT even though additional
                    variables could theoretically be explored.

                    MANDATORY ANALYTICAL EVIDENCE RULES:

                    Schema discovery is not analytical evidence.

                    Queries against information_schema, table descriptions,
                    dataset metadata and column definitions establish only
                    what data is available.

                    They do not establish business findings.

                    For an INVESTIGATE request, return INSUFFICIENT unless
                    the evidence ledger contains successful analytical SQL
                    queries against actual business data.

                    A proposed analysis is not an executed analysis.

                    Do not declare SUFFICIENT based on possible insights,
                    available columns, or suggested SQL queries.

                    When the user requests multiple business insights,
                    require multiple distinct findings supported by actual
                    query results.

                    If only schema discovery has been performed, explicitly
                    request analytical SQL queries in the next investigation round.
                    """
                    ),
                },
                {
                    "role": "user",
                    "content": f"""

Original business question:
{question}
Investigator summary:
{evidence_summary}
Application-controlled evidence ledger:
{evidence_ledger}
Evaluate whether this evidence is sufficient.
""",
                },
            ]
            evaluation_response = (
                self.llm.chat(
                    messages=evaluation_messages
                )
            )
            evaluation = (
                evaluation_response
                .message
                .content
                .strip()
            )
            print(evaluation)
            if evaluation.upper().startswith(
                "SUFFICIENT"
            ):
                break
            print(
                "\n========================================"
            )
            print(
                "ADDITIONAL EVIDENCE COLLECTION"
            )
            print(
                "========================================"
            )
            self._emit_progress(
                progress_callback,
                {
                    "type": "phase",
                    "phase": "additional_evidence",
                    "status": "running",
                    "title": "Collecting more evidence",
                    "message": "The evaluator identified material gaps, so the analyst is filling them.",
                },
            )
            verified_schema = self._verified_schema_context(
                trace
            )
            additional_system_prompt = investigation_prompt
            if verified_schema:
                additional_system_prompt += (
                    "\n\nVERIFIED SCHEMA METADATA\n\n"
                    + verified_schema
                    + "\n\nUse these verified table and column names. "
                      "Do not guess alternatives."
                )
            additional_messages = [
                {
                    "role": "system",
                    "content": additional_system_prompt,
                },
                {
                    "role": "user",
                    "content": f"""

Original business question:
{question}
Evidence already collected:
{evidence_summary}
The evidence evaluator identified these material gaps:
{evaluation}
Collect only the missing evidence using the available tools.
The schema has already been discovered. Do not repeat schema
discovery unless the previous discovery failed.
Do not repeat SQL queries already executed.
For numerical variables, do not group by individual raw values.
Use meaningful bins, ranges or summary statistics.
Do not simply recommend future queries.
Execute the necessary analysis.
When finished, provide a concise summary of the new evidence.
""",
                },
            ]
            additional_result = await self._tool_loop(
                messages=additional_messages,
                tools=tools,
                trace=trace,
                max_iterations=MAX_ADDITIONAL_EVIDENCE_ITERATIONS,
                phase="additional_evidence",
                progress_callback=progress_callback,
            )
            additional_evidence = (
                additional_result.content
            )
            evidence_summary += (
                "\n\nADDITIONAL EVIDENCE:\n"
                + additional_evidence
            )
        # ========================================================
        # FINAL STRUCTURED SYNTHESIS
        # ========================================================
        self._emit_progress(
            progress_callback,
            {
                "type": "phase",
                "phase": "synthesis",
                "status": "running",
                "title": "Building the conclusion",
                "message": "Producing the grounded structured analysis and visualization plan.",
            },
        )
        print(
            "\n========================================"
        )
        print(
            "FINAL STRUCTURED SYNTHESIS"
        )
        print(
            "========================================"
        )
        evidence = (
            self._build_evidence_from_trace(
                trace
            )
        )
        analysis = (
            self._create_structured_analysis(
                question=question,
                evidence=evidence,
            )
        )
        analysis = self._validate_grounding(
            analysis=analysis,
            evidence=evidence,
        )
        total_duration = time.perf_counter() - analysis_started
        result = build_final_response(
            mode="investigate",
            analysis=analysis,
            evidence=evidence,
            trace=trace,
        )
        result["timing"] = {
            "total_seconds": round(total_duration, 2)
        }
        return result
