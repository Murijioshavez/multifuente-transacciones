from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

from .models import InvalidTransaction, NormalizedTransaction, ProcessingReport
from .normalizer import NormalizationError, TransactionNormalizer


class TransactionPipeline:
    """
    Orquesta la ingestión, detección de fuente, normalización y validación estricta,
    separando sin pérdida de información los registros válidos de los inválidos.
    """

    def __init__(self, rules_path: Path | str) -> None:
        self.normalizer = TransactionNormalizer(rules_path)

    def process_records(self, raw_records: Any) -> ProcessingReport:
        if not isinstance(raw_records, list):
            raise ValueError(
                "El archivo JSON raíz debe contener una lista (array) de transacciones."
            )

        report = ProcessingReport()

        for idx, record in enumerate(raw_records):
            detected_source = "UNKNOWN"
            try:
                detected_source = self.normalizer.detect_source(record)
                normalized = self.normalizer.normalize(record, detected_source)
                self._validate_post_conditions(normalized)
                report.valid_transactions.append(normalized)
            except NormalizationError as exc:
                report.invalid_transactions.append(
                    InvalidTransaction(
                        index=idx,
                        detected_source=detected_source,
                        error_reason=str(exc),
                        raw_record=record,
                    )
                )
            except Exception as exc:  # Defensa ante estructuras inesperadas
                report.invalid_transactions.append(
                    InvalidTransaction(
                        index=idx,
                        detected_source=detected_source,
                        error_reason=f"Error inesperado de procesamiento: {exc}",
                        raw_record=record,
                    )
                )

        return report

    def process_file(self, file_path: Path | str) -> ProcessingReport:
        path = Path(file_path)
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return self.process_records(data)

    def _validate_post_conditions(self, tx: NormalizedTransaction) -> None:
        """Doble verificación contractual sobre el objeto normalizado final."""
        if not isinstance(tx.id, str) or not tx.id.strip():
            raise NormalizationError("Post-validación fallida: 'id' vacío.")
        if not isinstance(tx.amount, float) or tx.amount <= 0:
            raise NormalizationError("Post-validación fallida: 'amount' debe ser > 0.")
        if tx.currency not in self.normalizer.supported_currencies:
            raise NormalizationError(f"Post-validación fallida: moneda '{tx.currency}' no permitida.")
        if tx.status not in self.normalizer.allowed_statuses:
            raise NormalizationError(f"Post-validación fallida: estado '{tx.status}' no permitido.")
        if not tx.timestamp.endswith("Z"):
            raise NormalizationError("Post-validación fallida: 'timestamp' no está en UTC ISO-8601.")
