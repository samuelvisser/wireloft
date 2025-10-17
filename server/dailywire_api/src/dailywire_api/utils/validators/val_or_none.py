from typing import Annotated, Optional, Any

from pydantic import BeforeValidator

def emptyish_to_none(v: Any):
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


type ValOrNone[T] = Annotated[Optional[T], BeforeValidator(emptyish_to_none)]