from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class NewsContext:
    fetched_at: str
    sources_used: list[str]
    headline_count: int
    macro_trends: list[str] = field(default_factory=list)
    sector_signals: dict[str, str] = field(default_factory=dict)
    fund_developments: list[str] = field(default_factory=list)
    raw_headlines: list[str] = field(default_factory=list)
    summary_model: str = ""

    def __post_init__(self) -> None:
        if len(self.macro_trends) > 3:
            self.macro_trends = self.macro_trends[:3]
