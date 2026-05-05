import translations
translations.lang = "en"

import os, json, uuid, re
import datetime
import openai
import log, msgs, providers
from copy import deepcopy
from tools import safe_get, merge
from typing import Literal, Any, Callable
from translations import translate as t
# from my_io import linux_input # deprecated. use readline instead (wait for me to test on Windows)
# 不要问我为什么不遵循规范

# 处理一下，不然会出现莫名其妙的问题。
for name in os.environ.keys():
    if len(name) > 5 and name[-6] == "_" and name[-5:].lower() == "proxy":
        del os.environ[name]

class Config:
    def __init__(self, path: str = "", default: dict = {}):
        self.path = path
        self.default = deepcopy(default)
        self.data = deepcopy(self.default)
        if (os.path.exists(path)):
            self.load()
        self.save() # 格式化
    def load(self):
        try:
            if not self.path: raise ValueError("path is nullstr")
            with open(self.path, "r") as fp:
                self.data = json.load(fp)
        except Exception as e:
            log.error(t("error.config.load").replace("CONFIG", self.path), e)
    def save(self):
        try:
            if not self.path: raise ValueError("path is nullstr")
            with open(self.path+".tmp", "w") as fp:
                json.dump(self.data, fp, ensure_ascii=False, indent=4)
            os.replace(self.path+".tmp",self.path)
        except Exception as e:
            log.error(t("error.config.save").replace("CONFIG", self.path), e)
    def __repr__(self):
        return repr(self.data)
    def has(self, key : str = ""):
        return key in self.data
    def __getitem__(self, key : str = ""): # Returns a shallow copy
        if key in self.data:
            return self.data[key]
        # else: return None
    def __setitem__(self, key: str = "", value = None):
        self.data[key] = deepcopy(value)

class Model:
    name : str
    id : str
    support_vision : bool
    support_tools : bool
    default_thinking : bool
    default_temperature : float | None
    default_max_tokens : int
    thinking_stages : list[str]
    thinking_stage : int
    def __init__(self, name : str, id : str):
        self.name = name
        self.id = id
        self.support_vision = False
        self.support_tools = False
        self.default_thinking = False
        self.default_temperature = None
        self.default_max_tokens = 4096
        self.thinking_stages = []
        self.thinking_stage = 0
    @property
    def support_thinking(self): return len(self.thinking_stages) > 0
    @property
    def support_thinking_control(self): return len(self.thinking_stages) > 1
    def set_thinking_stages(self, stages : list[str], default_stage : int = 0):
        self.thinking_stages = deepcopy(stages)
        self.thinking_stage = default_stage if 0 <= default_stage < len(stages) else 0
        if len(stages) > 0:
            self.default_thinking = stages[default_stage] != "none" if 0 <= default_stage < len(stages) else False
    def mark_support_vision(self): self.support_vision = True
    def mark_support_tools(self): self.support_tools = True
    def set_default_thinking(self, stage : int = 0): self.thinking_stage = stage
    def set_default_temperature(self, temperature : float | None = None): self.default_temperature = temperature
    def set_default_max_tokens(self, max_tokens : int = 4096): self.default_max_tokens = max_tokens
    def generate(self, thinking_stage : int | None = None,
                       temperature : float | None = None,
                       max_tokens : int | None = None):
        data : dict[str, Any] = {}
        stage_label = None
        if len(self.thinking_stages) > 0:
            idx = thinking_stage if thinking_stage is not None else self.thinking_stage
            if 0 <= idx < len(self.thinking_stages):
                stage_label = self.thinking_stages[idx]
        if temperature is not None: data["temperature"] = temperature
        elif self.default_temperature is not None: data["temperature"] = self.default_temperature
        if max_tokens is not None: real_max_tokens = max_tokens
        else: real_max_tokens = self.default_max_tokens
        real_max_tokens = max(real_max_tokens, 0)
        data["model_name"] = self.name
        return (self.id, real_max_tokens, data, stage_label)
    def store(self) -> dict[str, Any]:
        data = {"name": self.name,
                "id": self.id,
                "default_thinking": self.default_thinking,
                "default_temperature": self.default_temperature,
                "default_max_tokens": self.default_max_tokens,
                "support_vision": self.support_vision,
                "support_tools": self.support_tools,
                "thinking_stages": deepcopy(self.thinking_stages),
                "thinking_stage": self.thinking_stage}
        return data
    @staticmethod
    def load(data : dict) -> "Model":
        name = safe_get(data, str, "name", "model", "GPT-4")
        id = safe_get(data, str, "id", "model", "gpt-4")
        a : Model = Model(name, id)
        a.default_thinking = safe_get(data, bool, "default_thinking", "model", False)
        a.default_temperature = safe_get(data, (float, type(None), ), "default_temperature", "model", None)
        a.default_max_tokens = safe_get(data, int, "default_max_tokens", "model", 4096)
        a.support_tools = safe_get(data, bool, "support_tools", "model", False)
        a.support_vision = safe_get(data, bool, "support_vision", "model", False)
        # Load thinking_stages (new format list[str]), with backward compat
        thinking_stages = safe_get(data, list, "thinking_stages", "model", None)
        if thinking_stages is not None:
            a.thinking_stages = deepcopy(thinking_stages)
            a.thinking_stage = safe_get(data, int, "thinking_stage", "model", 0)
        else:
            # Fallback: old thinking (list[dict]) format
            thinking = safe_get(data, list, "thinking", "model", None)
            if thinking is not None:
                a.thinking_stages = [item["stage"] for item in thinking if isinstance(item, dict)]
                a.thinking_stage = safe_get(data, int, "thinking_stage", "model", 0)
            elif safe_get(data, bool, "support_thinking", "model", False):
                # Legacy: convert think_on/think_off
                on = safe_get(data, dict, "think_on", "model", {})
                off = safe_get(data, dict, "think_off", "model", {})
                a.thinking_stages = []
                if off: a.thinking_stages.append("none")
                if on: a.thinking_stages.append("enabled")
                a.thinking_stage = 1 if a.default_thinking else 0
        return a

