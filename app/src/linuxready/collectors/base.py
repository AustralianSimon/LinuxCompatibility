from abc import ABC, abstractmethod
from ..models import CollectorResult, ScanContext


class Collector(ABC):
    id: str
    display_name: str
    requires_admin: bool = False

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def collect(self, ctx: ScanContext) -> CollectorResult: ...
