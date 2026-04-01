"""Chapter 02: 旅行プランナー — ClaudeSDKClient で対話型ワークフロー"""

import asyncio
from pathlib import Path
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


def parse_response(response: str, options: list[dict]) -> str:
    """番号入力なら option の label に変換、それ以外は自由回答として返す"""
    try:
        indices = [int(s.strip()) - 1 for s in response.split(",")]
        labels = [options[i]["label"] for i in indices if 0 <= i < len(options)]
        return ", ".join(labels) if labels else response
    except ValueError:
        return response


async def handle_ask_user_question(
    tool_input: dict[str, Any],
) -> PermissionResultAllow:
    """AskUserQuestion のハンドリング: 選択肢 + 自由入力対応"""
    answers: dict[str, str] = {}

    for q in tool_input.get("questions", []):
        print(f"\n💬 {q['header']}: {q['question']}")

        options = q.get("options", [])
        if options:
            for i, opt in enumerate(options):
                desc = f" - {opt['description']}" if opt.get("description") else ""
                print(f"  {i + 1}. {opt['label']}{desc}")
            if q.get("multiSelect"):
                print("  (番号をカンマ区切りで入力、または自由回答)")
            else:
                print("  (番号を入力、または自由回答)")

        response = input("あなたの回答: ").strip()
        answers[q["question"]] = (
            parse_response(response, options) if options else response
        )

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

    print(f"\n🔧 Claude が {tool_name} を使おうとしています")
    if tool_name == "Bash":
        print(f"   コマンド: {tool_input.get('command')}")
    else:
        input_str = str(tool_input)
        print(f"   入力: {input_str[:120]}{'...' if len(input_str) > 120 else ''}")

    response = input("許可しますか？ (y/n): ").strip().lower()
    if response == "y":
        return PermissionResultAllow(updated_input=tool_input)
    else:
        return PermissionResultDeny(message="ユーザーがこの操作を拒否しました")


def display_todos(tool_input: dict[str, Any]) -> None:
    todos = tool_input.get("todos", [])
    if not todos:
        return
    print("\n📋 タスクリスト:")
    for todo in todos:
        icon = (
            "✅"
            if todo.get("status") == "completed"
            else "🔄"
            if todo.get("status") == "in_progress"
            else "⬜"
        )
        print(f"  {icon} {todo.get('content', '')}")
    print()


async def main():
    print("=== 旅行プランナー ===\n")

    destination = input("旅行先を入力してください: ").strip()
    task = input("旅行の希望を入力してください: ").strip()
    if not task:
        print("希望が入力されませんでした。終了します。")
        return

    options = ClaudeAgentOptions(
        model="sonnet",
        cwd=str(Path.cwd()),
        permission_mode="plan",
        max_turns=20,
        include_partial_messages=True,
        can_use_tool=handle_tool_request,
    )
    async with ClaudeSDKClient(options=options) as client:
        # ヒアリング・計画
        print("\n🔍 ヒアリング・計画を開始します...\n")
        await client.query(
            f"以下の旅行について、希望をヒアリングして旅行プランを立ててください。\n"
            f"不明点があれば AskUserQuestion で質問してください。\n\n"
            f"旅行先: {destination}\n希望: {task}"
        )
        plan = None
        async for msg in client.receive_response():
            if isinstance(msg, StreamEvent):
                event = msg.event
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        print(delta["text"], end="", flush=True)
            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock) and block.name == "TodoWrite":
                        display_todos(block.input)
            elif isinstance(msg, ResultMessage):
                print(f"\n\n📊 ヒアリング完了 (コスト: ${msg.total_cost_usd or 0:.4f})")
                plan = msg.result

        if not plan:
            print("\n⚠️  プランの取得に失敗しました。終了します。")
            return

        print("\n" + "=" * 50)
        print("📝 旅行プラン:\n")
        print(plan[:500] + ("..." if len(plan) > 500 else ""))
        print("=" * 50)

        # y: はい / n: いいえ / その他はフィードバック
        while True:
            approval = input(
                "\nこのプランで進めますか？ (y: はい / n: いいえ / その他: フィードバック): "
            ).strip()
            if approval.lower() in ("n", "no"):
                print("プランニングをキャンセルしました。")
                return
            if approval.lower() in ("y", "yes"):
                break
            # フィードバックを Claude に返してプランを修正させる
            print("\n🔄 フィードバックを反映してプランを修正します...\n")
            await client.query(
                f"ユーザーからフィードバックがありました。プランを修正してください。\n\n"
                f"フィードバック: {approval}"
            )
            async for msg in client.receive_response():
                if isinstance(msg, StreamEvent):
                    event = msg.event
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            print(delta["text"], end="", flush=True)
                elif isinstance(msg, ResultMessage):
                    print(
                        f"\n\n📊 プラン修正完了 (コスト: ${msg.total_cost_usd or 0:.4f})"
                    )
                    plan = msg.result
            if plan:
                print("\n" + "=" * 50)
                print("📝 修正後のプラン:\n")
                print(plan[:500] + ("..." if len(plan) > 500 else ""))
                print("=" * 50)

        # 詳細な旅程作成 (権限を切り替え)
        print("\n🔨 詳細な旅程を作成します...\n")
        await client.set_permission_mode("acceptEdits")
        await client.query(
            "プランに基づいて詳細な旅程を作成してください。\n"
            "TodoWrite でタスクの進捗を管理してください。"
        )
        async for msg in client.receive_response():
            if isinstance(msg, StreamEvent):
                event = msg.event
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        print(delta["text"], end="", flush=True)
            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock) and block.name == "TodoWrite":
                        display_todos(block.input)
            elif isinstance(msg, ResultMessage):
                print(f"\n\n✅ 旅程作成完了 (コスト: ${msg.total_cost_usd or 0:.4f})")

    print("\n🎉 すべて完了しました！")


if __name__ == "__main__":
    asyncio.run(main())
