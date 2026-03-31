# Claude Agent SDK でつくる! 対話型AIエージェント開発

Zenn Book「Claude Agent SDK でつくる! 対話型AIエージェント開発」のサンプルコードです。

## セットアップ

```sh
# Python 依存パッケージ
uv sync

# .env を作成して API キーを設定
cp .env.template .env
# ANTHROPIC_API_KEY を設定 (必須)
# SERPAPI_API_KEY を設定 (3章・5章で使用)
```

## 各章のスクリプト

| ファイル | 内容 |
|---------|------|
| `scripts/chapter_01_hello_agent.py` | SDK の基本: query(), ClaudeSDKClient |
| `scripts/chapter_02_design_and_implement.py` | 対話型旅行プランナー: ヒアリング → プラン作成 |
| `scripts/chapter_03_serpapi_flights.py` | MCP サーバー連携: SerpApi でフライト検索 |
| `scripts/chapter_04_advanced_features.py` | 応用機能: Hooks, カスタムツール, 構造化出力など |
| `scripts/chapter_05_chat_app/` | Web UI: FastAPI + React チャットアプリ |

## 実行方法

```sh
# 1章
uv run python scripts/chapter_01_hello_agent.py

# 2章
uv run python scripts/chapter_02_design_and_implement.py

# 3章
uv run python scripts/chapter_03_serpapi_flights.py

# 4章 (セクション名を指定)
uv run python scripts/chapter_04_advanced_features.py hooks
uv run python scripts/chapter_04_advanced_features.py custom-tools
uv run python scripts/chapter_04_advanced_features.py structured-output
# ... 他: interrupt, subagents, cost, checkpoint, skills

# 5章 (Web UI)
cd scripts/chapter_05_chat_app/client && npm install && npm run build && cd -
uv run uvicorn scripts.chapter_05_chat_app.server:app --host 0.0.0.0 --port 3001
# ブラウザで http://localhost:3001 を開く
```
