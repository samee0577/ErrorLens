# ErrorLens

A terminal-based AI debugging assistant that reads your actual codebase to trace the *real* root cause of errors — not just what the traceback points at, but what's actually wrong, even when the bug spans multiple files.

Built on Groq's free tier, using a hand-rolled agent loop with tool calling and structured output. Read-only by design — ErrorLens diagnoses, it never edits your code.

## Why

A stack trace tells you *where* your code crashed. It doesn't tell you *why* — especially when the real problem is in a different file than the one that crashed. ErrorLens investigates like a developer would: read the file that crashed, follow the imports, check where else a variable or key is used, and only then explain the actual root cause.

## What it does

- Takes a pasted error (a traceback, or a plain description of wrong behavior — no crash required)
- Investigates your actual project files using three tools: reading files, listing the project structure, and searching for keywords across the codebase
- Traces the problem across as many files as it takes, deciding what to look at next based on what it's already found
- When two files are mismatched (e.g. one returns data the other doesn't expect), it reasons about which one is the *safer* place to fix — checking whether changing the other side would break something else
- Returns a structured diagnosis: file, line, reason, safer fix location, and any other files that would be affected — no code rewrites, no unsolicited fixes

## Example

Input:
```
I'm getting -1900 instead of 80, no error is thrown.
```

Output:
```json
{
  "root_cause_file": "cart.py",
  "root_cause_line": 4,
  "reason": "get_final_price forwards a whole-number percent (20) to apply_discount, which expects a decimal (0.2), so the calculation resolves to 100 - (100 * 20) = -1900 instead of 80.",
  "affected_files": [],
  "recommendation": "Convert the whole-number discount_percent to a decimal before passing it to apply_discount."
}
```

No traceback was given — ErrorLens investigated the codebase from a plain description of the wrong output and correctly traced a silent logic bug across two files.

## How it works

1. **Agent loop** — the LLM decides which tool to call next based on what it's already learned, repeating until it has enough information (or hits a safety cap on iterations)
2. **Three tools**: `read_file`, `get_file_structure`, `search_codebase` — each a plain Python function, described to the LLM via a JSON schema, dispatched through a name → function lookup
3. **Structured output** — once investigation is done, a final call forces the answer into a strict schema (validated with Pydantic), so the diagnosis is always machine-readable
4. **MCP variant included** (`main_mcp.py`) — the same three tools also exposed through a standalone MCP server (`mcp_server.py`), connected to over stdio. Built to prove out MCP integration; the direct-call version (`main.py`) is faster for a single local project like this one and is the one actually used day-to-day

## Setup

```bash
uv sync
```

Create a `.env` file in the project root:
```
GROQ_API_KEY=your_key_here
```

## Usage

```bash
uv run main.py
```

Paste your error (or a description of the wrong behavior) when prompted, or edit the hardcoded report at the top of `main.py` for now — runtime input is a planned improvement.

Update: ErrorLens now prompts for input at runtime instead of requiring a code edit

To try the MCP version instead:
```bash
uv run main_mcp.py
```

## Project structure

```
├── main.py           # direct tool-calling agent loop (primary version)
├── main_mcp.py        # same logic, tools served over MCP instead of direct calls
├── mcp_server.py      # MCP server exposing the three tools
├── tools.py           # read_file, get_file_structure, search_codebase
├── pyproject.toml
└── .env               # GROQ_API_KEY (not committed)
```

## Scope

ErrorLens is deliberately read-only and diagnosis-only. It does not:
- Auto-fix or rewrite code
- Use RAG (this is an exact-reference lookup problem, not a semantic search one)
- Persist history between runs (yet)

Two upgrades are scoped separately, deliberately not part of this version:
- **DevMate** — a broader agent that also edits/fixes code
- **Auto-capture** — automatically intercepting terminal errors instead of copy-paste

## Known limitations

- Occasional model-level glitch where the LLM tries to call a tool during the structured-output step, despite being told not to — retried automatically, rarely surfaces
- `affected_files` in the diagnosis is the least consistent field — treat it as a hint, not a guarantee
- Currently tuned and tested against small, controlled multi-file scenarios; not yet stress-tested on a large real-world codebase

## Built with

- Python 3.12, managed with [uv](https://github.com/astral-sh/uv)
- [Groq](https://groq.com) (`openai/gpt-oss-120b`) — free tier, OpenAI-compatible API
- [Pydantic](https://docs.pydantic.dev) — structured output validation
- [MCP](https://modelcontextprotocol.io) — for the alternate tool-serving architecture
