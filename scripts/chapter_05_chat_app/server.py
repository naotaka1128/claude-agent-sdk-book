"""Chapter 05: React チャット UI — FastAPI + WebSocket バックエンド

起動方法:
  cd scripts/chapter_05_chat_app
  uv run uvicorn server:app --host 0.0.0.0 --port 3001 --reload
"""

import asyncio
import datetime
import json
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import (
    PermissionResultAllow,
    ToolPermissionContext,
)

load_dotenv()
app = FastAPI()

pending_approvals: dict[str, asyncio.Future] = {}


async def handle_ask_user_via_ws(
    ws: WebSocket, tool_input: dict[str, Any]
) -> PermissionResultAllow:
    request_id = f"ask_{id(ws)}_{asyncio.get_event_loop().time()}"
    await ws.send_json(
        {
            "type": "ask_user",
            "requestId": request_id,
            "questions": tool_input.get("questions", []),
        }
    )
    future: asyncio.Future = asyncio.get_event_loop().create_future()
    pending_approvals[request_id] = future
    try:
        response = await future
        return PermissionResultAllow(
            updated_input={
                "questions": tool_input.get("questions", []),
                "answers": response.get("answers", {}),
            }
        )
    finally:
        pending_approvals.pop(request_id, None)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    client: ClaudeSDKClient | None = None

    # WebSocket メッセージを別タスクで読み、種類ごとに振り分ける。
    # ask_response は即座に Future を解決し、
    # それ以外 (message 等) は Queue に入れてメインループで処理する。
    msg_queue: asyncio.Queue = asyncio.Queue()

    async def ws_reader():
        try:
            while True:
                raw = await ws.receive_text()
                data = json.loads(raw)
                if data["type"] == "ask_response":
                    request_id = data.get("requestId", "")
                    if request_id in pending_approvals:
                        pending_approvals[request_id].set_result(data)
                else:
                    await msg_queue.put(data)
        except WebSocketDisconnect:
            await msg_queue.put(None)

    reader_task = asyncio.create_task(ws_reader())

    try:
        while True:
            data = await msg_queue.get()
            if data is None:
                break

            if data["type"] == "message":

                async def can_use_tool(
                    tool_name: str,
                    tool_input: dict[str, Any],
                    context: ToolPermissionContext,
                ) -> PermissionResultAllow:
                    if tool_name == "AskUserQuestion":
                        return await handle_ask_user_via_ws(ws, tool_input)
                    return PermissionResultAllow(updated_input=tool_input)

                if client is None:
                    # 第3章で使った SerpApi MCP を組み込む
                    serpapi_key = os.environ.get("SERPAPI_API_KEY", "")
                    mcp_servers = {}
                    mcp_tools = []
                    if serpapi_key:
                        mcp_servers["serpapi"] = {
                            "type": "http",
                            "url": f"https://mcp.serpapi.com/{serpapi_key}/mcp",
                        }
                        mcp_tools = ["mcp__serpapi__*"]

                    options = ClaudeAgentOptions(
                        model="sonnet",
                        system_prompt={
                            "type": "preset",
                            "preset": "claude_code",
                            "append": (
                                "あなたは旅行プランナーです。"
                                "ユーザーの旅行の希望を丁寧にヒアリングし、"
                                "対話を通じてプランをブラッシュアップしてください。"
                                "まず AskUserQuestion で旅行の詳細"
                                " (日程、予算、興味、メンバー構成など) "
                                "を確認してから、プランを提案してください。"
                                "一方的にプランを提示せず、"
                                "ユーザーとの対話を重視してください。"
                                "AskUserQuestion の制約: "
                                "質問は最大4つ、各質問の選択肢は2〜4個まで。"
                                f"今日の日付は {datetime.date.today().isoformat()} です。"
                                "フライトや観光情報の検索には"
                                " SerpApi の search ツールを活用してください。"
                            ),
                        },
                        **({"mcp_servers": mcp_servers} if mcp_servers else {}),
                        include_partial_messages=True,
                        can_use_tool=can_use_tool,
                        permission_mode="acceptEdits",
                        thinking={"type": "enabled", "budget_tokens": 10000},
                        allowed_tools=[
                            "Read",
                            "Glob",
                            "Grep",
                            "Edit",
                            "Write",
                            "Bash",
                            "TodoWrite",
                            *mcp_tools,
                        ],
                    )
                    client = ClaudeSDKClient(options=options)
                    await client.connect()

                await client.query(data.get("message", ""))

                async for msg in client.receive_response():
                    if isinstance(msg, StreamEvent):
                        event = msg.event
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                await ws.send_json(
                                    {
                                        "type": "stream_delta",
                                        "text": delta["text"],
                                    }
                                )
                            elif delta.get("type") == "thinking_delta":
                                await ws.send_json(
                                    {
                                        "type": "thinking_delta",
                                        "text": delta.get("thinking", ""),
                                    }
                                )

                    elif isinstance(msg, AssistantMessage):
                        text_parts = []
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                text_parts.append(block.text)
                            elif isinstance(block, ThinkingBlock):
                                pass
                            elif isinstance(block, ToolUseBlock):
                                input_summary = str(block.input)[:200]
                                await ws.send_json(
                                    {
                                        "type": "tool_use",
                                        "name": block.name,
                                        "input": input_summary,
                                    }
                                )
                                if block.name == "TodoWrite":
                                    await ws.send_json(
                                        {
                                            "type": "todo_update",
                                            "todos": block.input.get("todos", []),
                                        }
                                    )
                        if text_parts:
                            await ws.send_json(
                                {
                                    "type": "assistant",
                                    "text": "".join(text_parts),
                                    "toolCalls": [],
                                }
                            )

                    elif isinstance(msg, ResultMessage):
                        await ws.send_json(
                            {
                                "type": "result",
                                "result": msg.result,
                                "cost": msg.total_cost_usd or 0,
                                "turns": msg.num_turns,
                                "sessionId": msg.session_id,
                            }
                        )

    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        if client:
            await client.disconnect()


_client_dist = os.path.join(os.path.dirname(__file__), "client", "dist")
if os.path.isdir(_client_dist):
    app.mount("/", StaticFiles(directory=_client_dist, html=True), name="static")
