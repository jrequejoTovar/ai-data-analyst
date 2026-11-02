# AI Data Analyst — Installation, Configuration, Startup & Validation

**Deployment guide | PostgreSQL · MCP · Apache Superset · Ollama · Flask**

This guide describes how to install, start, configure, and validate AI Data Analyst. It covers both a fully local demonstration and a deployment with services distributed across different machines. All application-to-data access is mediated by **Model Context Protocol (MCP)**.

**Configuration baseline:** This guide describes the **updated working version** of the project. The application already loads `.env` in its Python modules, the PostgreSQL/Superset MCP endpoints and Ollama settings are configurable, and the test scripts have already been adapted to run as Python modules. No source-code changes are required to follow this guide. The original ZIP supplied for review predates some of these updates; live startup and test execution were not performed as part of preparing this guide.

## 1. System architecture

```text
                         Web browser
                              |
                      http://127.0.0.1:5002
                              |
                              v
                   AI Data Analyst (Flask)
                  /            |              \
                 /             |               \
      MCP (HTTP/S)        MCP (HTTP/S)       Ollama API
       configured          configured         configured
       in .env             in .env            in .env
            |                 |                    |
            v                 v                    v
   PostgreSQL MCP        Superset MCP        Ollama server
    (PG Airman)        (separate service)     + qwen3:8b
            |                 |
        PostgreSQL         Apache Superset
         database           instance / API
```

**Key principle:** Flask does **not** require a direct PostgreSQL connection **or a direct Apache Superset API/base URL**. The application talks to each service *through its corresponding MCP endpoint*:

- `POSTGRES_MCP_URL` points to the **PostgreSQL MCP server**, not to the PostgreSQL database.
- `SUPERSET_MCP_URL` points to the **Superset MCP server**, not to Superset's native web interface or REST API.
- `OLLAMA_HOST_URL` points to the **Ollama API**, which is a separate connection and does **not** use MCP in this application.

The **Superset MCP service itself** must be configured to connect to the actual Apache Superset instance, including any required Superset URL and credentials. That is an **MCP-side responsibility**, not a Flask-side setting. The supplied Compose file does not start either Superset MCP or Apache Superset.

| Component | Local default | Deployment location / execution |
| --- | --- | --- |
| Flask web application | `http://127.0.0.1:5002` | Python process on application host |
| PostgreSQL MCP (PG Airman) | `http://localhost:8001/mcp` | `postgres-mcp` Compose container or external host |
| PostgreSQL 17 | `postgres:5432` inside Compose; `localhost:5432` published | `postgres` Compose container or external database |
| Superset MCP | `http://localhost:5008/mcp` | Optional, independently managed MCP server |
| Apache Superset | No Flask endpoint required | Wherever the Superset MCP server can reach it |
| Ollama | `http://localhost:11434` | Local or remote Ollama process |
| Default language model | `qwen3:8b` | Must exist on the configured Ollama host |

### 1.1 Project layout

```text
ai-data-analyst/
├── compose.yaml
├── README.md
├── .env                     # runtime settings (existing in the updated project)
├── database/
│   ├── data/employees.csv
│   └── init/
│       ├── 01_schema.sql
│       ├── 02_load_data.sql
│       ├── 03_metadata.sql
│       └── 04_security.sql
├── pg-airman-mcp/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/...
└── app/
    ├── app.py
    ├── agents.py
    ├── mcp_client.py
    ├── ollama_client.py
    ├── requirements.txt
    ├── tools.py
    ├── web_app/...
    └── test/
        ├── test_agent.py
        ├── test_clients.py
        ├── test_mcp.py
        ├── test_superset_mcp.py
        ├── test_ollama.py
        ├── test_tool_calling.py
        ├── test_external_tools.py
        └── test_external_tools_calling.py
```

The current application uses the `.env` file in the project root (`ai-data-analyst/.env`). The Python modules load these settings automatically.

## 2. Prerequisites

- macOS, Linux, or Windows with WSL2 (for the Unix shell commands below).
- Docker + Compose v2, or Podman + a working Compose provider, **only on hosts running the supplied containers**.
- Python 3.12 recommended, with `pip` and `venv`; the MCP image uses Python 3.12.
- Ollama installed/running locally **or** an accessible remote Ollama API.
- Sufficient RAM/disk for PostgreSQL, the containers, Python packages, and the `qwen3:8b` model.
- Internet access for initial downloads; external holiday-tool tests also require outbound HTTPS access.
- Local demo ports available: `5432`, `8001`, `5002`, `11434`, plus `5008` **if** Superset MCP is running locally.

