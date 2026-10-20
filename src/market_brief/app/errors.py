"""Failures that belong to configuration and wiring, not to market math."""


class ConfigError(Exception):
    """runtime.yaml, watchlist.yaml, or the ingest connection is not usable."""


class IngestError(Exception):
    """The backend rejected one crawled batch."""


class UnknownAdapterError(ConfigError):
    """A name in runtime.yaml is not in the explicit registry."""

    def __init__(self, slot: str, name: str, known: list[str] | tuple[str, ...]) -> None:
        self.slot = slot
        self.name = name
        self.known = tuple(known)
        known_text = ", ".join(self.known) if self.known else "(không có)"
        super().__init__(f"Không có {slot} tên '{name}'. Tên hợp lệ: {known_text}.")
