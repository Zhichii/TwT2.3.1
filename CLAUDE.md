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

TwT2.3.1 is a chat application with a Flask web frontend and optional CLI mode. It supports multiple LLM providers via OpenAI-compatible and Anthropic APIs, with streaming responses, file attachments, thinking/reasoning display, branching conversations, tool calling, model recognition, and i18n (zh/en/ja).

## Architecture

### Data Flow (Web UI)

```
User types message (or sends files)
  → server.py POST /api/chat/send
    → app.py Chats.stream_message()
      → providers.py Provider subclass (OpenAI/Anthropic SDK)
        → SSE stream of {"type": "reason"|"content"|"done"|"error"|"usage"|"tool_calls"|"tool_result"|"reason_start"|"reason_end"} events
      ↓
    (tool calling loop, up to 10 rounds):
      → Execute tool via App._execute_tool()
      → Append ToolResultMsg
      → Re-call provider with tool results
```

### Key Files

- **`app.py`** — Core application logic. Classes:
  - `Config` — JSON file-backed config manager (atomic save via .tmp + replace)
  - `Model` — Single model config: name, id, capabilities, thinking stages, temperature, max_tokens. `Model.load()` handles backward compat for 3 thinking formats: `thinking_stages: list[str]` (new), `thinking: list[dict]` (old), `support_thinking` + `think_on`/`think_off` (legacy).
  - `Provider` — Wraps API client + list of models. Type string maps to provider class via `PROVIDER_CLASS_MAP`
  - `Providers` — Collection of providers, tracks current selection indices
  - `Chat` — Single conversation: title, uuid, MsgTree, provider/model selection, thinking stage
  - `Chats` — Manages all chats (load/save/find by uuid), handles streaming message generation. `stream_message()` has a tool calling loop (up to 10 rounds).
  - `App` — Top-level orchestrator, owns Config/Providers/Chats. Provides: model recognition (`get_recognized_models()`), model CRUD (`add/delete/edit_model_on_provider`), thinking presets (`get_thinking_presets()`), system prompt management, tools config (`get_tools_config`/`set_tool_enabled`), tool execution (`_get_enabled_tools`/`_execute_tool`), message editing, AI rename, chat state queries.

- **`providers.py`** — API provider implementations. Subclass hierarchy:
  - `OpenAIProvider` — base, `get_thinking_stages()` returns `[]`, `get_thinking_args()` returns `{}`.
    `__call__` includes `tools` param, accumulates `tool_calls` from streaming chunks via `tool_calls_acc`, yields `("tool_calls", list)` and `("usage", dict)` events. Sends `stream_options={"include_usage": True}`.
  - `DeepSeekProvider(OpenAIProvider)` — stages: ["none", "high", "max"], sends `thinking.type` + `reasoning_effort`
  - `MoonshotProvider(OpenAIProvider)` — stages: ["none", "enabled"], sends `thinking.type`
  - `AliyunProvider(OpenAIProvider)` — stages: ["none", "enabled"], sends `enable_thinking` + `thinking_budget`
  - `AnthropicProvider` — stages: ["none", "enabled"], uses Anthropic SDK `thinking` key, default max_tokens=64000. Formats tool calls as `tool_use` content blocks.

  `resolve_template(template, model_id, model_name)` replaces `{{model_id}}`, `{{model_name}}`, `{{date}}` in system prompts.

  All providers share `__call__(self, model, msg_tree, max_tokens, stream, thinking_stage, system_prompt, **kwargs)` signature and yield `(type, text)` tuples where type is `"reason"` or `"content"`. OpenAI subclasses additionally yield `"tool_calls"` and `"usage"`.

- **`msgs.py`** — Message model and branching tree:
  - `MsgBase` — base with role/content
  - `UserMsg` — adds `files: list[dict]` (each: {name, type, data})
  - `AssistantMsg` — unified assistant message: adds `interrupted`, `usage: dict`, `reason: str`, `tool_calls: list[dict]`
  - `ReasonAssistantMsg = AssistantMsg` — backward-compat alias for loading old configs
  - `ToolCallMsg = AssistantMsg` — backward-compat alias for loading old configs
  - `ToolResultMsg` — tool response with `tool_call_id` and content, role="tool"
  - `MsgTree` — Linked list tree structure with `MsgWrapper` nodes; each node has parent/children/child for branching. Root is always a system MsgBase at index 0. `append_after(parent_id, msg)` creates a new branch for message editing.

- **`server.py`** — Flask web server:
  - Routes: `/` (chat UI), `/chat/<uuid>`, `/settings`
  - All API routes under `/api/`:
    - `GET /api/state` — full app state (providers, chats, messages)
    - `POST /api/chat/send` — SSE stream (message + files + tools)
    - `POST /api/chat/new`, `POST /api/chat/switch`, `POST /api/chat/delete`
    - `PATCH /api/chat/<uuid>/rename`, `POST /api/chat/<uuid>/rename-ai`
    - `POST /api/chat/message/edit` — branch-edit a user message
    - `POST /api/model/select` — provider/model selection
    - `PATCH /api/thinking/stage` — thinking stage per-chat or global
    - `GET /api/thinking/presets` — thinking presets from `data/thinking.json`
    - `POST /api/provider/add`, `DELETE /api/provider/<int:index>`
    - `GET /api/provider/templates` — model capability templates
    - `GET /api/provider/<int:index>/models/recognize` — auto-recognize models
    - `POST /api/provider/<int:index>/models/add`
    - `DELETE/PATCH /api/provider/<int:pindex>/models/<int:midx>` — model CRUD
    - `GET/PATCH /api/system-prompt`
    - `GET/PATCH /api/tools` — tools config
  - SSE format: `data: {"type": "...", "content": "...", "chat_uuid": "..."}\n\n`
  - Handles `GeneratorExit` for client disconnection
  - Adds CORS headers on all responses (`Access-Control-Allow-Origin: *`)