Check the installed tooling:

```bash
python3 --version
python3 -m pip --version
docker --version
docker compose version
ollama --version
```

For Podman, replace the Docker commands with the equivalent `podman` commands.

## 3. Environment configuration (`.env`)

The existing `ai-data-analyst/.env` contains the following settings for a fully local environment:

```dotenv
# MCP endpoints used by the Flask application
POSTGRES_MCP_URL=http://localhost:8001/mcp
SUPERSET_MCP_URL=http://localhost:5008/mcp

# Ollama API endpoint and default model
OLLAMA_HOST_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=qwen3:8b
```

Use `KEY=value` without spaces around `=`. The MCP variables point to MCP endpoints, **not** directly to PostgreSQL or Superset. The values above are local defaults; replace them with reachable hosts or URLs in distributed deployments. The `.env` file is read by the application automatically, so no manual export step is needed.

| Variable | Read by | Meaning |
| --- | --- | --- |
| `POSTGRES_MCP_URL` | `app/mcp_client.py` | Streamable HTTP endpoint for PG Airman MCP |
| `SUPERSET_MCP_URL` | `app/mcp_client.py` | Streamable HTTP endpoint for Superset MCP |
| `OLLAMA_HOST_URL` | `app/ollama_client.py` | Ollama HTTP API base address |
| `OLLAMA_DEFAULT_MODEL` | `app/ollama_client.py` | Default LLM identifier in Ollama |
| `AIRMAN_MCP_DATABASE_URL` | PG Airman MCP **container/server** | PostgreSQL connection string; configured on the MCP side, **not** in Flask |

### 3.1 Application client configuration (already implemented)

The current application reads the two MCP endpoints from `.env` and registers them under the source identifiers used by the agent:

```python
MCP_URL = os.getenv("POSTGRES_MCP_URL", "http://localhost:8001/mcp")
SUPERSET_MCP_URL = os.getenv("SUPERSET_MCP_URL", "http://localhost:5008/mcp")

MCP_SERVERS = {
    "postgres": MCP_URL,
    "superset": SUPERSET_MCP_URL,
}
```

The Ollama client also uses the existing environment settings:

```python
OLLAMA_HOST = os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "qwen3:8b")
```

The Python modules **already load the root `.env` file before reading these values**, including when invoked through the test modules. No additional application or test-code edits are needed to configure a new environment: change the `.env` values and restart the affected Python process.

The MCP server itself manages its downstream connection: `AIRMAN_MCP_DATABASE_URL` configures PostgreSQL access on the PostgreSQL MCP host, and the Superset MCP server maintains its own Apache Superset connection. Flask does not require the database connection string or the native Superset URL.

## 4. First-time local installation

### 4.1 Unpack the project

```bash
unzip ai-data-analyst.zip
cd ai-data-analyst
```

The `docker compose` commands below run from the folder containing `compose.yaml`.

### 4.2 Start PostgreSQL and PostgreSQL MCP

```bash
docker compose up -d --build
# Or: podman compose up -d --build
```

The Compose setup starts:

1. `ai-analyst-postgres` — PostgreSQL 17, database `ai_analyst`.
2. `ai-analyst-postgres-mcp` — PG Airman MCP, Streamable HTTP on port `8001`, restricted mode.

On initial creation of an **empty** PostgreSQL data volume, initialization scripts create the schema, load `employees.csv`, add metadata, and configure the read-only account used by MCP. The included CSV contains **12,029 employee rows**.

```bash
docker compose ps
docker compose logs --tail=100 postgres
docker compose logs --tail=100 postgres-mcp

docker exec ai-analyst-postgres \
  psql -U admin -d ai_analyst \
  -c 'SELECT COUNT(*) AS employee_count FROM public.employees;'
```

Expected row count after a successful import: **12029**. PostgreSQL initialization scripts run only when the underlying data directory is empty; editing a script later does **not** automatically reapply it to an existing database volume.

### 4.3 Start Ollama and install the model

