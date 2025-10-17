from typing import Annotated, Optional, Any

from pydantic import BeforeValidator

def emptyish_to_zero(v: Any):
    if not v:
        return 0
    if isinstance(v, str) and v.strip() == "":
        return 0
    return v


type ValOrZero[T] = Annotated[Optional[T], BeforeValidator(emptyish_to_zero)]