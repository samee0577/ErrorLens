import asyncio
import json
import os

from dotenv import load_dotenv
from groq import Groq
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field
from typing import Optional

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL_NAME = "openai/gpt-oss-120b"
MAX_ITERATIONS = 10
MAX_RETRIES = 3

SYSTEM_PROMPT = (
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
)

USER_ERROR_REPORT = "I'm getting Total: -1520 when checking out items priced at 50 and 30 — I expected around 64. No error is thrown. Only investigate config.py, pricing.py, store.py, and main_test.py. Investigate the codebase and tell me the exact root cause."


class Diagnosis(BaseModel):
    root_cause_file: str = Field(
        description="The single file where the fix should be applied."
    )
    root_cause_line: Optional[int] = Field(
        description="The specific line number, if known."
    )
    reason: str = Field(
        description="Plain explanation of why this error is happening."
    )
    affected_files: list[str] = Field(
        description="Files OTHER than root_cause_file affected if the fix were "
        "applied elsewhere instead. Empty list if none."
    )
    recommendation: str = Field(
        description="One-line description of the fix, no code."
    )


def build_tool_schema(mcp_tools):
    """Convert the MCP server's tool list into the schema format Groq expects."""
    schema = []
    for tool in mcp_tools:
        schema.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            }
        })
    return schema


async def call_llm_with_retries(messages, tools=None, structured=False):
    """
    Calls the Groq API, retrying a few times if the request fails.
    Returns the response object, or None if every attempt failed.
    """
    request_kwargs = {"model": MODEL_NAME, "messages": messages}

    if structured:
        request_kwargs["tools"] = None
        request_kwargs["tool_choice"] = "none"
        request_kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "diagnosis",
                "schema": Diagnosis.model_json_schema(),
            },
        }
    elif tools:
        request_kwargs["tools"] = tools
        request_kwargs["tool_choice"] = "auto"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.chat.completions.create(**request_kwargs)
        except Exception as error:
            print(f"  [attempt {attempt}/{MAX_RETRIES}] request failed: {error}")

    return None


async def execute_tool_calls(session, message, messages):
    """
    Executes every tool call the model requested in this turn,
    appending each result back into the conversation.
    """
    messages.append(message)

    for tool_call in message.tool_calls:
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)

        result = await session.call_tool(tool_name, tool_args)
        result_text = result.content[0].text

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result_text,
        })


async def get_final_diagnosis(messages):
    """
    Asks the model for its final answer in the required structured format,
    and validates it against the Diagnosis schema.
    """
    messages.append(message_from_assistant := messages[-1])  # keep history intact
    messages.append({
        "role": "user",
        "content": "Now provide your final diagnosis in the required structured format.",
    })

    response = await call_llm_with_retries(messages, structured=True)
    if response is None:
        return None

    raw_json = response.choices[0].message.content
    return Diagnosis.model_validate_json(raw_json)


async def run_investigation():
    server_params = StdioServerParameters(command="uv", args=["run", "mcp_server.py"])

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            mcp_tools = (await session.list_tools()).tools
            tools = build_tool_schema(mcp_tools)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_ERROR_REPORT},
            ]

            for iteration in range(1, MAX_ITERATIONS + 1):
                response = await call_llm_with_retries(messages, tools=tools)
                if response is None:
                    print("Failed to get a response after retries.")
                    return

                message = response.choices[0].message
                called_tools = [tc.function.name for tc in (message.tool_calls or [])]
                print(f"[iteration {iteration}] tool_calls: {called_tools or 'none — ready to answer'}")

                if not message.tool_calls:
                    messages.append(message)
                    messages.append({
                        "role": "user",
                        "content": "Investigation is complete. Do NOT call any more tools. "
        "Respond with ONLY the JSON diagnosis object matching the required schema — "
        "no tool calls, no additional text.",
                    })

                    final_response = await call_llm_with_retries(messages, structured=True)
                    if final_response is None:
                        print("Failed to get a structured diagnosis after retries.")
                        return

                    try:
                        diagnosis = Diagnosis.model_validate_json(
                            final_response.choices[0].message.content
                        )
                        print(diagnosis.model_dump_json(indent=2))
                    except Exception as error:
                        print(f"Diagnosis validation failed: {error}")
                    return

                await execute_tool_calls(session, message, messages)

            print("Hit max iterations without a final answer.")


if __name__ == "__main__":
    asyncio.run(run_investigation())