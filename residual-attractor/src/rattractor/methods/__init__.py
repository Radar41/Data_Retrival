"""Method families. Stages look methods up here by the name the registry carries."""

from .ar import AR
from .base import Fitted, Method
from .fused import Fused
from .holt import Holt
from .ses import SES

FAMILIES: dict[str, type[Method]] = {cls.name: cls for cls in (SES, AR, Holt, Fused)}


def get_method(name: str, cfg: dict) -> Method:
    try:
        return FAMILIES[name](cfg)
    except KeyError:
        raise KeyError(f"no method family {name!r}; known: {sorted(FAMILIES)}") from None


__all__ = ["AR", "SES", "Holt", "Fused", "Fitted", "Method", "FAMILIES", "get_method"]
