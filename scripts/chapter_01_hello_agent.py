"""Chapter 01: SDK セットアップと最初の query()"""

import asyncio
from pathlib import Path

from dotenv import load_dotenv

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

load_dotenv()


# =============================================
# Step 1: 最小の query() 実行
# =============================================
async def step1_hello():
    print("=== Step 1: 最小の query() 実行 ===\n")

    async for message in query(
        prompt="「Hello from Claude Agent SDK!」と日本語で一言挨拶してください。短く1文で。",
        options=ClaudeAgentOptions(max_turns=1),
    ):
        if isinstance(message, ResultMessage):
            print("結果:", message.result)


# =============================================
# Step 2: ツール付きで query() を実行
# =============================================
async def step2_with_tools():
    print("\n=== Step 2: ツール付き query() ===\n")

    async for message in query(
        prompt="このリポジトリのトップレベルのファイル構成を簡潔に教えてください。",
        options=ClaudeAgentOptions(
            model="sonnet",
            cwd=str(Path.cwd()),
            allowed_tools=["Read", "Glob", "Grep"],
            permission_mode="dontAsk",
            max_turns=3,
        ),
    ):
        if isinstance(message, ResultMessage):
            print("結果:", message.result)


# =============================================
# Step 3: 代表的なメッセージ型をログ出力
# =============================================
async def step3_all_messages():
    print("\n=== Step 3: メッセージフローの可視化 ===\n")

    async for message in query(
        prompt="このリポジトリの pyproject.toml を読んで、プロジェクト名と依存パッケージを教えてください。",
        options=ClaudeAgentOptions(
            model="sonnet",
            cwd=str(Path.cwd()),
            allowed_tools=["Read", "Glob"],
            permission_mode="dontAsk",
            max_turns=3,
        ),
    ):
        if isinstance(message, SystemMessage):
            print(f"[system] サブタイプ: {message.subtype}")

        elif isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"[assistant] {block.text[:200]}")
                elif isinstance(block, ToolUseBlock):
                    print(
                        f"[tool_use] ツール: {block.name}, "
                        f"入力: {str(block.input)[:100]}"
                    )

        elif isinstance(message, UserMessage):
            if isinstance(message.content, list):
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        result_text = str(block.content)[:120] if block.content else ""
                        print(
                            f"[tool_result] ID: {block.tool_use_id}, "
                            f"結果: {result_text}..."
                        )

        elif isinstance(message, ResultMessage):
            print(f"\n[result] session_id: {message.session_id}")
            print(f"[result] コスト: ${message.total_cost_usd or 0:.4f}")
            print(f"[result] 最終結果:\n{message.result}")


# =============================================
# Step 4: ClaudeSDKClient の基本
# =============================================
async def step4_client():
    print("\n=== Step 4: ClaudeSDKClient の基本 ===\n")

    async with ClaudeSDKClient(
        options=ClaudeAgentOptions(model="sonnet", max_turns=1)
    ) as client:
        await client.query("Python の asyncio を一言で説明してください。短く1文で。")
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                print("結果:", msg.result)


# メイン実行
async def main():
    await step1_hello()
    await step2_with_tools()
    await step3_all_messages()
    await step4_client()


if __name__ == "__main__":
    asyncio.run(main())