PROVIDER_CLASS_MAP = {
    "openai": providers.OpenAIProvider,
    "deepseek": providers.DeepSeekProvider,
    "moonshot": providers.MoonshotProvider,
    "aliyun": providers.AliyunProvider,
    "llama-cpp": providers.LlamaCppProvider,
    "anthropic": providers.AnthropicProvider,
}

class Provider:
    name : str
    base_url : str
    api_key : str
    type : str
    models : list[Model]
    def __init__(self, name : str, base_url : str, api_key : str, type : str = "openai"):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.type = type
        client_class = PROVIDER_CLASS_MAP.get(type, providers.OpenAIProvider)
        self.client = client_class(base_url, api_key)
        self.models = []
    @staticmethod
    def load(data : dict):
        name = safe_get(data, str, "name", "provider", "OpenAI")
        base_url = safe_get(data, str, "base_url", "provider", "https://api.openai.com/v1")
        api_key = safe_get(data, str, "api_key", "provider", "sk-?")
        type = safe_get(data, str, "type", "provider", "openai")
        a = Provider(name, base_url, api_key, type)
        models_ = safe_get(data, list, "models", "provider", [])
        models = []
        for model in models_:
            models.append(Model.load(model))
        a.models = models
        return a
    def store(self) -> dict[str, Any]:
        return {"name": self.name,
                "base_url": self.base_url,
                "api_key": self.api_key,
                "type": self.type,
                "models": [model.store() for model in self.models]}
    def __len__(self) -> int: return len(self.models)
    def generate(self, model : int, **kwargs):
        if 0 <= model <= len(self):
            return self.models[model].generate(**kwargs)
        else:
            log.error("model index out of bound")

class Providers:
    cfg : Config
    providers : list[Provider]
    provider_index : int | None
    provider_model : int | None
    def __init__(self, cfg : Config):
        self.cfg = cfg
        self.providers = []
        if cfg.has("providers"):
            providers_ = cfg["providers"]
            if isinstance(providers_, list):
                providers = []
                for provider in providers_:
                    if isinstance(provider, dict):
                        p = Provider.load(provider)
                        self.providers.append(p)
                        providers.append(p.store())
                cfg["providers"] = providers
        else:
            log.error(t("error.config.not_valid").replace("VAR", "providers"))
            cfg["providers"] = []
        if cfg.has("provider_index") and isinstance(cfg["provider_index"], (int, type(None),)):
            self.provider_index = cfg["provider_index"]
        else:
            log.error(t("error.config.not_valid").replace("VAR", "provider_index"))
            self.provider_index = None
        if cfg.has("provider_model") and isinstance(cfg["provider_model"], (int, type(None),)):
            self.provider_model = cfg["provider_model"]
        else:
            log.error(t("error.config.not_valid").replace("VAR", "provider_model"))
            self.provider_model = None
        self.cfg.save()
    def __len__(self) -> int: return len(self.providers)
    def generate(self, provider : int, model : int, **kwargs):
        if 0 <= provider <= len(self):
            return self.providers[provider].generate(model, **kwargs)
        else:
            log.error("that can't be true")
            return None

