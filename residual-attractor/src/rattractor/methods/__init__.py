"""Method families. Stages look methods up here by the name the registry carries."""

from .ar import AR
from .base import Fitted, Method
from .holt import Holt
from .precomputed import FAMILIES as _GDSS
from .precomputed import Precomputed
from .ses import SES

FAMILIES: dict[str, type[Method]] = {cls.name: cls for cls in (SES, AR, Holt)} | _GDSS


def get_method(name: str, cfg: dict) -> Method:
    try:
        return FAMILIES[name](cfg)
    except KeyError:
        raise KeyError(f"no method family {name!r}; known: {sorted(FAMILIES)}") from None


__all__ = ["AR", "SES", "Holt", "Precomputed", "Fitted", "Method", "FAMILIES", "get_method"]
