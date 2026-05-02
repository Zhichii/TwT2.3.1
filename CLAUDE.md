# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the Web UI (Flask, port 5004)
python3 server.py

# Run the CLI (deprecated; Web UI is primary)
python3 app.py
```

No test framework is configured. There are no linting or formatting commands.

## Project Overview

TwT2.3.1 is a chat application with a Flask web frontend and optional CLI mode. It supports multiple LLM providers via OpenAI-compatible and Anthropic APIs, with streaming responses, file attachments, thinking/reasoning display, branching conversations, and i18n (zh/en/ja).

## Architecture

### Data Flow (Web UI)

```
User types message (or sends files)
  → server.py POST /api/chat/send
    → app.py Chats.stream_message()
      → providers.py Provider subclass (OpenAI/Anthropic SDK)
        → SSE stream of {"type": "reason"|"content"|"done"|"error"} events
```

### Key Files

- **`app.py`** — Core application logic. Classes:
  - `Config` — JSON file-backed config manager (atomic save via .tmp + replace)
  - `Model` — Single model config: name, id, capabilities, thinking stages, temperature, max_tokens
  - `Provider` — Wraps API client + list of models. Type string maps to provider class via `PROVIDER_CLASS_MAP`
  - `Providers` — Collection of providers, tracks current selection indices
  - `Chat` — Single conversation: title, uuid, MsgTree, provider/model selection, thinking stage
  - `Chats` — Manages all chats (load/save/find by uuid), handles streaming message generation
  - `App` — Top-level orchestrator, owns Config/Providers/Chats, provides model recognition/templates

- **`providers.py`** — API provider implementations. Subclass hierarchy:
  - `OpenAIProvider` — base, `get_thinking_stages()` returns `[]`, `get_thinking_args()` returns `{}`
  - `DeepSeekProvider(OpenAIProvider)` — stages: ["none", "high", "max"], sends `thinking.type` + `reasoning_effort`
  - `MoonshotProvider(OpenAIProvider)` — stages: ["none", "enabled"], sends `thinking.type`
  - `AliyunProvider(OpenAIProvider)` — stages: ["none", "enabled"], sends `enable_thinking` + `thinking_budget`
  - `AnthropicProvider` — stages: ["none", "enabled"], uses Anthropic SDK `thinking` key, default max_tokens=64000

  All providers share `__call__(self, model, msg_tree, max_tokens, stream, thinking_stage, system_prompt, **kwargs)` signature and yield `(type, text)` tuples where type is `"reason"` or `"content"`.

- **`msgs.py`** — Message model and branching tree:
  - `MsgBase` — base with role/content
  - `UserMsg` — adds `files: list[dict]` (each: {name, type, data})
  - `AssistantMsg` — adds `interrupted` flag
  - `ReasonAssistantMsg` — adds `reason` string for thinking/reasoning content
  - `MsgTree` — Linked list tree structure with `MsgWrapper` nodes; each node has parent/children/child for branching. Root is always a system MsgBase at index 0.

- **`server.py`** — Flask web server:
  - Routes: `/` (chat UI), `/chat/<uuid>`, `/settings`
  - All API routes under `/api/`: state, chat CRUD, send (SSE), provider/model management, thinking stage, system prompt
  - SSE format: `data: {"type": "...", "content": "...", "chat_uuid": "..."}\n\n`
  - Handles `GeneratorExit` for client disconnection

- **`tools.py`** — Utility functions: `safe_get()` (typed dict access with error logging), `merge()` (deep merge with type-aware handling)

- **`log.py`** — Rich-based console logging: `error()`, `whisper()`, `hint()`

- **`translations.py`** — i18n dictionary for CLI mode only (`app.py`). Does NOT affect the Web UI frontend. Keys use dot notation (e.g., `"error.config.load"`).

- **`data/template.json`** — Model capability templates applied when adding models. Each template has: id, name, support_vision, support_tools, default_max_tokens, default_temperature, thinking_stages.

- **`data/recognize.json`** — Auto-recognize models from `/v1/models` API and map to templates. Falls back to regex patterns.

- **`templates/index.html`** — Single-page frontend (85KB). Communicates with `/api/*` endpoints. Refs served by Flask. **Frontend i18n is defined here** in the JS `i18n` object, NOT in `translations.py`.

- **`config.json`** (gitignored) — Runtime config: providers, provider_index, provider_model, thinking_stage, chats, system_prompt.

### Thinking / Reasoning Architecture

Thinking stages are defined per-provider-type (not per-model). The `Model` class stores `thinking_stages: list[str]` and `thinking_stage: int` (index). Two derived properties:
- `support_thinking` — True if any stages exist
- `support_thinking_control` — True if more than one stage (user can toggle)

`Model.generate()` returns `(id, max_tokens, data, stage_label)` where `stage_label` is passed as `thinking_stage` to the provider's `__call__`.

### File Attachment Support

`UserMsg` has optional `files: list[dict]`. Each file: `{name, type, data}` (base64 for images, raw text for text files). Providers format files into messages:
- Text files → `"[file name]: ...\n[file content begin]\n...\n[file content end]"`
- Images → OpenAI: `{type: "image_url", image_url: {url: "data:mime;base64,..."}}`, Anthropic: `{type: "image", source: {type: "base64", media_type: "...", data: "..."}}`

### Frontend (templates/index.html)

Single HTML file Vanilla JS frontend that communicates with Flask REST API. No build step needed.

### Config Persistence

All state is in `config.json` (gitignored). `Config` class loads on init, saves atomically on every mutation (`os.replace` with `.tmp`). Chat data, provider config, model selections, and system prompt are all stored here.

## Notes

- This project is simple. Do not launch an Agent tool for most tasks — prefer direct file reads/writes/edits.
- Frontend UI translations go in `templates/index.html` (JS `i18n` object). `translations.py` only affects the CLI mode (`app.py`), NOT the Web UI.
