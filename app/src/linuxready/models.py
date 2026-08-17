from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RawItem:
    source: str
    raw_name: str
    raw_keys: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanItem:
    source: str
    raw_name: str
    raw_keys: dict[str, Any] = field(default_factory=dict)
    matched_id: Optional[str] = None
    match_tier: Optional[int] = None
    match_confidence: Optional[str] = None
    verdict: Optional[str] = None
    verdict_reason: Optional[str] = None
    is_blocker: bool = False
    evidence: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


@dataclass
class CollectorResult:
    id: str
    status: str  # ok | partial | failed | skipped
    duration_ms: int
    warnings: list[str] = field(default_factory=list)
    items: list[RawItem] = field(default_factory=list)


@dataclass
class ScanContext:
    db_path: str
    timeout_default: int = 30
    timeout_hardware: int = 60


@dataclass
class ScanResult:
    schema_version: str
    scan_id: str
    scanned_at: str
    db_build: str
    app_version: str
    system: dict[str, Any]
    collectors: list[dict[str, Any]]
    items: list[ScanItem]
    score: dict[str, Any]
