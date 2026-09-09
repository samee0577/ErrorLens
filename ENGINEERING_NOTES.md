# Design Notes / Decisions

Notes on the real engineering behind ErrorLens — decisions made, trade-offs weighed, and bugs actually hit and fixed. Not just what was built, but why it works this way.

---

## Why no RAG

ErrorLens's job is exact-reference lookup: "where is this function defined," "what does this file return." That's closer to `Array.find()` than `Array.filter()` + semantic ranking. RAG solves a different problem — retrieving relevant content from something too large to fit in context, or too fuzzy to search exactly. A personal codebase of a few dozen files doesn't need that; a direct `read_file`/`search_codebase` tool is simpler, faster, and more precise for this use case. RAG stays on the table only if the codebase being debugged grows into the thousands of files.

## Why a hand-rolled agent loop before MCP

Tool use → agents → MCP, in that order, was deliberate. Building the agent loop with plain Python functions first meant any bug encountered (and there were several) could only be an agent-logic bug — not an agent bug tangled up with an MCP client/server bug at the same time. Once the core loop was proven solid, swapping local functions for an MCP server was a clean, isolated change instead of debugging two new systems simultaneously.

## MCP: built, benchmarked, not the default

MCP was implemented as a full alternate path (`main_mcp.py` + `mcp_server.py`), wrapping the same three tools behind a standardized protocol instead of direct in-process calls.

**Initial assumption:** MCP would be noticeably slower, given the added subprocess + JSON-RPC overhead per tool call.

**What actually happened:** an early side-by-side comparison seemed to confirm this — but that test changed two variables at once (transport *and* model). Re-ran the comparison holding the model constant (same model, direct vs. MCP) and found **no meaningful difference** in speed or reliability. The earlier "MCP is slower" read was actually just a slower model being tested on the MCP side.

**Decision:** keep direct tool calls (`main.py`) as the version actually used day to day — for a single local tool with three functions, MCP's interoperability benefit (multiple apps sharing one tool server) doesn't apply. Kept `main_mcp.py` as a working, proven implementation rather than default usage — the value was in learning and proving the integration, not in running it permanently.

## Model choice: gpt-oss-120b over gpt-oss-20b and qwen3.8-27b

Compared three models on the same investigation task:

- **qwen/qwen3.8-27b** — consistently batched multiple tool calls into a single turn (e.g. 4 searches at once), converging in fewer iterations. But: violated the `affected_files` schema intent in 2 of 3 runs (including the root cause file in a field meant to exclude it), and has a much smaller per-minute token limit (7K) that a broad search query blew straight through during testing.
- **openai/gpt-oss-20b** — reliable baseline, but capped at the same size class as the free-tier limits allow, no headroom.
- **openai/gpt-oss-120b** — same daily rate limit as the 20b model (no cost to upgrading), and investigates one tool call at a time rather than batching — more deliberate, evidence-informed reasoning at the cost of a couple extra iterations.

**Decision:** `gpt-oss-120b`. For a debugging tool, being right matters more than being fast — the one-step-at-a-time behavior reads as more careful, not just slower.

## Real bugs hit and fixed

**Tool-avoidance** — the model occasionally answered from assumption/general knowledge instead of actually calling a tool to verify. Caught when it invented a plausible-sounding but entirely fictional explanation for `read_file`. Fixed by explicitly forbidding assumption-based answers in the system prompt, and later reinforced with `tool_choice="required"` on the first turn.

**Schema semantic drift** — `affected_files` was technically valid JSON but semantically wrong: it kept including the root cause file itself, despite the field name implying otherwise. Lesson: a Pydantic field name and type tell the model *nothing* about intended meaning — only an explicit `Field(description=...)` does.

**Tool-mode transition bug** — after investigation finished, the final structured-output call would sometimes still try to invoke a tool, despite `tool_choice="none"`, throwing `"Tool choice is none, but model called a tool."` This happened across multiple models (20b, 120b), ruling out "just a small-model problem." Fixed by making the transition instruction explicit and forceful ("Do NOT call any more tools") instead of just implying the investigation phase was over.

**Harmony-token leak** — `gpt-oss-20b`'s internal formatting system occasionally leaked a fragment (`<|channel|>commentary`) into a tool call name, producing a malformed request. Model-level quirk, not a bug in this code. Mitigated with retry logic rather than a permanent fix, since it's not something application code can prevent.

**search_codebase token bloat** — an early broad search query returned matches from `uv.lock`, a large auto-generated lockfile, and blew past the per-minute token limit on one request. Fixed by excluding known non-source files/extensions and capping result count, rather than assuming every file in the project is a legitimate search target.

**False-positive search matches** — a ripple-effect check searched for `"username"` and matched ErrorLens's own diagnosis code (which contains that string in an f-string), sending the investigation down an irrelevant path for one extra iteration. Fixed by excluding ErrorLens's own source files from search results — the tool debugging a codebase needs to not treat itself as part of that codebase.

**Ambiguous codebase, not a reasoning failure** — during stress testing, ErrorLens returned a *wrong* diagnosis once: it correctly found *a* bug matching the vague symptom description given, but it was an old test scenario left in the project folder, not the new one being tested. Not a logic failure — the codebase itself was ambiguous (two valid-looking "wrong discount" bugs coexisting). Lesson: diagnosis accuracy depends on codebase scoping as much as prompt or model quality.

## Stress test results

Tested against four structurally different bug types, all correctly diagnosed once codebase ambiguity was controlled for:

1. **Crashing cross-file key mismatch** — `KeyError` in one file, real cause in a different file entirely
2. **Silent logic bug, no traceback** — wrong numeric output, no exception at all, required investigating from a plain description of the wrong result
3. **"Lying traceback" scenario** — the file where bad output is *produced* (`pricing.py`) was three files away from the file where the bad *value originates* (`config.py`); correctly traced backward through the import chain instead of stopping at the first suspicious line
4. **Codebase-ambiguity case** — see above; the one genuine miss, and a useful one

## What's deliberately out of scope

- **Auto-fixing code** (would be "DevMate," a separate, larger project) — ErrorLens diagnoses only, by design, both in the system prompt and structurally in the output schema (no `fix_code` field exists)
- **Auto-capturing terminal errors** — a separate OS/process-hooking problem, unrelated to the AI/agent logic
- **Persistent history across runs** — deprioritized until single-session reliability with growing context is well understood; no point persisting a history the agent already struggles to reason over cleanly within one run
