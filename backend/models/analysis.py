from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AnalysisResult:
    category_totals: dict[str, float]
    merchant_totals: list[tuple[str, float]]
    daily_trend: list[tuple[str, float]]
    savings_opportunity: float
    insights: list[str]
    total_spend: float
    transaction_count: int
    anomalies: list[dict[str, str | float | bool | None]] = field(default_factory=list)
    budget_status: dict[str, float] = field(default_factory=dict)

    @property
    def top_merchants(self) -> list[tuple[str, float]]:
        return self.merchant_totals
