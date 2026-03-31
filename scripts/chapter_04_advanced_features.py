"""Chapter 04: SDK の応用機能を試そう

各セクションは独立しており、個別に実行できます。
  uv run python scripts/chapter_04_advanced_features.py <section>
  sections: hooks, interrupt, custom-tools, subagents,
            structured-output, cost, checkpoint, skills
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    query,
    tool,
)
from claude_agent_sdk.types import (
    HookMatcher,
)

load_dotenv()


def safe_input(prompt: str = "") -> str:
    """EOF でも落ちない input"""
    try:
        return input(prompt)
    except EOFError:
        return ""


# =============================================
# Section 1: Hooks — ツール実行に割り込む
# =============================================
async def section_hooks():
    print("=== Hooks: .env への書き込みをブロック ===\n")

    async def protect_env_files(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: Any,
    ) -> dict[str, Any]:
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if ".env" in file_path:
            print(f"\n🚫 [Hook] .env への書き込みをブロック: {file_path}")
            return {
                "hookSpecificOutput": {
                    "hookEventName": input_data.get("hook_event_name"),
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        ".env ファイルへの書き込みは禁止されています"
                    ),
                }
            }
        return {}

    prompt = (
        ".env ファイルに TEST=1 と書き込んでください。"
        "書き込めなかったらその旨を報告してください。"
    )
    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            model="sonnet",
            cwd=str(Path.cwd()),
            permission_mode="acceptEdits",
            disallowed_tools=["Bash"],
            max_turns=3,
            hooks={
                "PreToolUse": [
                    HookMatcher(matcher="Write|Edit", hooks=[protect_env_files])
                ],
            },
        ),
    ):
        if isinstance(msg, ResultMessage):
            print(f"\n結果: {msg.result}")


# =============================================
# Section 2: Interrupt — 実行を中断する
# =============================================
async def section_interrupt():
    print("=== Interrupt: graceful な中断 ===\n")

    async with ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model="sonnet",
            permission_mode="plan",
            max_turns=20,
        )
    ) as client:
        await client.query(
            "1から100までの素数をすべて列挙してから、それぞれについて豆知識を述べてください。"
        )

        # 3秒後に interrupt
        async def interrupt_after_delay():
            await asyncio.sleep(3)
            print("\n⏸️  3秒経過、interrupt を送信...")
            await client.interrupt()

        interrupt_task = asyncio.create_task(interrupt_after_delay())

        # メッセージをドレイン（interrupt 後も必須）
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(block.text[:100], end="")
            elif isinstance(msg, ResultMessage):
                print(f"\n\n中断完了: subtype={msg.subtype}")
                print(f"ターン数: {msg.num_turns}")

        interrupt_task.cancel()

        # interrupt 後も新しいクエリを送信可能
        await client.query("代わりに、10以下の素数だけ教えてください。短く。")
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                print(f"\n新しい結果: {msg.result}")


# =============================================
# Section 3: カスタムツール
# =============================================
async def section_custom_tools():
    print("=== カスタムツール: 現在時刻を返すツール ===\n")

    @tool("current_time", "現在の日時をフォーマットして返す", {"format": str})
    async def current_time(args: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now()
        match args.get("format", "iso"):
            case "iso":
                text = now.isoformat()
            case "japanese":
                text = now.strftime("%Y年%m月%d日 %H:%M:%S")
            case "unix":
                text = str(int(now.timestamp()))
            case _:
                text = str(now)
        return {"content": [{"type": "text", "text": text}]}

    server = create_sdk_mcp_server(
        name="time-tools", version="1.0.0", tools=[current_time]
    )

    async with ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model="sonnet",
            mcp_servers={"time-tools": server},
            allowed_tools=["mcp__time-tools__current_time"],
            permission_mode="dontAsk",
            max_turns=3,
        )
    ) as client:
        await client.query(
            "current_time ツールを使って、現在の日時を japanese 形式で教えてください。"
        )
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(f"[assistant] {block.text}")
                    elif isinstance(block, ToolUseBlock):
                        print(f"[tool_use] {block.name}: {block.input}")
            elif isinstance(msg, ResultMessage):
                print(f"\n結果: {msg.result}")


# =============================================
# Section 4: サブエージェント
# =============================================
async def section_subagents():
    print("=== サブエージェント: 目的地調査を委譲 ===\n")

    from claude_agent_sdk import AgentDefinition

    destination_expert = AgentDefinition(
        description="旅行先の専門調査エージェント",
        prompt=(
            "指定された目的地の気候・治安・交通事情・"
            "おすすめスポットを調査し、"
            "簡潔に日本語で報告してください。"
        ),
        tools=["Read", "Glob", "Grep"],
    )
    prompt = (
        "destination-expert サブエージェントを使って、"
        "7月のローマの観光情報を調査してください。"
    )
    options = ClaudeAgentOptions(
        model="sonnet",
        cwd=str(Path.cwd()),
        permission_mode="plan",
        allowed_tools=["Read", "Glob", "Grep", "Agent"],
        max_turns=10,
        agents={"destination-expert": destination_expert},
    )
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, ResultMessage):
            print(f"結果:\n{msg.result}")


# =============================================
# Section 5: 構造化出力
# =============================================
async def section_structured_output():
    print("=== 構造化出力: JSON スキーマで出力を強制 ===\n")

    from pydantic import BaseModel, Field

    class FileInfo(BaseModel):
        path: str = Field(description="ファイルパス")
        description: str = Field(description="ファイルの1行説明")

    class FileReport(BaseModel):
        files: list[FileInfo]
        total_count: int = Field(description="ファイル総数")

    async for msg in query(
        prompt=".py ファイルを検索し、各ファイルの概要を返してください。",
        options=ClaudeAgentOptions(
            model="sonnet",
            cwd=str(Path.cwd()),
            output_format={
                "type": "json_schema",
                "schema": FileReport.model_json_schema(),
            },
            permission_mode="plan",
            max_turns=5,
        ),
    ):
        if isinstance(msg, ResultMessage):
            import json

            if msg.structured_output:
                print(json.dumps(msg.structured_output, indent=2, ensure_ascii=False))
            else:
                print(f"結果: {msg.result}")


# =============================================
# Section 6: コスト管理
# =============================================
async def section_cost():
    print("=== コスト管理: 予算上限と使用量追跡 ===\n")

    async for msg in query(
        prompt="Python の asyncio について3文で説明してください。",
        options=ClaudeAgentOptions(
            model="sonnet",
            max_budget_usd=0.50,
            max_turns=1,
        ),
    ):
        if isinstance(msg, ResultMessage):
            print(f"結果: {msg.result}\n")
            print(f"合計コスト: ${msg.total_cost_usd:.4f}")
            print(f"ターン数: {msg.num_turns}")
            print(f"サブタイプ: {msg.subtype}")
            if msg.usage:
                print(f"使用量: {msg.usage}")


# =============================================
# Section 7: ファイルチェックポイント
# =============================================
async def section_checkpoint():
    print("=== ファイルチェックポイント: 変更の巻き戻し ===\n")
    print("（このセクションは実際にファイルを変更するため、/tmp で実行します）\n")

    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        # テスト用ファイルを作成
        test_file = os.path.join(tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("original content\n")
        print(f"初期内容: {open(test_file).read().strip()}")

        checkpoint_id = None
        session_id = None

        # Step 1: チェックポイント有効でエージェント実行
        options = ClaudeAgentOptions(
            model="sonnet",
            cwd=tmpdir,
            permission_mode="acceptEdits",
            allowed_tools=["Write", "Read"],
            enable_file_checkpointing=True,
            extra_args={"replay-user-messages": None},
            max_turns=3,
        )
        async with ClaudeSDKClient(options=options) as client:
            await client.query(
                "test.txt の内容を 'modified by Claude' に書き換えてください。"
            )
            async for msg in client.receive_response():
                if isinstance(msg, UserMessage) and msg.uuid and not checkpoint_id:
                    checkpoint_id = msg.uuid
                if isinstance(msg, ResultMessage):
                    session_id = msg.session_id
                    print(f"\n変更後の内容: {open(test_file).read().strip()}")

        # Step 2: 巻き戻し
        if checkpoint_id and session_id:
            print(f"\nチェックポイント: {checkpoint_id[:12]}...")
            response = safe_input("巻き戻しますか？ (y/n): ").strip().lower()
            if response == "y":
                resume_options = ClaudeAgentOptions(
                    model="sonnet",
                    enable_file_checkpointing=True,
                    resume=session_id,
                )
                async with ClaudeSDKClient(
                    options=resume_options,
                ) as client:
                    await client.query("")  # 空プロンプトで接続
                    async for msg in client.receive_response():
                        await client.rewind_files(checkpoint_id)
                        break
                print(f"巻き戻し後の内容: {open(test_file).read().strip()}")


# =============================================
# Section 8: スキルとスラッシュコマンド
# =============================================
async def section_skills():
    print("=== スキルとスラッシュコマンド ===\n")

    # /compact の実行例
    print("--- /compact で会話を圧縮 ---")
    async with ClaudeSDKClient(
        options=ClaudeAgentOptions(model="sonnet", max_turns=3)
    ) as client:
        # まず何か会話してから compact
        await client.query("こんにちは。今日の作業を始めましょう。")
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                print(f"応答: {msg.result[:100]}")

        await client.query("/compact")
        async for msg in client.receive_response():
            if isinstance(msg, SystemMessage) and msg.subtype == "compact_boundary":
                print("✅ 会話を圧縮しました")
            elif isinstance(msg, ResultMessage):
                print(f"結果: {msg.result[:100] if msg.result else '(compact 完了)'}")

    print("\n--- スキルの有効化例（コード説明のみ） ---")
    print("""
