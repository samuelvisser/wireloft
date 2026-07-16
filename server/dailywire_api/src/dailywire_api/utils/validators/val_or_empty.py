from typing import Annotated, Any

from pydantic import BeforeValidator

def noneish_to_empty(v: Any):
    if v is None:
        return ""
    return v


type ValOrEmpty = Annotated[str, BeforeValidator(noneish_to_empty)]
