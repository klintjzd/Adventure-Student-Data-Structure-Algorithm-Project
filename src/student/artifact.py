#Artifact

from src.api import Position


class Artifact:

    def __init__(
        self,
        artifact_id: str,
        position: Position,
        value: int,
    ) -> None:
        self._artifact_id = artifact_id
        self._position = position
        self._value = value

    @property
    def artifact_id(self) -> str:
        return self._artifact_id

    @property
    def position(self) -> Position:
        return self._position

    @property
    def value(self) -> int:
        return self._value
