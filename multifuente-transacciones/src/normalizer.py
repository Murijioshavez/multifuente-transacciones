from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Tuple

from .models import NormalizedTransaction


class NormalizationError(Exception):
    """Excepción controlada cuando un registro incumple reglas de formato o negocio."""


class TransactionNormalizer:
    """Detecta la fuente de origen y transforma registros heterogéneos al esquema canónico."""

    def __init__(self, rules_path: Path | str) -> None:
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules(self.rules_path)

        self.supported_currencies = {
            c.strip().upper() for c in self.rules.get("supported_currencies", [])
        }
        self.currency_symbols: Dict[str, str] = self.rules.get("currency_symbols", {})
        self.allowed_statuses = {
            s.strip().upper() for s in self.rules.get("allowed_statuses", [])
        }
        self.status_mapping: Dict[str, str] = {
            k.strip().lower(): v.strip().upper()
            for k, v in self.rules.get("status_mapping", {}).items()
        }
        self.sources_config: Dict[str, Dict[str, Any]] = self.rules.get("sources", {})

    @staticmethod
    def _load_rules(path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"No se encontró el archivo de configuración: {path}")
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def detect_source(self, record: Any) -> str:
        """
        Identifica la fuente evaluando las llaves del diccionario contra los esquemas
        declarados en config/rules.json.
        """
        if not isinstance(record, dict) or not record:
            raise NormalizationError("El registro no es un objeto JSON válido o está vacío.")

        record_keys = set(record.keys())

        # 1. Coincidencia completa con alguno de los esquemas registrados por fuente
        for source_name, cfg in self.sources_config.items():
            schemas = cfg.get("key_schemas") or [cfg.get("required_keys", [])]
            for schema_keys in schemas:
                required = set(schema_keys)
                if required and required.issubset(record_keys):
                    return source_name

        # 2. Diagnóstico de coincidencia parcial (faltan campos críticos)
        best_match = None
        best_overlap = 0
        missing_for_best: list[str] = []

        for source_name, cfg in self.sources_config.items():
            schemas = cfg.get("key_schemas") or [cfg.get("required_keys", [])]
            for schema_keys in schemas:
                required = set(schema_keys)
                overlap = len(required.intersection(record_keys))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = source_name
                    missing_for_best = sorted(required - record_keys)

        if best_match and best_overlap >= 2:
            raise NormalizationError(
                f"Esquema incompleto para {best_match}: faltan campos críticos {missing_for_best}."
            )

        raise NormalizationError(
            f"Fuente desconocida: la estructura de llaves {sorted(record_keys)} no coincide con ninguna fuente registrada."
        )

    @staticmethod
    def _get_aliased_field(
        record: Dict[str, Any], source_cfg: Dict[str, Any], canonical_name: str
    ) -> Tuple[Any, str]:
        aliases = source_cfg.get("field_aliases", {}).get(canonical_name, [canonical_name])
        for alias in aliases:
            if alias in record:
                return record[alias], alias
        return None, aliases[0]

    def normalize(self, record: Dict[str, Any], source: str) -> NormalizedTransaction:
        """Despacha el registro al adaptador específico de la fuente detectada."""
        if source == "SOURCE_A":
            return self._normalize_source_a(record)
        if source == "SOURCE_B":
            return self._normalize_source_b(record)
        if source == "SOURCE_C":
            return self._normalize_source_c(record)
        raise NormalizationError(f"Adaptador no implementado para la fuente: {source}")

    def _normalize_source_a(self, record: Dict[str, Any]) -> NormalizedTransaction:
        cfg = self.sources_config["SOURCE_A"]
        raw_id, id_key = self._get_aliased_field(record, cfg, "id")
        raw_amount, amt_key = self._get_aliased_field(record, cfg, "amount")
        raw_curr, curr_key = self._get_aliased_field(record, cfg, "currency")
        raw_ts, ts_key = self._get_aliased_field(record, cfg, "timestamp")
        raw_status, status_key = self._get_aliased_field(record, cfg, "status")

        tx_id = self._parse_id(raw_id, id_key)
        amount = self._parse_standard_decimal_amount(raw_amount, amt_key)
        currency = self._parse_currency_code(raw_curr, curr_key)
        timestamp = self._parse_formatted_timestamp(raw_ts, cfg["date_format"], ts_key)
        status = self._parse_status(raw_status, status_key)

        return NormalizedTransaction(
            id=tx_id,
            amount=amount,
            currency=currency,
            timestamp=timestamp,
            status=status,
            source="SOURCE_A",
        )

    def _normalize_source_b(self, record: Dict[str, Any]) -> NormalizedTransaction:
        cfg = self.sources_config["SOURCE_B"]
        raw_id, id_key = self._get_aliased_field(record, cfg, "id")
        raw_total, total_key = self._get_aliased_field(record, cfg, "amount")
        raw_curr, curr_key = self._get_aliased_field(record, cfg, "currency")
        raw_ts, ts_key = self._get_aliased_field(record, cfg, "timestamp")
        raw_status, status_key = self._get_aliased_field(record, cfg, "status")

        if raw_id is None or isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
            raise NormalizationError(f"Campo '{id_key}' inválido o nulo en Fuente B.")
        tx_id = str(raw_id).strip()
        if not tx_id:
            raise NormalizationError(f"Campo '{id_key}' vacío en Fuente B.")

        divisor = int(cfg.get("cents_divisor", 100))
        amount = self._parse_cents_amount(raw_total, divisor, total_key)
        currency = self._parse_currency_code(raw_curr, curr_key)
        timestamp = self._parse_formatted_timestamp(raw_ts, cfg["date_format"], ts_key)
        status = self._parse_status(raw_status, status_key)

        return NormalizedTransaction(
            id=tx_id,
            amount=amount,
            currency=currency,
            timestamp=timestamp,
            status=status,
            source="SOURCE_B",
        )

    def _normalize_source_c(self, record: Dict[str, Any]) -> NormalizedTransaction:
        cfg = self.sources_config["SOURCE_C"]
        raw_id, id_key = self._get_aliased_field(record, cfg, "id")
        raw_amt, amt_key = self._get_aliased_field(record, cfg, "amount")
        raw_ts, ts_key = self._get_aliased_field(record, cfg, "timestamp")
        raw_status, status_key = self._get_aliased_field(record, cfg, "status")

        tx_id = self._parse_id(raw_id, id_key)
        currency, amount = self._parse_european_amount_and_currency(raw_amt, amt_key)
        timestamp = self._parse_iso_timestamp(raw_ts, ts_key)
        status = self._parse_status(raw_status, status_key)

        return NormalizedTransaction(
            id=tx_id,
            amount=amount,
            currency=currency,
            timestamp=timestamp,
            status=status,
            source="SOURCE_C",
        )

    # --- Métodos auxiliares de parsing y sanitización ---

    @staticmethod
    def _parse_id(raw_value: Any, field_name: str) -> str:
        if raw_value is None or isinstance(raw_value, bool):
            raise NormalizationError(f"Campo '{field_name}' nulo o tipo no permitido.")
        cleaned = str(raw_value).strip()
        if not cleaned:
            raise NormalizationError(f"Campo '{field_name}' está vacío.")
        return cleaned

    @staticmethod
    def _round_money(value: Decimal) -> float:
        if not value.is_finite():
            raise NormalizationError("El monto numérico no es finito (NaN/Infinity).")
        if value <= Decimal("0"):
            raise NormalizationError(f"El monto debe ser mayor a 0 (recibido: {value}).")
        quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if quantized <= Decimal("0"):
            raise NormalizationError(f"El monto redondeado a 2 decimales es 0 o negativo ({quantized}).")
        return float(quantized)

    def _parse_standard_decimal_amount(self, raw_amount: Any, field_name: str) -> float:
        if raw_amount is None or isinstance(raw_amount, bool):
            raise NormalizationError(f"Campo '{field_name}' nulo o inválido.")
        if isinstance(raw_amount, str):
            cleaned = raw_amount.strip()
            if not cleaned or "," in cleaned:
                raise NormalizationError(
                    f"Formato decimal inválido en '{field_name}': '{raw_amount}'."
                )
            try:
                dec_val = Decimal(cleaned)
            except InvalidOperation as exc:
                raise NormalizationError(
                    f"Valor no numérico en '{field_name}': '{raw_amount}'."
                ) from exc
        elif isinstance(raw_amount, (int, float)):
            try:
                dec_val = Decimal(str(raw_amount))
            except InvalidOperation as exc:
                raise NormalizationError(f"Valor numérico corrupto en '{field_name}'.") from exc
        else:
            raise NormalizationError(f"Tipo de dato no soportado en '{field_name}'.")

        return self._round_money(dec_val)

    def _parse_cents_amount(self, raw_total: Any, divisor: int, field_name: str = "total") -> float:
        if raw_total is None or isinstance(raw_total, bool) or not isinstance(raw_total, int):
            raise NormalizationError(
                f"El campo '{field_name}' de Fuente B debe ser un entero en centavos (recibido: {raw_total!r})."
            )
        dec_val = Decimal(raw_total) / Decimal(divisor)
        return self._round_money(dec_val)

    def _parse_european_amount_and_currency(
        self, raw_amount: Any, field_name: str = "amount"
    ) -> Tuple[str, float]:
        if not isinstance(raw_amount, str) or not raw_amount.strip():
            raise NormalizationError(f"Campo '{field_name}' de Fuente C vacío o no es cadena de texto.")

        text = raw_amount.strip()
        detected_currency: str | None = None
        numeric_part = text

        for symbol, iso_code in self.currency_symbols.items():
            if text.startswith(symbol):
                detected_currency = iso_code
                numeric_part = text[len(symbol):].strip()
                break
            if text.endswith(symbol):
                detected_currency = iso_code
                numeric_part = text[:-len(symbol)].strip()
                break

        if not detected_currency:
            raise NormalizationError(
                f"Símbolo de moneda no soportado o ausente en '{field_name}' (Fuente C): '{raw_amount}'."
            )

        if detected_currency not in self.supported_currencies:
            raise NormalizationError(f"Moneda '{detected_currency}' no está habilitada en reglas.")

        if not re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*(?:,\d+)?|-?\d+(?:,\d+)?", numeric_part):
            raise NormalizationError(
                f"Formato numérico europeo inválido en '{field_name}' (Fuente C): '{raw_amount}'."
            )

        normalized_num_str = numeric_part.replace(".", "").replace(",", ".")
        try:
            dec_val = Decimal(normalized_num_str)
        except InvalidOperation as exc:
            raise NormalizationError(
                f"No se pudo convertir el monto de Fuente C a decimal: '{raw_amount}'."
            ) from exc

        return detected_currency, self._round_money(dec_val)

    def _parse_currency_code(self, raw_currency: Any, field_name: str) -> str:
        if not isinstance(raw_currency, str) or not raw_currency.strip():
            raise NormalizationError(f"Campo '{field_name}' vacío o inválido.")
        code = raw_currency.strip().upper()
        if code not in self.supported_currencies:
            raise NormalizationError(
                f"Moneda no soportada '{code}' (permitidas: {sorted(self.supported_currencies)})."
            )
        return code

    @staticmethod
    def _parse_formatted_timestamp(raw_ts: Any, fmt: str, field_name: str) -> str:
        if not isinstance(raw_ts, str) or not raw_ts.strip():
            raise NormalizationError(f"Campo de fecha '{field_name}' vacío o inválido.")
        try:
            dt = datetime.strptime(raw_ts.strip(), fmt)
        except ValueError as exc:
            raise NormalizationError(
                f"Fecha corrupta o imposible en '{field_name}': '{raw_ts}' (esperado: {fmt})."
            ) from exc
        return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _parse_iso_timestamp(raw_ts: Any, field_name: str) -> str:
        if not isinstance(raw_ts, str) or not raw_ts.strip():
            raise NormalizationError(f"Campo de fecha '{field_name}' vacío o inválido.")
        cleaned = raw_ts.strip()
        if "T" not in cleaned:
            raise NormalizationError(
                f"Fecha '{raw_ts}' en '{field_name}' no cumple estándar ISO-8601 completo."
            )
        try:
            iso_compatible = cleaned.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_compatible)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
        except ValueError as exc:
            raise NormalizationError(
                f"Fecha ISO-8601 inválida o imposible en '{field_name}': '{raw_ts}'."
            ) from exc
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _parse_status(self, raw_status: Any, field_name: str) -> str:
        if not isinstance(raw_status, str) or not raw_status.strip():
            raise NormalizationError(f"Campo de estado '{field_name}' vacío o inválido.")
        key = raw_status.strip().lower()
        mapped = self.status_mapping.get(key)
        if not mapped or mapped not in self.allowed_statuses:
            raise NormalizationError(
                f"Estado desconocido '{raw_status}' en '{field_name}'."
            )
        return mapped
