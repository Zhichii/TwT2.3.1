import json, openai, anthropic
import msgs, log
from tools import merge
from typing import Any
from datetime import datetime

def resolve_template(template: str, model_id: str, model_name: str) -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return template.replace("{{model_id}}", model_id).replace("{{model_name}}", model_name).replace("{{date}}", date_str)

class OpenAIProvider:
    def __init__(self, base_url : str, api_key : str):
        self.client = openai.OpenAI(base_url = base_url, api_key = api_key)
    def _to_format(self, msg_tree : msgs.MsgTree, system_prompt: str = "", model_name: str = "", model_id: str = ""):
        cur = 0
        messages = []
        last_msg_id = msg_tree.get_last_msg_id()
        while True:
            msg = msg_tree.msg_list[cur]
            if (msg.type == "MsgBase"):
                if msg.msg.role in ["user", "system", "assistant", "tool"]:
                    if msg.msg.role == "system" and cur == 0 and system_prompt:
                        messages.append({"role": "system", "content": resolve_template(system_prompt, model_id, model_name)})
                    else:
                        messages.append({"role": msg.msg.role, "content": msg.msg.content})
            if (msg.type == "UserMsg"):
                files = getattr(msg.msg, 'files', []) or []
                if not files:
                    messages.append({"role": "user", "content": msg.msg.content})
                else:
                    parts = []
                    text_parts = []
                    for f in files:
                        if f["type"].startswith("text/") or f["type"] in ("application/json", "image/svg+xml"):
                            text_parts.append(f"[file name]: {f['name']}\n[file content begin]\n{f['data']}\n[file content end]")
                    combined_parts = []
                    if text_parts or msg.msg.content:
                        combined = "\n\n".join(text_parts)
                        if msg.msg.content:
                            combined += "\n\n" + msg.msg.content
                        combined_parts.append({"type": "text", "text": combined})
                    for f in files:
                        if f["type"].startswith("image/") and f["type"] != "image/svg+xml":
                            combined_parts.append({"type": "image_url", "image_url": {"url": f"data:{f['type']};base64,{f['data']}"}})
                    messages.append({"role": "user", "content": combined_parts})
            if (msg.type == "AssistantMsg"):
                # 因为prefix是DeepSeek特有的，partial是Moonshot Kimi特有的
                if False and msg.msg.interrupted and cur == last_msg_id:
                    messages.append({"role": "assistant", "content": msg.msg.content, "prefix": True})
                else:
                    messages.append({"role": "assistant", "content": msg.msg.content})
            if (msg.type == "ReasonAssistantMsg"):
                # 因为prefix是DeepSeek特有的，partial是Moonshot Kimi特有的
                if False and msg.msg.interrupted and cur == last_msg_id:
                    messages.append({"role": "assistant", "content": msg.msg.content, "reasoning_content": msg.msg.reason, "prefix": True})
                else:
                    messages.append({"role": "assistant", "content": msg.msg.content, "reasoning_content": msg.msg.reason})
            if (msg.type == "ToolCallMsg"):
                entry = {"role": "assistant", "content": msg.msg.content if msg.msg.content else None}
                if hasattr(msg.msg, 'reason') and msg.msg.reason:
                    entry["reasoning_content"] = msg.msg.reason
                if hasattr(msg.msg, 'tool_calls') and msg.msg.tool_calls:
                    entry["tool_calls"] = []
                    for tc in msg.msg.tool_calls:
                        entry["tool_calls"].append({
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": tc.get("function", {}).get("arguments", "")
                            }
                        })
                messages.append(entry)
            if (msg.type == "ToolResultMsg"):
                messages.append({
                    "role": "tool",
                    "tool_call_id": msg.msg.tool_call_id,
                    "content": msg.msg.content
                })
            if msg_tree.msg_list[cur].child is not None: cur = msg_tree.msg_list[cur].children[msg_tree.msg_list[cur].child]
            else: break
        return messages
    def get_thinking_stages(self) -> list[str]:
        return []
    def get_thinking_args(self, stage: str, max_tokens: int) -> dict:
        return {}
    def __call__(self, model : str, msg_tree : msgs.MsgTree, max_tokens : int = 4096, stream : bool = True, thinking_stage : str | None = None, system_prompt : str | None = None, tools : list | None = None, **kwargs):
        model_name = kwargs.pop("model_name", "")
        messages = self._to_format(msg_tree, system_prompt=system_prompt or "", model_name=model_name, model_id=model)
        extra_body = dict(kwargs)
        if thinking_stage is not None:
            merge(extra_body, self.get_thinking_args(thinking_stage, max_tokens))
        create_kwargs = dict(model=model, messages=messages, stream=stream, max_tokens=max_tokens, extra_body=extra_body)
        if tools:
            create_kwargs["tools"] = tools
        tool_calls_acc = {}  # index -> {id, type, function: {name, arguments}}
        for chunk in self.client.chat.completions.create(**create_kwargs):
            if hasattr(chunk, "choices") and isinstance(chunk.choices, list):
                if len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                        yield ("reason", delta.reasoning_content)
                    if hasattr(delta, "reasoning") and delta.reasoning:
                        yield ("reason", delta.reasoning)
                    if delta.content:
                        yield ("content", delta.content)
                    # Accumulate tool calls
                    if hasattr(delta, "tool_calls") and delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {
                                    "id": tc.id or "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""}
                                }
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_acc[idx]["function"]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_acc[idx]["function"]["arguments"] += tc.function.arguments
        # If tool calls were accumulated, yield them
        if tool_calls_acc:
            sorted_indices = sorted(tool_calls_acc.keys())
            tool_calls_list = [tool_calls_acc[i] for i in sorted_indices]
            yield ("tool_calls", tool_calls_list)

