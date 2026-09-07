from dotenv import load_dotenv
from groq import Groq
import os
import json
from tools import read_file, get_file_structure, search_codebase
from pydantic import BaseModel, Field
from typing import Optional

class Diagnosis(BaseModel):
    root_cause_file: str = Field(description="The single file where the fix should be applied.")
    root_cause_line: Optional[int] = Field(description="The specific line number, if known.")
    reason: str = Field(description="Plain explanation of why this error is happening.")
    recommendation: str = Field(description="One-line description of what to change, no code.")
    affects_files: list[str] = Field(description="Files OTHER than root_cause_file affected if the fix were applied elsewhere. Empty list if none.")

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

tools = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Reads and returns the full contents of a file given its path.",
        "parameters": {"type": "object", "properties": {
            "filepath": {"type": "string", "description": "Path to the file to read."}
        }, "required": ["filepath"]}
    }},
    {"type": "function", "function": {
        "name": "get_file_structure",
        "description": "Lists all files in the project, optionally scoped to a subfolder.",
        "parameters": {"type": "object", "properties": {
            "directory": {"type": "string", "description": "Optional subfolder, relative to project root."}
        }, "required": []}
    }},
    {"type": "function", "function": {
        "name": "search_codebase",
        "description": "Searches all files for a keyword, returning matching file paths and line numbers.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Keyword or text to search for."},
            "directory": {"type": "string", "description": "Optional subfolder to search within."}
        }, "required": ["query"]}
    }}
]

available_tools = {
    "read_file": lambda args: read_file(args["filepath"]),
    "get_file_structure": lambda args: get_file_structure(args.get("directory")),
    "search_codebase": lambda args: search_codebase(args["query"], args.get("directory"))
}

def call_llm(messages, use_tools=True, structured=False):
    """One retry-wrapped LLM call, reused for both investigation and final answer."""
    kwargs = {"model": "openai/gpt-oss-120b", "messages": messages}
    if use_tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if structured:
        kwargs["tools"] = None
        kwargs["tool_choice"] = "none"
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "diagnosis", "schema": Diagnosis.model_json_schema()}
        }

    for attempt in range(3):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            print(f"  [retry {attempt+1}/3] {e}")
    return None

messages = [
    {"role": "system", "content": (
        "You are ErrorLens, a codebase debugging assistant. Never answer from "
        "assumption or general knowledge — always verify using the available tools "
        "before answering. If you haven't actually read or searched for something, "
        "say you don't know rather than guessing. If the user has not provided an "
        "actual error message or traceback, do not investigate — ask them to paste "
        "the exact error output first. When a mismatch spans two files, use search "
        "to check whether the relevant function, key, or variable is used elsewhere "
        "before deciding the root cause. Recommend the single safer location to "
        "point to. Do NOT suggest code fixes or rewrites — diagnosis only."
        "You must call read_file on every file mentioned in the traceback before giving any diagnosis, even if the cause seems obvious from the error message alone."
    )},
    {"role": "user", "content": "I'm getting Total: -1520 when checking out items priced at 50 and 30 — I expected around 64. No error is thrown. im running main_test.py. Investigate the codebase and tell me the exact root cause."},
]

MAX_ITERATIONS = 10

for i in range(MAX_ITERATIONS):
    response = call_llm(messages)
    if response is None:
        print("Failed after retries.")
        break

    message = response.choices[0].message
    print(f"[iteration {i+1}] tool_calls: {[tc.function.name for tc in (message.tool_calls or [])] or 'NONE — final answer ready'}")

    if not message.tool_calls:
        messages.append(message)
        messages.append({"role": "user", "content": "Investigation is complete. Do NOT call any more tools. "
        "Respond with ONLY the JSON diagnosis object matching the required schema — "
        "no tool calls, no additional text."})

        final_response = call_llm(messages, structured=True)
        if final_response:
            try:
                diagnosis = Diagnosis.model_validate_json(final_response.choices[0].message.content)
                print(diagnosis.model_dump_json(indent=2))
            except Exception as e:
                print(f"Validation failed: {e}")
        else:
            print("Failed to get structured diagnosis.")
        break

    messages.append(message)
    for tool_call in message.tool_calls:
        args = json.loads(tool_call.function.arguments)
        result = available_tools[tool_call.function.name](args)
        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
else:
    print("Hit max iterations without a final answer.")