- **`tools.py`** — Utility functions: `safe_get()` (typed dict access with error logging), `merge()` (deep merge with type-aware handling)

- **`log.py`** — Rich-based console logging: `error()`, `whisper()`, `hint()`

- **`translations.py`** — i18n dictionary for CLI mode only (`app.py`). Does NOT affect the Web UI frontend. Keys use dot notation (e.g., `"error.config.load"`).

- **`data/template.json`** — Model capability templates applied when adding models. Each template has: id, name, support_vision, support_tools, default_max_tokens, default_temperature, thinking_stages.

- **`data/recognize.json`** — Auto-recognize models from `/v1/models` API and map to templates. Maps model IDs → `{name, template}`. Has `patterns: [{pattern, template, name}]` for regex fallback.

- **`data/thinking.json`** — Thinking preset configurations for the frontend settings UI. Each preset has: id, name (i18n object), stages array. Presets include: "Dual Mode" (`["none", "enabled"]`), "DeepSeek V4 Style" (`["none", "high", "max"]`), "GPT Style" (`["minimal", "low", "medium", "high", "xhigh"]`).

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

All state is in `config.json` (gitignored). `Config` class loads on init, saves atomically on every mutation (`os.replace` with `.tmp`). Chat data, provider config, model selections, system prompt, and tools config are all stored here.

### Tool Calling

Tools are defined in `config.json` under the `"tools"` key (e.g., `{"get_current_time": {"enabled": true}}`). The tool calling flow:
1. `App._get_enabled_tools()` builds OpenAI-compatible tools list from config
2. `Chats.stream_message()` passes tools to the provider on the first and each re-call
3. Provider streams chunks, accumulates `tool_calls` across delta chunks, yields `("tool_calls", list)` at the end
4. `stream_message()` saves the AssistantMsg with tool_calls, then calls `App._execute_tool()` for each
5. Tool results are appended as `ToolResultMsg` and the provider is re-called (up to 10 rounds)
6. Each tool response round also streams `("tool_result", ...)` events to the frontend

Currently only one built-in tool: `get_current_time` (returns the current datetime string).

### Model Recognition & CRUD

`App.get_recognized_models(provider_index)` calls the provider's `/v1/models` API endpoint, then matches returned model IDs against `data/recognize.json`:
1. Exact match in `recognize.json["models"]` dictionary
2. Regex fallback via `recognize.json["patterns"]` array
3. Each matched model gets a template from `data/template.json` (capabilities: vision, tools, thinking stages, max_tokens, temperature)

`App.add_model_to_provider()` / `App.delete_model_from_provider()` / `App.edit_model_on_provider()` handle model CRUD, applying templates and individual field overrides.

### System Prompt Templates

System prompts support template variables resolved by `providers.resolve_template()`:
- `{{model_id}}` — replaced with the model ID string
- `{{model_name}}` — replaced with the model display name
- `{{date}}` — replaced with current date in `YYYY-MM-DD` format

### SSE Event Types

`Chats.stream_message()` yields dicts with `type` field:
- `"reason"` / `"reason_start"` / `"reason_end"` — thinking/reasoning content
- `"content"` — response text content
- `"usage"` — token usage stats `{prompt_tokens, completion_tokens, total_tokens, completion_tokens_details: {reasoning_tokens}}`
- `"tool_calls"` — `{tool_calls: [{id, type, function: {name, arguments}}]}`
- `"tool_result"` — `{tool_call_id, tool_name, content}`
- `"error"` — error message string
- `"done"` — signals stream end with `{reason, content, chat_uuid}`

### Frontend Message Rendering (Card Interleaving)

A single assistant response can interleave thinking blocks, content blocks, and tool call blocks in any order. The frontend renders these as independent DOM elements inside `.msg.assistant`:

**Streaming** (`handleStreamEvent`): Each SSE event appends at the end of the assistant div, preserving the natural order. `reason_start` creates a new `.tc-card.tc-thinking`, `content` creates/reuses a `.bubble`, `tool_calls` creates `.tc-card.tc-tool` cards.

**Loaded messages** (`updateMessages`): Since `AssistantMsg` stores a single concatenated `reason` string and `content` string, interleaving is partially preserved across multiple saved messages:
- First API round (reason → content → tool_calls): Rendered as `[thinking card, bubble, tool cards]` in order.
- Second API round after tool execution (reason → content): Appended to the same div as `[thinking card, bubble]` after the tool cards, keeping the chronological sequence.

Key rendering rules:
- Thinking cards (`.tc-card.tc-thinking`) are always inserted BEFORE their paired content bubble within the same message.
- Across messages (tool round → next round), cards and bubbles are appended in arrival order.
- `hasToolContent` check: if the previous assistant div already has tc-cards (from tool calls), subsequent messages append to the same div rather than creating a new one.

## Notes

- This project is simple. Do not launch an Agent tool for most tasks — prefer direct file reads/writes/edits.
- Frontend UI translations go in `templates/index.html` (JS `i18n` object). `translations.py` only affects the CLI mode (`app.py`), NOT the Web UI.
- Tool-related UI translations (tool names, descriptions, settings) are in `translations.py` and used by the frontend via the `/api/state` endpoint (embedded in the providers/state response for the settings UI).