Install Ollama from <https://ollama.com/download> if needed. Start the local Ollama app/service, or use a terminal:

```bash
ollama serve
```

Do not start a second `ollama serve` if the local service is already running. In a separate terminal:

```bash
ollama pull qwen3:8b
ollama list
curl http://localhost:11434/api/tags
```

If `OLLAMA_HOST_URL` points to a remote server, pull the configured `OLLAMA_DEFAULT_MODEL` **on that remote Ollama instance**, and use the corresponding host URL for connectivity checks.

### 4.4 Install application dependencies

From `ai-data-analyst/`:

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The updated application uses `requests` (public-holiday tool), `sqlglot` (Superset SQL validation), and `python-dotenv` (`.env` loading). These packages must be available in the Python environment. If your current `requirements.txt` does not yet include all three, install the missing ones with:

```bash
python -m pip install requests sqlglot python-dotenv
```

This is a dependency-installation check, **not** a request to change the already configured Python clients or test scripts.

### 4.5 Superset (optional)

The local demo can start with PostgreSQL alone. To use Superset as a second source:

1. Start or obtain access to an **Apache Superset instance**.
2. Start or obtain access to its **Superset MCP server**, configured to communicate with that Superset instance.
3. Set `SUPERSET_MCP_URL` to **the MCP server's `/mcp` endpoint** (local default `http://localhost:5008/mcp`).
4. Confirm network connectivity from Flask to that MCP server, and the MCP server's connectivity/authentication to Superset.
5. In the application Admin UI, select `superset` as the active source. This choice changes which **MCP server** the agent uses; Flask does not need `SUPERSET_URL`, Superset API credentials, or a native Superset web URL.

**Authorization note:** The supplied `app/mcp_client.py` restricts Superset SQL calls to database ID `2` via `SUPERSET_ALLOWED_DATABASE_IDS = {2}`. If the authorized database has a different ID, review the allowlist and permissions deliberately; this is not an endpoint configuration issue.

### 4.6 Start Flask

From `ai-data-analyst/app/`, with the virtual environment active (the application loads `.env` automatically):

```bash
python3 app.py
```

Open **<http://127.0.0.1:5002>**. The original project README mentions `5000`, but `app/app.py` uses **5002**. The application defaults to the `postgres` source and exposes an Admin UI at `/admin` for selecting `postgres` or `superset`.

A simple manual question is: **“How many employees are in the database?”** It should be answered using a PostgreSQL MCP tool result, rather than invented model knowledge.

## 5. Normal startup / shutdown

From the project root, start the containerized components:

```bash
docker compose up -d
```

Verify that the configured Ollama instance is running. Then start Flask:

```bash
cd app
source .venv/bin/activate
python3 app.py
```

Stop Flask with `Ctrl+C`. From the project root, stop Compose services without deleting persisted database data:

```bash
docker compose down
```

**Warning:** `docker compose down -v` also removes the PostgreSQL data volume; only use it when intentionally resetting local development data.

## 6. Remote / distributed deployment

The endpoints are intentionally independent. Moving any of the services to another machine normally requires changing configuration, not the agent's business logic.

| Scenario | Flask connects to | MCP connects to | What changes |
| --- | --- | --- | --- |
| All local | Local PostgreSQL MCP, optional local Superset MCP, local Ollama | Local PostgreSQL / local Superset | Defaults in `.env` |
| PostgreSQL + PostgreSQL MCP remote | Remote PostgreSQL MCP | PostgreSQL on remote host | Change **only** `POSTGRES_MCP_URL` in Flask `.env` |
| PostgreSQL remote, MCP local | Local PostgreSQL MCP | Remote PostgreSQL | Change `AIRMAN_MCP_DATABASE_URL` **on MCP host** |
| Superset MCP remote | Remote Superset MCP | Configured Superset instance | Change **only** `SUPERSET_MCP_URL` in Flask `.env` |
| Ollama remote | Configured remote Ollama API | N/A | Change `OLLAMA_HOST_URL` and, optionally, `OLLAMA_DEFAULT_MODEL` |
| All independent | Two reachable MCP URLs + Ollama URL | Database and Superset reachable from their respective MCP hosts | Configure each endpoint independently |

For example, the **Flask host's** `.env` could contain:

