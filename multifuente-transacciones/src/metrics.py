from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any, Dict

from .models import ProcessingReport


class MetricsCalculator:
    """Calcula KPIs operativos, calidad de datos y agregaciones financieras."""

    CANONICAL_STATUSES = ("SUCCESS", "FAILED", "PENDING")
    CANONICAL_SOURCES = ("SOURCE_A", "SOURCE_B", "SOURCE_C")

    @classmethod
    def compute(cls, report: ProcessingReport) -> Dict[str, Any]:
        valid = report.valid_transactions
        invalid = report.invalid_transactions

        total_processed = len(valid) + len(invalid)
        valid_count = len(valid)
        invalid_count = len(invalid)

        valid_pct = round((valid_count / total_processed) * 100, 2) if total_processed > 0 else 0.0
        invalid_pct = round((invalid_count / total_processed) * 100, 2) if total_processed > 0 else 0.0

        # Conteo por estado (garantizando presencia de los 3 estados canónicos)
        raw_status_counts = Counter(tx.status for tx in valid)
        by_status = {status: raw_status_counts.get(status, 0) for status in cls.CANONICAL_STATUSES}

        # Suma de montos agrupados por moneda (usando Decimal para precisión exacta)
        currency_sums: Dict[str, Decimal] = {}
        for tx in valid:
            curr = tx.currency
            currency_sums[curr] = currency_sums.get(curr, Decimal("0.00")) + Decimal(str(tx.amount))

        amount_by_currency = {
            curr: float(total.quantize(Decimal("0.01")))
            for curr, total in sorted(currency_sums.items())
        }

        # Conteo de transacciones válidas por fuente
        raw_source_counts = Counter(tx.source for tx in valid)
        by_source = {src: raw_source_counts.get(src, 0) for src in cls.CANONICAL_SOURCES}

        # Conteo total por fuente (incluyendo intentos detectados antes de fallar)
        total_source_counts = Counter(tx.source for tx in valid)
        for err in invalid:
            if err.detected_source in cls.CANONICAL_SOURCES:
                total_source_counts[err.detected_source] += 1
        by_source_total = {src: total_source_counts.get(src, 0) for src in cls.CANONICAL_SOURCES}

        return {
            "total_processed": total_processed,
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "valid_percentage": valid_pct,
            "invalid_percentage": invalid_pct,
            "by_status": by_status,
            "amount_by_currency": amount_by_currency,
            "by_source": by_source,
            "by_source_total": by_source_total,
        }