class Chat:
    title : str
    uuid : str
    msg_tree : msgs.MsgTree
    provider_index : int | None
    provider_model : int | None
    thinking_stage : int | None
    def __init__(self):
        self.title = t("chat.new")
        self.uuid = str(uuid.uuid4())
        self.msg_tree = msgs.MsgTree()
        self.thinking_stage = None
    @staticmethod
    def load(data : dict):
        the_chat = Chat()
        the_chat.title = safe_get(data, str, "title", "chat", t("chat.new"))
        the_chat.uuid = safe_get(data, str, "uuid", "chat", str(uuid.uuid4()))
        msg_tree_json = safe_get(data, dict, "msg_tree", "chat", None)
        if msg_tree_json is None:
            the_chat.msg_tree = msgs.MsgTree()
        else:
            the_chat.msg_tree = msgs.MsgTree.load(msg_tree_json)
        the_chat.provider_index = safe_get(data, (int,type(None),), "provider_index", "chat", None)
        the_chat.provider_model = safe_get(data, (int,type(None),), "provider_model", "chat", None)
        the_chat.thinking_stage = safe_get(data, (int,type(None),), "thinking_stage", "chat", None)
        return the_chat
    def store(self):
        return {"title": self.title,
                "uuid": self.uuid,
                "msg_tree": self.msg_tree.store(),
                "provider_index": self.provider_index,
                "provider_model": self.provider_model,
                "thinking_stage": self.thinking_stage}
    def append(self, msg : msgs.MsgBase):
        self.msg_tree.append(msg)
    def get_last_msg_id(self) -> None | int:
        return self.msg_tree.get_last_msg_id()
    def ends_with_assistant(self):
        return self.msg_tree.ends_with_assistant()
    def complete_last_assistant(self, idx : int, msg : msgs.AssistantMsg):
        self.msg_tree.complete_last_assistant(idx, msg)

