from typing import Annotated

from fastapi import Path

IdPath = Annotated[int, Path(ge=1)]