```dotenv
POSTGRES_MCP_URL=https://pg-mcp.example.internal/mcp
SUPERSET_MCP_URL=https://superset-mcp.example.internal/mcp
OLLAMA_HOST_URL=http://ollama.example.internal:11434
OLLAMA_DEFAULT_MODEL=qwen3:8b
```

These are example addresses, **not** working endpoints. No PostgreSQL hostname, password, or Superset web/API URL is needed in Flask's configuration.

### 6.1 PostgreSQL MCP → PostgreSQL connection

The supplied Compose service configures this connection *inside MCP*:

```yaml
AIRMAN_MCP_DATABASE_URL: postgresql://ai_analyst:ai_analyst_readonly@postgres:5432/ai_analyst
```

Here `postgres` is a **Compose-internal service name**. To connect that MCP server to a database on another machine, set the connection string to an actual reachable DNS name or IP address, ideally with TLS and an appropriately privileged, read-only account:

```text
postgresql://<readonly_user>:<url_encoded_password>@db.example.internal:5432/<db_name>?sslmode=verify-full
```

A remote database must already contain the required tables/data: the bundled initialization scripts are **not** automatically applied to external databases. When running only MCP against a remote database, use an MCP-only Compose definition or remove the local database dependency; the supplied `compose.yaml` otherwise also launches PostgreSQL.

### 6.2 Superset MCP → Apache Superset connection

The Superset MCP service resolves and authenticates its connection to the real Superset instance. Its configuration depends on the **particular Superset MCP implementation/deployment** and is not included in the ZIP. The Flask process only needs a working `SUPERSET_MCP_URL`, such as `https://superset-mcp.example.internal/mcp`.

**Do not confuse** `http://localhost:5008/mcp` (the locally assumed **Superset MCP**) with a native Apache Superset web URL. The two services can run on separate hosts.

### 6.3 Network and security considerations

- Permit Flask → PostgreSQL MCP and Flask → Superset MCP over their configured HTTP(S) endpoints.
- Permit PG Airman MCP → PostgreSQL over its database port, normally `5432`.
- Permit Superset MCP → Apache Superset using whatever authenticated endpoint its own configuration requires.
- Permit Flask → Ollama over the configured API endpoint.
- Prefer HTTPS, a private network, VPN, or SSH tunneling for remote services. Do **not** publicly expose unauthenticated MCP or Ollama endpoints.
- A container's `localhost` refers to **that container**, not automatically to the host machine or another container.

For a simple demonstration with remote PostgreSQL MCP but no public listener, forward the remote MCP port to local `8001`:

```bash
ssh -N -L 8001:127.0.0.1:8001 user@mcp-server.example.internal
```

Then Flask can continue using `POSTGRES_MCP_URL=http://localhost:8001/mcp` as long as that tunnel is running and nothing else is using the local port.

## 7. Validation and test scripts

The project contains **eight standalone Python test scripts** in `app/test/`. They are **not** one unified `pytest` suite: most print diagnostic output, and only `test_agent.py` contains extensive response-shape assertions. Their results should be interpreted as connectivity or functional checks, not as comprehensive production certification.

### 7.1 Test execution prerequisites

Before running the tests, start the services required by each test, activate the application's virtual environment, and ensure that the Python dependencies have been installed. The **updated test modules are already configured to import application components and read the applicable `.env` settings**.

Execute the main test **from `ai-data-analyst/app/test/`**:

```bash
# Starting from ai-data-analyst/app/
source .venv/bin/activate
cd test
python3 -m test_agent
```

There is no need to set `PYTHONPATH` manually or edit test imports in the current project. If the virtual environment is already active and you are already inside `app/test`, only the last command is required.

### 7.2 Test inventory and what each test validates