スキルを有効にするには setting_sources + allowed_tools に "Skill" を含めます:

    ClaudeAgentOptions(
        model="sonnet",
        setting_sources=["user", "project"],  # スキル読み込みに必須
        allowed_tools=["Skill", "Read", "Write"],
    )

注意:
- SKILL.md の allowed-tools は SDK 経由では無視される
- setting_sources を設定しないとスキルは読み込まれない
- @ プレフィックスでファイル参照可能: await client.query("@src/auth.py をレビュー")
""")


# =============================================
# メインルーター
# =============================================
SECTIONS = {
    "hooks": section_hooks,
    "interrupt": section_interrupt,
    "custom-tools": section_custom_tools,
    "subagents": section_subagents,
    "structured-output": section_structured_output,
    "cost": section_cost,
    "checkpoint": section_checkpoint,
    "skills": section_skills,
}


async def main():
    if len(sys.argv) < 2:
        print("使い方: uv run python scripts/chapter_04_advanced_features.py <section>")
        print(f"sections: {', '.join(SECTIONS.keys())}")
        return

    section = sys.argv[1]
    if section not in SECTIONS:
        print(f"不明なセクション: {section}")
        print(f"利用可能: {', '.join(SECTIONS.keys())}")
        return

    await SECTIONS[section]()


if __name__ == "__main__":
    asyncio.run(main())
