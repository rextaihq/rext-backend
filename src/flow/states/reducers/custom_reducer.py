from typing import Annotated, Any
from typing_extensions import TypedDict

def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    result = left.copy() if left else {}
    result.update(right)
    return result

# Reducer fun
def override(_: dict, new: dict) -> dict:
    return new