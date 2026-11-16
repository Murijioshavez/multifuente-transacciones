from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class NormalizedTransaction:
    """Modelo de salida canónico para una transacción válida normalizada."""

    id: str
    amount: float
    currency: str
    timestamp: str
    status: str
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InvalidTransaction:
    """Registro de auditoría para transacciones rechazadas durante la ingestión."""

    index: int
    detected_source: str
    error_reason: str
    raw_record: Any

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessingReport:
    """Resultado consolidado de la ejecución del pipeline de procesamiento."""

    valid_transactions: List[NormalizedTransaction] = field(default_factory=list)
    invalid_transactions: List[InvalidTransaction] = field(default_factory=list)

    def valid_as_dicts(self) -> List[Dict[str, Any]]:
        return [tx.to_dict() for tx in self.valid_transactions]

    def invalid_as_dicts(self) -> List[Dict[str, Any]]:
        return [err.to_dict() for err in self.invalid_transactions]
