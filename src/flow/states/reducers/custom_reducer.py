from typing import Annotated, Any
from typing_extensions import TypedDict

def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    result = left.copy() if left else {}
    result.update(right)
    return result

def deep_merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """
    Deeply merges two dictionaries. 
    If a key exists in both and both values are dictionaries, they are merged recursively.
    """
    if not left:
        return right or {}
    if not right:
        return left or {}
        
    result = left.copy()
    for key, value in right.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result

# Reducer fun
def override(_: dict, new: dict) -> dict:
    return new