import asyncio
import json
import queue
import threading

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from agents import DataAnalystAgent, RouterAgent


app = Flask(
    __name__,
    template_folder="web_app/templates",
    static_folder="web_app/static",
)

router = RouterAgent()

active_source = "postgres"
source_lock = threading.Lock()
ALLOWED_SOURCES = {"postgres", "superset"}


@app.get("/")
def index():
    return render_template("analyst.html")


@app.get("/analyst")
def analyst():
    return render_template("analyst.html")


@app.get("/admin")
def admin():
    return render_template("admin.html")


@app.get("/api/admin/source")
def get_active_source():
    with source_lock:
        source = active_source

    return jsonify({"source": source})


@app.put("/api/admin/source")
def set_active_source():
    global active_source

    payload = request.get_json(silent=True) or {}
    source = payload.get("source")

    if source not in ALLOWED_SOURCES:
        return jsonify({
            "error": "Invalid MCP source."
        }), 400

    with source_lock:
        active_source = source

    return jsonify({
        "source": source,
        "status": "updated"
    })

@app.post("/api/analyze")
def analyze():
    """
    Stream newline-delimited JSON (NDJSON).

    The browser receives real operational events while the router
    and analyst are working. These events expose phases, tool calls,
    SQL arguments/results and recovery — never private chain-of-thought.
    """
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()


    if not question:
        return jsonify({"error": "Question is required."}), 400

    # Capture the active MCP source for this analysis
    with source_lock:
        selected_source = active_source

    events = queue.Queue()
    finished = object()

    def emit(event):
        events.put(event)

    async def execute():
        try:
            emit({
                "type": "phase",
                "phase": "routing",
                "status": "running",
                "title": "Routing the question",
                "message": "Selecting the appropriate analytical strategy.",
            })

            strategy = await router.classify(question)

            emit({
                "type": "strategy",
                "phase": "routing",
                "status": "complete",
                "title": f"Strategy selected: {strategy['selected'].upper()}",
                "message": strategy["reason"],
                "strategy": strategy,
            })

            agent = DataAnalystAgent(source=selected_source)

            result = await agent.run(
                question=question,
                mode=strategy["selected"],
                progress_callback=emit,
            )

            result["source"] = selected_source

            result["strategy"] = strategy

            emit({
                "type": "phase",
                "phase": "complete",
                "status": "complete",
                "title": "Analysis complete",
                "message": "The grounded response is ready.",
            })

            emit({
                "type": "result",
                "data": result,
            })

        except Exception as exc:
            app.logger.exception("Analysis failed")
            emit({
                "type": "error",
                "message": str(exc),
            })
        finally:
            events.put(finished)

    def worker():
        asyncio.run(execute())

    threading.Thread(target=worker, daemon=True).start()

    @stream_with_context
    def generate():
        while True:
            item = events.get()

            if item is finished:
                break

            yield json.dumps(
                item,
                ensure_ascii=False,
                default=str,
            ) + "\n"

    return Response(
        generate(),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5002,
        debug=True,
        threaded=True,
    )
