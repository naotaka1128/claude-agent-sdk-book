"""Chapter 03: MCP でフライト検索機能を追加しよう"""

import asyncio
import os
from typing import Any

from dotenv import load_dotenv

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
    ToolUseBlock,
)
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

load_dotenv()


def log_tool_use(tool_name: str, tool_input: Any) -> None:
    from datetime import datetime

    timestamp = datetime.now().strftime("%H:%M:%S")
    input_summary = str(tool_input)[:80]
    print(f"  [{timestamp}] 🔧 {tool_name}: {input_summary}...")


async def handle_ask_user_question(
    tool_input: dict[str, Any],
) -> PermissionResultAllow:
    answers: dict[str, str] = {}
    for q in tool_input.get("questions", []):
        print(f"\n💬 {q['header']}: {q['question']}")
        options = q.get("options", [])
        if options:
            for i, opt in enumerate(options):
                desc = f" - {opt['description']}" if opt.get("description") else ""
                print(f"  {i + 1}. {opt['label']}{desc}")
        response = input("あなたの回答: ").strip()
        if options:
            try:
                idx = int(response) - 1
                if 0 <= idx < len(options):
                    response = options[idx]["label"]
            except ValueError:
                pass
        answers[q["question"]] = response
    return PermissionResultAllow(
        updated_input={
            "questions": tool_input.get("questions", []),
            "answers": answers,
        }
    )


async def handle_tool_request(
    tool_name: str,
    tool_input: dict[str, Any],
    context: ToolPermissionContext,
) -> PermissionResultAllow | PermissionResultDeny:
    if tool_name == "AskUserQuestion":
        return await handle_ask_user_question(tool_input)
    return PermissionResultAllow(updated_input=tool_input)


async def main():
    print("=== SerpApi MCP フライト検索 ===\n")

    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        print("SERPAPI_API_KEY が設定されていません。")
        print(".env ファイルに SERPAPI_API_KEY=xxx を設定してください。")
        return

    origin = input("出発地の空港コード (例: NRT): ").strip()
    destination = input("目的地の空港コード (例: FCO): ").strip()
    departure = input("出発日 (YYYY-MM-DD): ").strip()
    return_date = input("帰着日 (YYYY-MM-DD、片道なら空欄): ").strip()

    if not origin or not destination or not departure:
        print("出発地・目的地・出発日は必須です。")
        return

    print(f"\n✈️ {origin} → {destination} のフライトを検索します...\n")
    print("--- ツール実行タイムライン ---")

    mcp_url = f"https://mcp.serpapi.com/{api_key}/mcp"

    options = ClaudeAgentOptions(
        model="sonnet",
        mcp_servers={
            "serpapi": {
                "type": "http",
                "url": mcp_url,
            },
        },
        allowed_tools=["mcp__serpapi__*"],
        permission_mode="dontAsk",
        max_turns=15,
        include_partial_messages=True,
        can_use_tool=handle_tool_request,
    )

    return_info = f"帰着日: {return_date}\n" if return_date else "片道\n"
    prompt = (
        f"以下の条件でフライトを検索し、"
        f"おすすめのフライトをレポートしてください。\n\n"
        f"出発地: {origin}\n"
        f"目的地: {destination}\n"
        f"出発日: {departure}\n"
        f"{return_info}\n"
        f"SerpApi の search ツールを engine=google_flights で"
        f"使ってください。結果は日本語でまとめてください。"
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        async for msg in client.receive_response():
            if isinstance(msg, StreamEvent):
                event = msg.event
                if (
                    event.get("type") == "content_block_delta"
                    and event.get("delta", {}).get("type") == "text_delta"
                ):
                    print(
                        event["delta"]["text"],
                        end="",
                        flush=True,
                    )

            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        log_tool_use(block.name, block.input)

            elif isinstance(msg, ResultMessage):
                print("\n\n--- 完了 ---")
                print(f"コスト: ${msg.total_cost_usd or 0:.4f}")
                print(f"ターン数: {msg.num_turns}")


if __name__ == "__main__":
    asyncio.run(main())