class Chats:
    cfg : Config
    providers : Providers
    def __init__(self, cfg : Config, providers : Providers):
        self.cfg = cfg
        self.providers = providers
        if not isinstance(self.cfg["chats"], list):
            log.error(t("error.config.not_valid").replace("VAR", "chats"))
            self.cfg["chats"] = []
        # Clean up legacy config keys
        for k in ("chat_index", "current_chat_uuid"):
            if cfg.has(k):
                del cfg.data[k]
        # Ensure all chats have uuids
        need_save = False
        for i, chat_dict in enumerate(self.cfg["chats"]):
            if isinstance(chat_dict, dict) and not chat_dict.get("uuid"):
                chat_dict["uuid"] = str(uuid.uuid4())
                self.cfg["chats"][i] = chat_dict
                need_save = True
        if need_save:
            self.cfg.save()
    def _find_chat_index(self, uuid_str: str) -> int | None:
        if not uuid_str:
            return None
        for i, c in enumerate(self.cfg["chats"]):
            if isinstance(c, dict) and c.get("uuid") == uuid_str:
                return i
        return None
    def _load_chat(self, uuid_str: str) -> Chat | None:
        """Load a chat from config by uuid. No side effects."""
        idx = self._find_chat_index(uuid_str)
        if idx is None:
            return None
        cd = self.cfg["chats"][idx]
        if isinstance(cd, dict):
            return Chat.load(cd)
        return None
    def _save_chat(self, chat: Chat):
        """Save a chat to config. If not found in list, append it."""
        idx = self._find_chat_index(chat.uuid)
        if idx is not None:
            self.cfg["chats"][idx] = chat.store()
        else:
            self.cfg["chats"].append(chat.store())
        self.cfg.save()
    def user_msg_send(self, msg: str, chat_uuid: str | None = None):
    # 向指定对话发送消息。如果 chat_uuid 为 None 则创建新对话
        chat = self._load_chat(chat_uuid) if chat_uuid else None
        if chat is None: # 创建新的对话
            chat = Chat()
            chat.provider_index = self.providers.provider_index
            chat.provider_model = self.providers.provider_model
            chat.thinking_stage = self.cfg["thinking_stage"]
            chat_uuid = chat.uuid
        if msg:
            chat.append(msgs.UserMsg(msg))
        self._save_chat(chat)
        ends_with_assistant = chat.ends_with_assistant()
        if ends_with_assistant:
            return
        if (chat.provider_index is None) or (chat.provider_model is None):
            log.error(t("error.provider.no"))
            return
        gen = self.providers.generate(chat.provider_index, chat.provider_model, thinking_stage=chat.thinking_stage)
        if gen is None:
            log.error("that can't be true! ")
            return
        system_prompt = self.cfg.data.get("system_prompt", "")
        system_prompt = system_prompt.replace("{{language}}", translations.lang)
        reasons = []
        contents = []
        interrupt = False
        state : Literal["content", "reason"] = "content"
        try:
            for i in self.providers.providers[chat.provider_index].client(gen[0], chat.msg_tree, gen[1], True, thinking_stage=gen[3], system_prompt=system_prompt, **gen[2]):
                if (i[0] != state):
                    if i[0] == "reason": log.console.print("Thinking...", style="bold #808080")
                    else:
                        print()
                        log.console.print("... done thinking", style="bold #808080")
                        print()
                    state = i[0]
                if state == "reason": log.console.print(i[1], style="#808080", end="")
                if state == "content": print(i[1], end="", flush=True)
                import sys
                sys.stdout.flush()
                sys.stdin.flush()
                if i[0] == "reason":
                    reasons.append(i[1])
                if i[0] == "content":
                    contents.append(i[1])
        except KeyboardInterrupt:
            interrupt = True
        except Exception as e:
            log.error("stream error", e)
            interrupt = True
            print(f"\n[Error: {e}]")
        print()
        reason = "".join(reasons)
        content = "".join(contents)
        if False and ends_with_assistant:
            last_msg_id = chat.get_last_msg_id()
            if reason: chat.complete_last_assistant(last_msg_id, msgs.AssistantMsg(content, interrupt, reason=reason))
            else: chat.complete_last_assistant(last_msg_id, msgs.AssistantMsg(content, interrupt))
        else:
            if reason: chat.append(msgs.AssistantMsg(content, interrupt, reason=reason))
            else: chat.append(msgs.AssistantMsg(content, interrupt))
        self._save_chat(chat)
    def stream_message(self, msg: str, chat_uuid: str | None = None, files: list[dict] | None = None, language: str = "en", tools: list | None = None, execute_tool: Callable | None = None):
        """Generator that streams a response, yielding event dicts.
        Supports tool calling loop: if the model calls tools, they are executed
        and the result is sent back to the model for the next round.
        If chat_uuid is None, creates a new chat."""
        files = files or []
        tools = tools or []
        chat = self._load_chat(chat_uuid) if chat_uuid else None
        if chat is None:
            chat = Chat()
            if chat_uuid:
                chat.uuid = chat_uuid
            chat.provider_index = self.providers.provider_index
            chat.provider_model = self.providers.provider_model
            chat.thinking_stage = self.cfg["thinking_stage"]
            chat_uuid = chat.uuid
        if msg or files:
            chat.append(msgs.UserMsg(msg, files=files))
        self._save_chat(chat)
        if chat.ends_with_assistant():
            yield {"type": "done", "reason": "", "content": "", "chat_uuid": chat_uuid}
            return
        if (chat.provider_index is None) or (chat.provider_model is None):
            yield {"type": "error", "content": "No provider or model selected"}
            return
        system_prompt = self.cfg.data.get("system_prompt", "")
        system_prompt = system_prompt.replace("{{language}}", language)
        client_disconnected = False
        max_tool_rounds = 10
        total_usage = {}
        for tool_round in range(max_tool_rounds + 1):
            gen = self.providers.generate(chat.provider_index, chat.provider_model, thinking_stage=chat.thinking_stage)
            if gen is None:
                if tool_round == 0:
                    yield {"type": "error", "content": "Failed to generate"}
                return
            reasons = []
            contents = []
            tool_calls = None
            state : Literal["content", "reason"] = "content"
            api_error = False
            try:
                for i in self.providers.providers[chat.provider_index].client(gen[0], chat.msg_tree, gen[1], True, thinking_stage=gen[3], system_prompt=system_prompt, tools=tools, **gen[2]):
                    if i[0] == "tool_calls":
                        tool_calls = i[1]
                    elif i[0] != state:
                        if i[0] == "reason":
                            yield {"type": "reason_start"}
                        else:
                            yield {"type": "reason_end"}
                        state = i[0]
                    if i[0] == "reason":
                        reasons.append(i[1])
                        yield {"type": "reason", "content": i[1]}
                    if i[0] == "content":
                        contents.append(i[1])
                        yield {"type": "content", "content": i[1]}
                    if i[0] == "usage":
                        yield {"type": "usage", "usage": i[1]}
                        u = i[1]
                        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                            total_usage[k] = total_usage.get(k, 0) + u.get(k, 0)
                        details = u.get("completion_tokens_details", {})
                        if details:
                            d = total_usage.setdefault("completion_tokens_details", {})
                            d["reasoning_tokens"] = d.get("reasoning_tokens", 0) + details.get("reasoning_tokens", 0)
            except GeneratorExit:
                client_disconnected = True
                break
            except Exception as e:
                log.error("stream error", e)
                api_error = True
                try:
                    yield {"type": "error", "content": str(e)}
                except GeneratorExit:
                    client_disconnected = True
                break
            # Check if model wants to call tools
            if tool_calls and not client_disconnected and not api_error:
                # Save the tool call message
                combined_content = "".join(contents)
                combined_reason = "".join(reasons)
                tc_msg = msgs.AssistantMsg(combined_content, interrupted=False, usage=deepcopy(total_usage) if total_usage else None, reason=combined_reason, tool_calls=tool_calls)
                chat.append(tc_msg)
                # Execute each tool and append results
                yield {"type": "tool_calls", "tool_calls": tool_calls}
                for tc in tool_calls:
                    result = execute_tool(tc) if execute_tool else f"Error: no tool executor"
                    chat.append(msgs.ToolResultMsg(tc.get("id", ""), result))
                    yield {"type": "tool_result", "tool_call_id": tc.get("id", ""), "tool_name": tc.get("function", {}).get("name", ""), "content": result}
                self._save_chat(chat)
                # Continue loop to re-call provider with tool results
                continue
            # Normal response (content/reason, no tool calls)
            reason = "".join(reasons)
            content = "".join(contents)
            interrupted = client_disconnected or api_error
            if reason or content:
                if reason:
                    chat.append(msgs.AssistantMsg(content, interrupted, deepcopy(total_usage) if total_usage else None, reason=reason))
                else:
                    chat.append(msgs.AssistantMsg(content, interrupted, deepcopy(total_usage) if total_usage else None))
                self._save_chat(chat)
            # Only yield "done" if client is still connected
            if not client_disconnected:
                yield {"type": "done", "reason": reason, "content": content, "chat_uuid": chat_uuid}
            return
    def set_thinking_stage(self, stage: int | None, chat_uuid: str | None = None):
        if chat_uuid:
            idx = self._find_chat_index(chat_uuid)
            if idx is not None:
                chat = Chat.load(self.cfg["chats"][idx])
                chat.thinking_stage = stage
                self.cfg["chats"][idx] = chat.store()
                self.cfg.save()
        else:
            # Save as global default for new chats
            self.cfg["thinking_stage"] = stage
            self.cfg.save()
    def rename_chat_by_uuid(self, uuid_str: str, title: str) -> bool:
        idx = self._find_chat_index(uuid_str)
        if idx is None:
            return False
        cd = self.cfg["chats"][idx]
        if not isinstance(cd, dict):
            return False
        chat = Chat.load(cd) if "msg_tree" in cd else Chat()
        chat.title = title
        self.cfg["chats"][idx] = chat.store()
        self.cfg.save()
        return True
    def edit_user_message_by_uuid(self, uuid_str: str, msg_id: int, new_content: str) -> bool:
        idx = self._find_chat_index(uuid_str)
        if idx is None:
            return False
        chat = Chat.load(self.cfg["chats"][idx])
        if msg_id < 0 or msg_id >= len(chat.msg_tree.msg_list):
            return False
        wrapper = chat.msg_tree.msg_list[msg_id]
        if wrapper.type != "UserMsg":
            return False
        parent_id = wrapper.parent
        if parent_id is None:
            return False
        new_msg = msgs.UserMsg(new_content)
        chat.msg_tree.append_after(parent_id, new_msg)
        self.cfg["chats"][idx] = chat.store()
        self.cfg.save()
        return True
    def switch_branch_by_uuid(self, uuid_str: str, msg_id: int, branch_index: int) -> bool:
        idx = self._find_chat_index(uuid_str)
        if idx is None:
            return False
        chat = Chat.load(self.cfg["chats"][idx])
        if msg_id < 0 or msg_id >= len(chat.msg_tree.msg_list):
            return False
        wrapper = chat.msg_tree.msg_list[msg_id]
        if wrapper.parent is None:
            return False
        parent = chat.msg_tree.msg_list[wrapper.parent]
        if branch_index < 0 or branch_index >= len(parent.children):
            return False
        parent.child = branch_index
        self.cfg["chats"][idx] = chat.store()
        self.cfg.save()
        return True
    def retry_by_uuid(self, uuid_str: str, msg_id: int) -> bool:
        """Retry an assistant message: reset the active branch so the AI re-responds
        to the parent user message. Does NOT create any new message."""
        idx = self._find_chat_index(uuid_str)
        if idx is None:
            return False
        chat = Chat.load(self.cfg["chats"][idx])
        if msg_id < 0 or msg_id >= len(chat.msg_tree.msg_list):
            return False
        wrapper = chat.msg_tree.msg_list[msg_id]
        if wrapper.parent is None:
            return False
        user_msg = chat.msg_tree.msg_list[wrapper.parent]
        # Clear active child so tree ends at user_msg → AI re-responds
        user_msg.child = None
        self.cfg["chats"][idx] = chat.store()
        self.cfg.save()
        return True