| Test module (`app/test/`) | Purpose | Dependencies / notes |
| --- | --- | --- |
| `test_clients.py` | Tests the app's PostgreSQL MCP client by listing exposed tools, then sends a basic request through `OllamaClient`. | PG MCP + Ollama; a convenient first integration check. |
| `test_mcp.py` | Creates a direct MCP session; lists tools/schemas/tables, fetches `employees` metadata, and queries an employee count. | PG MCP + PostgreSQL. |
| `test_ollama.py` | Sends a basic prompt asking for the definition of employee attrition using the Ollama SDK. | Reachable Ollama server with the configured model available. |
| `test_tool_calling.py` | Provides a mock `get_employee_count` tool to the LLM and checks the *interaction flow*: proposed tool call → local execution → model response. | Ollama only; no MCP/database needed. The model may choose not to call the tool. |
| `test_external_tools.py` | Calls `get_public_holidays(country_code="ES", year=2026)` directly and prints its result. | `requests` and outbound internet access to the Nager.Date API. |
| `test_external_tools_calling.py` | Tests LLM function calling against the real `get_public_holidays` Python tool and feeds results back to the model. | Ollama, `requests`, and outbound internet. The model may choose not to request the tool. |
| `test_superset_mcp.py` | Connects to Superset MCP; searches for the `execute_sql` tool definition and prints its schema. | Reachable Superset MCP service. **Does not connect directly to the Superset web/API URL.** |
| `test_agent.py` | **End-to-end INVESTIGATE test:** asks why employees leave, calls `DataAnalystAgent`, and checks structured result fields. | Ollama + PostgreSQL MCP + PostgreSQL; default agent source is `postgres`. This is the main comprehensive smoke test. |

### 7.3 Suggested validation sequence

Run the following commands from **`ai-data-analyst/app/test/`**, with the virtual environment active. These are the regular module entry points in the updated project; no manual `PYTHONPATH` prefix or code corrections are required.

```bash
# 1. Check the app's MCP and Ollama client connectivity
python3 -m test_clients

# 2. Check the PostgreSQL MCP protocol and database metadata
python3 -m test_mcp

# 3. Check Ollama availability
python3 -m test_ollama

# 4. Check Ollama's tool-calling loop without using the database
python3 -m test_tool_calling

# 5. Optional tests of external tools (requires internet access)
python3 -m test_external_tools
python3 -m test_external_tools_calling

# 6. Optional Superset MCP tool discovery (requires Superset MCP)
python3 -m test_superset_mcp

# 7. Full end-to-end agent test (PostgreSQL + MCP + Ollama)
python3 -m test_agent
```

**Expected result of `test_agent`:** a JSON response with `mode: "investigate"`, `analysis` (including `answer`, `facts`, `observations`, `hypotheses`, `recommendations`, `visualizations`), `evidence`, and `trace`. The script checks the presence and types of these fields and, when successful, prints `TEST COMPLETED SUCCESSFULLY` with diagnostic counts. These checks validate the **response structure**, not the accuracy or causal validity of every generated insight.

`test_agent.py` runs the employee-attrition investigation against **PostgreSQL by default**. It does not provide end-to-end coverage of Superset. `test_superset_mcp.py` checks Superset MCP tool discovery; use the Superset source in the web application to validate the complete Superset analysis workflow.

### 7.4 Interpreting test results

These tests check different layers of the system. If a test fails, identify the affected layer before changing the application:

- **PostgreSQL/MCP tests:** verify the PostgreSQL MCP endpoint, MCP-side database credentials, and data initialization.
- **Superset MCP discovery:** verify the Superset MCP endpoint and its own connection to Superset; Flask does not require the native Superset URL.
- **Ollama/tool-calling tests:** verify the configured Ollama endpoint, the model installation, and support for tool calls.
- **External-tools tests:** verify outbound HTTPS/network access and the external holiday API.
- **Full agent test:** review the MCP calls, model output, structured-response validation, and server logs together.

Passing these tests gives confidence that the demo is operational. It does not amount to full load, security, or production-readiness testing.

## 8. Troubleshooting

