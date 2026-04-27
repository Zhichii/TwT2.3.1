import log
from typing import Literal, Any
from translations import translate as t
from copy import deepcopy

def safe_get(data : dict[str, Any], type : type | tuple[type, ...], key : str, category : Literal["message", "provider", "model", "chat"], default : Any) -> Any:
    if (key in data) and (isinstance(data[key], type)):
        return data[key]
    else:
        log.error(t(f"error.load").replace("CATEGORY", t(f"error.load.{category}")).replace("KEY", key).replace("DEFAULT", repr(default)))
        return default

def merge_list(data_dst : list[Any], data_src : list[Any]):
    for i in data_src:
        data_dst.append(i)
def merge(data_dst : dict[str, Any], data_src : dict[str, Any]):
    for key in data_src:
        if key in data_dst:
            if isinstance(data_src[key], (int, str, float, type(None))):
                data_dst[key] = data_src[key]
            elif isinstance(data_src[key], list):
                merge_list(data_dst[key], data_src[key])
            elif isinstance(data_src[key], dict):
                merge(data_dst[key], data_src[key])
            else:
                log.error(f"unknown type `{type(data_src[key])}`")
        else:
            data_dst[key] = deepcopy(data_src[key])