import json
import log
import time
from typing import Any
from translations import translate as t

from tools import safe_get

class MsgBase:
    role: str = ""
    content: str = ""
    def __init__(self, role: str = "", content = ""):
        self.role = role
        self.content = content
    def __repr__(self) -> str:
        return str(self.store())
    def store(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content}
    @staticmethod
    def load(data : dict) -> "MsgBase | UserMsg | AssistantMsg | ReasonAssistantMsg":
        content = safe_get(data, str, "content", "message", "")
        role = safe_get(data, str, "role", "message", "user")
        if role == "user": return UserMsg.load(data)
        if role == "assistant": return AssistantMsg.load(data) # Can be ReasonAssistantMsg
        # else: 
        return MsgBase(role, content)
class UserMsg(MsgBase):
    def __init__(self, content: str = "", files: list[dict] = None):
        super().__init__("user", content)
        self.files = files or []
    def store(self) -> dict[str, Any]:
        data = super().store()
        if self.files:
            data["files"] = self.files
        return data
    @staticmethod
    def load(data : dict) -> "UserMsg":
        content = safe_get(data, str, "content", "message", "")
        files = data.get("files", [])
        if not isinstance(files, list):
            files = []
        return UserMsg(content, files)
class AssistantMsg(MsgBase):
    def __init__(self, content: str = "", interrupted : bool = False):
        super().__init__("assistant", content)
        self.interrupted = interrupted
    def store(self) -> dict[str, Any]:
        data = super().store()
        data["interrupted"] = self.interrupted
        return data
    @staticmethod
    def load(data : dict) -> "AssistantMsg | ReasonAssistantMsg":
        content = safe_get(data, str, "content", "message", "")
        interrupted = safe_get(data, bool, "interrupted", "message", False)
        if "reason" not in data:
            return AssistantMsg(content, interrupted)
        else:
            reason = safe_get(data, str, "reason", "message", "")
            return ReasonAssistantMsg(content, reason, interrupted)
        # 特殊处理reason字段的原因：这类似一个Fallback机制
class ReasonAssistantMsg(AssistantMsg):
    reason: str = ""
    def __init__(self, content: str = "", reason: str = "", interrupted : bool = False):
        super().__init__(content)
        self.reason = reason
        self.interrupted = interrupted
    def store(self) -> dict[str, Any]:
        data = super().store()
        data["reason"] = self.reason
        return data
    @staticmethod
    def load(data : dict) -> "AssistantMsg | ReasonAssistantMsg":
        content = safe_get(data, str, "content", "message", "")
        interrupted = safe_get(data, bool, "interrupted", "message", False)
        reason = safe_get(data, str, "reason", "message", "")
        if reason:
            return ReasonAssistantMsg(content, reason, interrupted)
        else:
            return AssistantMsg(content, interrupted)