class DeepSeekProvider(OpenAIProvider):
    def get_thinking_stages(self) -> list[str]:
        return ["none", "high", "max"]
    def get_thinking_args(self, stage: str, max_tokens: int) -> dict:
        if stage == "none":
            return {"thinking": {"type": "disabled"}}
        elif stage == "high":
            return {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}
        elif stage == "max":
            return {"thinking": {"type": "enabled"}, "reasoning_effort": "max"}
        return {}

class MoonshotProvider(OpenAIProvider):
    def get_thinking_stages(self) -> list[str]:
        return ["none", "enabled"]
    def get_thinking_args(self, stage: str, max_tokens: int) -> dict:
        if stage == "none":
            return {"thinking": {"type": "disabled"}}
        elif stage == "enabled":
            return {"thinking": {"type": "enabled"}}
        return {}

class AliyunProvider(OpenAIProvider):
    def get_thinking_stages(self) -> list[str]:
        return ["none", "enabled"]
    def get_thinking_args(self, stage: str, max_tokens: int) -> dict:
        if stage == "none":
            return {"enable_thinking": False}
        elif stage == "enabled":
            return {"enable_thinking": True, "thinking_budget": max_tokens}
        return {}

class AnthropicProvider:
    def __init__(self, base_url : str, api_key : str):
        self.client = anthropic.Anthropic(base_url = base_url, api_key = api_key)
    def get_thinking_stages(self) -> list[str]:
        return ["none", "enabled"]
    def _to_format(self, msg_tree : msgs.MsgTree, system_prompt: str = "", model_name: str = "", model_id: str = ""):
        cur = 0
        system = []
        messages = []
        while True:
            msg = msg_tree.msg_list[cur]
            if (msg.type == "MsgBase"):
                if msg.msg.role in ["user", "assistant", "tool"]:
                    messages.append({"role": msg.msg.role, "content": msg.msg.content})
                if msg.msg.role == "system":
                    if cur == 0 and system_prompt:
                        system.append(resolve_template(system_prompt, model_id, model_name))
                    else:
                        system.append(msg.msg.content)
            if (msg.type == "UserMsg"):
                files = getattr(msg.msg, 'files', []) or []
                if not files:
                    messages.append({"role": "user", "content": msg.msg.content})
                else:
                    parts = []
                    text_parts = []
                    for f in files:
                        if f["type"].startswith("text/") or f["type"] in ("application/json", "image/svg+xml"):
                            text_parts.append(f"[file name]: {f['name']}\n[file content begin]\n{f['data']}\n[file content end]")
                    combined_parts = []
                    if text_parts or msg.msg.content:
                        combined = "\n\n".join(text_parts)
                        if msg.msg.content:
                            combined += "\n\n" + msg.msg.content
                        combined_parts.append({"type": "text", "text": combined})
                    for f in files:
                        if f["type"].startswith("image/") and f["type"] != "image/svg+xml":
                            combined_parts.append({"type": "image", "source": {"type": "base64", "media_type": f["type"], "data": f["data"]}})
                    messages.append({"role": "user", "content": combined_parts})
            if (msg.type == "AssistantMsg"):
                messages.append({"role": "assistant", "content": msg.msg.content})
            if (msg.type == "ReasonAssistantMsg"):
                if isinstance(msg.msg, msgs.ReasonAssistantMsg): # 不然IDE报错
                    messages.append({"role": "assistant", "content": msg.msg.content, "reasoning_content": msg.msg.reason})
                else:
                    log.error("the tag and the type are not the same")
            if (msg.type == "ToolCallMsg"):
                content_blocks = []
                reason = getattr(msg.msg, 'reason', '')
                if reason:
                    content_blocks.append({"type": "thinking", "thinking": reason})
                content_text = msg.msg.content
                if content_text:
                    content_blocks.append({"type": "text", "text": content_text})
                for tc in getattr(msg.msg, 'tool_calls', []):
                    try:
                        input_data = json.loads(tc.get("function", {}).get("arguments", "{}"))
                    except json.JSONDecodeError:
                        input_data = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", ""),
                        "input": input_data
                    })
                entry = {"role": "assistant", "content": content_blocks} if content_blocks else {"role": "assistant", "content": msg.msg.content}
                messages.append(entry)
            if (msg.type == "ToolResultMsg"):
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.msg.tool_call_id,
                        "content": msg.msg.content
                    }]
                })
            if msg_tree.msg_list[cur].child is not None: cur = msg_tree.msg_list[cur].children[msg_tree.msg_list[cur].child]
            else: break
        return (messages, "\n".join(system), )
    def __call__(self, model : str, msg_tree : msgs.MsgTree, max_tokens : int = 64000, stream : bool = True, thinking_stage : str | None = None, system_prompt : str | None = None, **kwargs):
        model_name = kwargs.pop("model_name", "")
        messages, system = self._to_format(msg_tree, system_prompt=system_prompt or "", model_name=model_name, model_id=model)
        create_kwargs = dict(kwargs)
        if max_tokens is None:
            max_tokens = 64000
        if thinking_stage is not None and thinking_stage != "none":
            budget = max(max_tokens // 2, 1024)
            create_kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            max_tokens = max(max_tokens, budget)
        for chunk in self.client.messages.create(max_tokens=max_tokens, messages=messages, system=system, model=model, stream=stream, **create_kwargs):
            if chunk.type == "content_block_delta":
                if chunk.delta.type == "text_delta":
                    text = chunk.delta.text
                    yield ("content", text)
            if chunk.type == "content_block_start" and chunk.content_block.type == "thinking":
                yield ("reason", chunk.content_block.thinking or "")
            if chunk.type == "content_block_delta" and chunk.delta.type == "thinking_delta":
                yield ("reason", chunk.delta.thinking or "")