| Symptom | Likely cause / corrective action |
| --- | --- |
| `.env` changes have no effect | Restart Flask or the test process; confirm that you edited the root `ai-data-analyst/.env` and used the correct variable names. The application already loads this file. |
| Ollama uses the wrong model/host | Verify `OLLAMA_HOST_URL` and `OLLAMA_DEFAULT_MODEL` in `.env`, model availability on the configured server, and restart the application. |
| Flask cannot reach PostgreSQL MCP | Verify `POSTGRES_MCP_URL`, MCP service status, port `8001`, firewall/VPN/SSH tunnel, and `/mcp` path. |
| Flask cannot reach Superset MCP | Verify `SUPERSET_MCP_URL` and that the **MCP server**, not just the Superset web application, is running/reachable. |
| Superset MCP can connect but Superset calls fail | Check the Superset MCP service's own Superset URL/auth, authorized database ID, and tool permissions. |
| Superset SQL rejected | The supplied app validates a single read-only SELECT and restricts allowed database IDs (currently `{2}`); `sqlglot` must be installed. |
| PostgreSQL MCP tools fail | Validate `AIRMAN_MCP_DATABASE_URL`, network access from the MCP host to PostgreSQL, and the database read-only role. |
| `postgres` hostname not found remotely | `postgres` is a Compose-network service name; use a reachable real database hostname outside that network. |
| Python cannot import an application module in tests | Confirm you are using the updated test files, activating the application's virtual environment, and running `python3 -m test_agent` from `app/test/`. |
| `ModuleNotFoundError: requests` | Install `requests` into the application's active virtual environment. |
| `ModuleNotFoundError: sqlglot` | Install `sqlglot` if using Superset SQL tooling. |
| `ModuleNotFoundError: dotenv` | Install `python-dotenv` if the client code calls `load_dotenv`. |
| No model found in Ollama | Run `ollama list` and pull the value of `OLLAMA_DEFAULT_MODEL` on the **configured Ollama server**. |
| Employee count not `12029` | Check import logs, existing Docker volume, dataset, and whether a remote DB has the same data. |
| SQL changes do not take effect | Database initialization scripts are only applied to a **new** PostgreSQL volume. |
| Web UI unavailable at `localhost:5000` | The supplied Flask app listens on `127.0.0.1:5002`. |
| External holiday tests fail | Check external internet/DNS/TLS and Nager.Date availability. These tests do not validate MCP. |

Useful logs from the project root:

```bash
docker compose ps
docker compose logs -f postgres postgres-mcp
```

Checking `http://host:8001/mcp` or `http://host:5008/mcp` with an ordinary browser GET is **not** a substitute for initializing an MCP client session; use the application's test scripts for protocol validation.

## 9. Security and deployment readiness

The supplied Compose file includes development-only credentials (`admin/admin` and `ai_analyst/ai_analyst_readonly`), publishes PostgreSQL port `5432` and MCP port `8001`, and runs Flask with `debug=True`. These are appropriate only for a controlled demo, **not** an Internet-exposed deployment.

Before wider use, adopt managed credentials; restrict network exposure; use TLS/authenticated proxy or VPN for remote MCP connections; maintain PostgreSQL read-only privileges; protect the Superset MCP-to-Superset connection; restrict Ollama access; disable Flask debug mode; pin and review dependencies; add observability, backups, and automated tests. Changing database initialization SQL does not update a populated volume or rotate existing passwords.

## 10. Final verification checklist

- [ ] The PostgreSQL database is initialized (or the external database is ready and accessible from its MCP).
- [ ] PostgreSQL MCP is running and offers the expected restricted query/discovery tools.
- [ ] The `.env` file defines both MCP URLs and `OLLAMA_HOST_URL` / `OLLAMA_DEFAULT_MODEL`.
- [ ] The existing environment-aware client configuration loads `.env` at startup.
- [ ] The application communicates with Superset through **Superset MCP only**, with no Flask-side Superset API URL.
- [ ] The Superset MCP service can authenticate to the Superset instance, if that source is enabled.
- [ ] The configured Ollama host has the configured model installed.
- [ ] The Flask virtual environment has `requests`, `sqlglot` (if needed), and `python-dotenv` (if used).
- [ ] From `app/test`, `python3 -m test_clients` completes.
- [ ] From `app/test`, `python3 -m test_mcp` completes.
- [ ] From `app/test`, `python3 -m test_agent` completes and prints a structured result.
- [ ] If Superset is enabled, `python3 -m test_superset_mcp` completes against `SUPERSET_MCP_URL`.
- [ ] Flask serves the UI at `http://127.0.0.1:5002`.
- [ ] Remote services are secured and firewall rules allow only the required paths.

---

**Source basis:** The originally supplied `compose.yaml`, database initialization files, Flask application, MCP/Ollama clients, and eight `app/test/*.py` scripts, plus the confirmed subsequent changes to `.env` loading and test execution. This guide assumes those changes are **already implemented** in the current project and does not request further code modification.