class MsgTree:
    class MsgWrapper:
        type : str
        msg : MsgBase
        parent : int | None
        children : list[int]
        child : int | None
        time : float
        def __init__(self, msg : MsgBase, parent : int | None):
            self.type = type(msg).__name__
            self.msg = msg
            self.parent = parent
            self.children = []
            self.child = None
            self.time = time.time()
        def __repr__(self) -> str:
            return str(self.store())
        def store(self) -> dict[str, Any]:
            return {"type": self.type, 
                    "msg": self.msg.store(),
                    "time": self.time,
                    "parent": self.parent,
                    "children": list(self.children), # 创建List[int]的副本
                    "child": self.child
                    }
        @staticmethod
        def load(data : dict) -> "MsgTree.MsgWrapper | None":
            msg_type = MsgBase
            type_ = safe_get(data, str, "type", "message", "MsgBase")
            if (type_ == "MsgBase"): msg_type = MsgBase
            if (type_ == "UserMsg"): msg_type = UserMsg
            if (type_ == "AssistantMsg"): msg_type = AssistantMsg
            if (type_ == "ReasonAssistantMsg"): msg_type = ReasonAssistantMsg
            if (type_ not in ("MsgBase", "UserMsg", "AssistantMsg", "ReasonAssistantMsg",)):
                log.error(t("error.load").replace("CATEGORY", t("error.load.message")).replace("TYPE", data["type"]).replace("DEFAULT","MsgBase"))
            parent = safe_get(data, (int, type(None), ), "parent", "message", None)
            msg = safe_get(data, dict, "msg", "message", None)
            if not msg: return
            msg_wrapper = MsgTree.MsgWrapper(msg_type.load(msg), parent)
            time = safe_get(data, float, "time", "message", 0.)
            children_ = safe_get(data, list, "children", "message", [])
            children = []
            for i in range(len(children_)):
                if (not isinstance(children_[i], int)) or (children_[i] < 0):
                    log.error(t("error.message.load").replace("KEY", "children.%d"%(i,)).replace("DEFAULT","(None)"))
                else:
                    children.append(children_[i])
            child = safe_get(data, (int,type(None),), "child", "message", len(children)-1)
            if isinstance(child, int) and ((child < 0) or (child >= len(children))):
                log.error(t("error.message.load").replace("KEY", "child").replace("DEFAULT",repr(len(children)-1)))
                child = len(children)-1
                if child < 0: child = None
            msg_wrapper.time = time
            msg_wrapper.children = children
            msg_wrapper.child = child
            return msg_wrapper
    msg_list : list[MsgWrapper]
    def __init__(self):
        self.msg_list = []
        self.append(MsgBase("system", "")) # 根消息，也是系统消息。
    def __repr__(self) -> str:
        return str(self.store())
    def store(self) -> dict[str, Any]:
        return {'conversation': [i.store() for i in self.msg_list]}
    @staticmethod
    def load(data : dict) -> "MsgTree":
        msg_tree = MsgTree()
        msg_tree.msg_list = []
        for i in data["conversation"]:
            loaded = MsgTree.MsgWrapper.load(i)
            if loaded is not None:
                if (isinstance(loaded.parent, int)) and (loaded.parent < len(msg_tree.msg_list)): # 否则就是超前了
                    msg_tree.msg_list.append(loaded)
                if loaded.parent is None: # 适用于根消息
                    msg_tree.msg_list.append(loaded)
        return msg_tree
    def get_last_msg_id(self) -> None | int:
        if len(self.msg_list) == 0:
            return None
        else:
            cur : int = 0
            while self.msg_list[cur].child is not None:
                cur = self.msg_list[cur].children[self.msg_list[cur].child]
            return cur
    def append(self, msg : MsgBase):
        cur = self.get_last_msg_id()
        if cur is None: # 相当于len(self.msg_list) == 0:
            self.msg_list.append(MsgTree.MsgWrapper(msg, None))
        else:
            self.msg_list[cur].children.append(len(self.msg_list))
            self.msg_list.append(MsgTree.MsgWrapper(msg, cur))
            self.msg_list[cur].child = len(self.msg_list[cur].children)-1
    def append_after(self, parent_id: int, msg: MsgBase) -> int:
        """Append a message after a specific parent, creating a new branch."""
        idx = len(self.msg_list)
        self.msg_list[parent_id].children.append(idx)
        self.msg_list.append(MsgTree.MsgWrapper(msg, parent_id))
        self.msg_list[parent_id].child = len(self.msg_list[parent_id].children) - 1
        return idx
    def complete_last_assistant(self, idx : int, msg : AssistantMsg | ReasonAssistantMsg):
        if not self.ends_with_assistant():
            return
        if 0 <= idx < len(self.msg_list):
            self.msg_list[idx].msg.content += msg.content
            if self.msg_list[idx].type == "ReasonAssistantMsg":
                if isinstance(msg, ReasonAssistantMsg):
                    self.msg_list[idx].msg.reason += msg.reason
            self.msg_list[idx].time = time.time()
            self.msg_list[idx].msg.interrupted = msg.interrupted
        else:
            raise ValueError("message list index out of range")
    def ends_with_assistant(self):
        last_msg_id = self.get_last_msg_id()
        if last_msg_id is None:
            return False
        else:
            return self.msg_list[last_msg_id].type in ("AssistantMsg","ReasonAssistantMsg",)