class App:
    cfg : Config
    providers : Providers
    chats : Chats
    recognize_data : dict
    template_data : dict
    def __init__(self):
        self.cfg = Config("config.json", {"providers":[],"provider_index":None,"provider_model":None,"thinking_stage":None,"chats":[],"system_prompt":"","tools":{"get_current_time":{"enabled":True}}})
        self.providers = Providers(self.cfg)
        self.chats = Chats(self.cfg, self.providers)
        # Load data files
        self.recognize_data = self._load_json("data/recognize.json", {"providers": []})
        self.template_data = self._load_json("data/template.json", {"templates": []})
    def _load_json(self, path: str, default: dict) -> dict:
        try:
            if os.path.exists(path):
                with open(path, "r") as fp:
                    return json.load(fp)
        except Exception as e:
            log.error(f"Failed to load {path}", e)
        return default
    def get_model_templates(self) -> list:
        return self.template_data.get("templates", [])
    def get_thinking_presets(self) -> list:
        try:
            path = os.path.join(os.path.dirname(__file__), "data", "thinking.json")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("presets", [])
        except Exception:
            return []
    def get_system_prompt(self) -> str:
        return self.cfg.data.get("system_prompt", "")
    def set_system_prompt(self, value: str):
        self.cfg.data["system_prompt"] = value
        self.cfg.save()
    def get_recognized_models(self, provider_index: int) -> list:
        """Call the provider's /v1/models API endpoint, then match returned model IDs
        against recognize.json to identify known models and apply templates."""
        if provider_index < 0 or provider_index >= len(self.providers.providers):
            return []
        provider = self.providers.providers[provider_index]
        templates = {t["id"]: t for t in self.template_data.get("templates", [])}
        known = self.recognize_data.get("models", {})

        # Call the provider's /v1/models endpoint (OpenAI-compatible only)
        api_model_ids = []
        try:
            if provider.type in ("openai", "deepseek", "moonshot", "aliyun"):
                client = openai.OpenAI(base_url=provider.base_url, api_key=provider.api_key)
                models_response = client.models.list()
                api_model_ids = sorted([m.id for m in models_response])
        except Exception:
            pass  # If API call fails (auth, network), return empty

        # Build recognized model list by looking up each ID in recognize.json
        existing_ids = {m.id for m in provider.models}
        patterns = self.recognize_data.get("patterns", [])
        results = []
        for model_id in api_model_ids:
            info = known.get(model_id, {})
            if not info:
                # Fallback: try regex patterns
                for p in patterns:
                    pattern_str = p.get("pattern", "")
                    try:
                        if re.match(pattern_str, model_id):
                            info = {"name": p.get("name", model_id), "template": p.get("template")}
                            break
                    except re.error:
                        pass
            model_info = {
                "id": model_id,
                "name": info.get("name", model_id),
                "exists": model_id in existing_ids
            }
            template_id = info.get("template")
            if template_id and template_id in templates:
                model_info["template"] = templates[template_id]
            results.append(model_info)

        return results
    def add_model_to_provider(self, provider_index: int, model_data: dict) -> bool:
        """Add a model to a provider. model_data should have 'id' and 'name'.
        Optional 'template' key to apply capabilities from template.json."""
        if provider_index < 0 or provider_index >= len(self.providers.providers):
            return False
        provider = self.providers.providers[provider_index]
        mid = model_data.get("id", "").strip()
        mname = model_data.get("name", mid).strip()
        if not mid:
            return False
        # Check for duplicates
        for existing in provider.models:
            if existing.id == mid:
                return False
        model = Model(mname, mid)
        # Apply template if specified
        template_id = model_data.get("template")
        if template_id:
            for t in self.template_data.get("templates", []):
                if t.get("id") == template_id:
                    model.support_vision = t.get("support_vision", False)
                    model.support_tools = t.get("support_tools", False)
                    model.default_max_tokens = t.get("default_max_tokens", 4096)
                    model.default_temperature = t.get("default_temperature", None)
                    thinking_stages = t.get("thinking_stages", [])
                    if thinking_stages:
                        model.set_thinking_stages(thinking_stages)
                    break
        provider.models.append(model)
        # Save to config
        data = self.cfg["providers"]
        if 0 <= provider_index < len(data):
            data[provider_index] = provider.store()
            self.cfg["providers"] = data
            self.cfg.save()
        return True
    def delete_model_from_provider(self, provider_index: int, model_index: int) -> bool:
        if provider_index < 0 or provider_index >= len(self.providers.providers):
            return False
        provider = self.providers.providers[provider_index]
        if model_index < 0 or model_index >= len(provider.models):
            return False
        del provider.models[model_index]
        data = self.cfg["providers"]
        if 0 <= provider_index < len(data):
            data[provider_index] = provider.store()
            self.cfg["providers"] = data
            self.cfg.save()
        return True
    def edit_model_on_provider(self, provider_index: int, model_index: int, model_data: dict) -> bool:
        """Edit an existing model's properties. Optionally re-apply a template,
        then override individual fields."""
        if provider_index < 0 or provider_index >= len(self.providers.providers):
            return False
        provider = self.providers.providers[provider_index]
        if model_index < 0 or model_index >= len(provider.models):
            return False
        model = provider.models[model_index]

        # Re-apply template if specified
        template_id = model_data.get("template")
        if template_id:
            for t in self.template_data.get("templates", []):
                if t.get("id") == template_id:
                    model.support_vision = t.get("support_vision", False)
                    model.support_tools = t.get("support_tools", False)
                    model.default_max_tokens = t.get("default_max_tokens", 4096)
                    model.default_temperature = t.get("default_temperature", None)
                    thinking_stages = t.get("thinking_stages", [])
                    if thinking_stages:
                        model.set_thinking_stages(thinking_stages)
                    break

        # Individual field overrides (applied after template, so these win)
        if "name" in model_data:
            name = model_data["name"].strip()
            if name:
                model.name = name
        if "support_vision" in model_data:
            model.support_vision = bool(model_data["support_vision"])
        if "support_tools" in model_data:
            model.support_tools = bool(model_data["support_tools"])
        if "thinking_stages" in model_data:
            stages = model_data["thinking_stages"]
            if isinstance(stages, list):
                default_stage = model_data.get("thinking_stage", 0)
                model.set_thinking_stages(stages, default_stage)
        elif "thinking_stage" in model_data:
            idx = int(model_data["thinking_stage"])
            if 0 <= idx < len(model.thinking_stages):
                model.thinking_stage = idx
        if "temperature" in model_data:
            val = model_data["temperature"]
            model.default_temperature = float(val) if val is not None else None
        if "max_tokens" in model_data:
            model.default_max_tokens = int(model_data["max_tokens"])

        # Save to config
        data = self.cfg["providers"]
        if 0 <= provider_index < len(data):
            data[provider_index] = provider.store()
            self.cfg["providers"] = data
            self.cfg.save()
        return True
    def get_providers_json(self) -> list:
        """Returns providers/models list for the dropdown UI."""
        result = []
        for pi, provider in enumerate(self.providers.providers):
            pdata = {"index": pi, "name": provider.name, "base_url": provider.base_url, "type": provider.type, "models": []}
            for mi, model in enumerate(provider.models):
                pdata["models"].append({"index": mi, "name": model.name, "id": model.id, "support_thinking": model.support_thinking, "support_vision": model.support_vision, "support_tools": model.support_tools, "support_thinking_control": model.support_thinking_control, "thinking_stages": model.thinking_stages, "thinking_stage": model.thinking_stage, "default_max_tokens": model.default_max_tokens, "default_temperature": model.default_temperature})
            result.append(pdata)
        return result
    def get_chats_list(self) -> list:
        """Returns chat list for sidebar."""
        chats = self.cfg["chats"]
        result = []
        for i, chat in enumerate(chats):
            if isinstance(chat, dict):
                result.append({"index": i, "uuid": chat.get("uuid", ""), "title": chat.get("title", "New Chat")})
        return result
    def get_current_state(self, chat_uuid: str | None = None) -> dict:
        if chat_uuid:
            chat = self.chats._load_chat(chat_uuid)
            if chat is not None:
                return {"provider_index": chat.provider_index, "provider_model": chat.provider_model, "chat_uuid": chat.uuid, "thinking_stage": chat.thinking_stage, "system_prompt": self.get_system_prompt(), "tools": self.get_tools_config()}
        return {"provider_index": self.providers.provider_index, "provider_model": self.providers.provider_model, "chat_uuid": None, "thinking_stage": self.cfg["thinking_stage"], "system_prompt": self.get_system_prompt(), "tools": self.get_tools_config()}
    def set_thinking_stage(self, stage: int | None, chat_uuid: str | None = None):
        self.chats.set_thinking_stage(stage, chat_uuid)
    def select_provider(self, provider_idx: int, model_idx: int, chat_uuid: str | None = None):
        self.cfg["provider_index"] = provider_idx
        self.cfg["provider_model"] = model_idx
        self.providers.provider_index = provider_idx
        self.providers.provider_model = model_idx
        if chat_uuid:
            chat = self.chats._load_chat(chat_uuid)
            if chat:
                chat.provider_index = provider_idx
                chat.provider_model = model_idx
                self.chats._save_chat(chat)
        self.cfg.save()
    def add_provider(self, name: str, base_url: str, api_key: str, ptype: str):
        provider = Provider(name, base_url, api_key, ptype)
        self.providers.providers.append(provider)
        self.cfg["providers"].append(provider.store())
        self.cfg.save()
    def new_chat(self):
        """Return None to indicate a clean/new chat state.
        The actual Chat object is created lazily when the first message is sent."""
        return None
    def switch_chat_by_uuid(self, uuid_str: str) -> bool:
        if not uuid_str:
            return False
        return self.chats._find_chat_index(uuid_str) is not None
    def delete_chat_by_uuid(self, uuid_str: str) -> bool:
        idx = self.chats._find_chat_index(uuid_str)
        if idx is None:
            return False
        del self.cfg["chats"][idx]
        self.cfg.save()
        return True
    def get_chat_messages(self, uuid_str: str | None = None) -> list:
        """Get messages for display."""
        if uuid_str is None:
            return []
        idx = self.chats._find_chat_index(uuid_str)
        if idx is None:
            return []
        chat = Chat.load(self.cfg["chats"][idx])
        if chat is None:
            return []
        messages = []
        cur = 0
        while True:
            wrapper = chat.msg_tree.msg_list[cur]
            if wrapper.type in ("UserMsg", "AssistantMsg", "ReasonAssistantMsg", "ToolCallMsg", "ToolResultMsg"):
                msg_data = {"type": wrapper.type, "content": wrapper.msg.content, "msg_id": cur}
                if isinstance(wrapper.msg, msgs.AssistantMsg):
                    if wrapper.msg.reason:
                        msg_data["reason"] = wrapper.msg.reason
                    if wrapper.msg.usage is not None:
                        msg_data["usage"] = wrapper.msg.usage
                    if wrapper.msg.tool_calls:
                        msg_data["tool_calls"] = wrapper.msg.tool_calls
                if wrapper.type == "UserMsg" and wrapper.msg.files:
                    msg_data["files"] = wrapper.msg.files
                if wrapper.type == "ToolResultMsg":
                    msg_data["tool_call_id"] = wrapper.msg.tool_call_id
                # Branch info: check if this message's parent has multiple branches
                if wrapper.parent is not None:
                    parent = chat.msg_tree.msg_list[wrapper.parent]
                    if len(parent.children) > 1:
                        try:
                            child_idx = parent.children.index(cur)
                            msg_data["branches"] = len(parent.children)
                            msg_data["active_branch"] = child_idx
                        except ValueError:
                            pass
                messages.append(msg_data)
            if wrapper.child is not None:
                cur = wrapper.children[wrapper.child]
            else:
                break
        return messages
    def rename_chat(self, uuid_str: str, title: str) -> bool:
        return self.chats.rename_chat_by_uuid(uuid_str, title)
    def rename_chat_ai(self, uuid_str: str) -> bool:
        """Rename chat using first user message as title."""
        idx = self.chats._find_chat_index(uuid_str)
        if idx is None:
            return False
        chat = Chat.load(self.cfg["chats"][idx])
        for wrapper in chat.msg_tree.msg_list:
            if wrapper.type == "UserMsg" and wrapper.msg.content:
                title = wrapper.msg.content[:50]
                if len(wrapper.msg.content) > 50:
                    title += "..."
                chat.title = title
                self.cfg["chats"][idx] = chat.store()
                self.cfg.save()
                return True
        return False
    def edit_user_message(self, chat_uuid: str, msg_id: int, new_content: str) -> bool:
        """Edit a user message by branching."""
        return self.chats.edit_user_message_by_uuid(chat_uuid, msg_id, new_content)
    def switch_branch(self, chat_uuid: str, msg_id: int, branch_index: int) -> bool:
        return self.chats.switch_branch_by_uuid(chat_uuid, msg_id, branch_index)
    def retry_message(self, chat_uuid: str, msg_id: int) -> bool:
        return self.chats.retry_by_uuid(chat_uuid, msg_id)
    def get_tools_config(self) -> dict:
        """Returns the tools configuration dict."""
        tools = self.cfg.data.get("tools", {})
        if not isinstance(tools, dict):
            tools = {}
        return tools
    def set_tool_enabled(self, tool_id: str, enabled: bool):
        """Enable or disable a specific tool."""
        tools = self.cfg.data.get("tools", {})
        if not isinstance(tools, dict):
            tools = {}
        if tool_id not in tools:
            tools[tool_id] = {}
        tools[tool_id]["enabled"] = bool(enabled)
        self.cfg.data["tools"] = tools
        self.cfg.save()
    def _get_enabled_tools(self) -> list:
        """Build the OpenAI-compatible tools list from enabled tools config."""
        tools_config = self.get_tools_config()
        tools_list = []
        if tools_config.get("get_current_time", {}).get("enabled", True):
            tools_list.append({
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get the current date and time. Returns the current date and time in a readable format.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            })
        return tools_list
    def _execute_tool(self, tool_call: dict) -> str:
        """Execute a tool call and return the result string."""
        name = tool_call.get("function", {}).get("name", "")
        if name == "get_current_time":
            now = datetime.datetime.now()
            return now.strftime("%Y-%m-%d %H:%M:%S")
        return f"Error: unknown tool '{name}'"
