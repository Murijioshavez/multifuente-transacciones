from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

import pandas as pd
import streamlit as st

from src.metrics import MetricsCalculator
from src.validator import TransactionPipeline

# Configuración base de rutas relativa al proyecto
BASE_DIR = Path(__file__).resolve().parent
RULES_PATH = BASE_DIR / "config" / "rules.json"
DEFAULT_DATA_PATH = BASE_DIR / "data" / "transactions_sample.json"

st.set_page_config(
    page_title="Normalizador de Transacciones Multifuente",
    page_icon="💳",
    layout="wide",
)


def load_raw_records(uploaded_file: Any) -> tuple[List[Any] | None, str]:
    """Carga el JSON subido por el usuario o el dataset de muestra por defecto."""
    if uploaded_file is not None:
        try:
            content = uploaded_file.getvalue().decode("utf-8")
            data = json.loads(content)
            return data, f"Archivo cargado: `{uploaded_file.name}`"
        except UnicodeDecodeError:
            st.error("Error de codificación: el archivo debe estar en UTF-8.")
            return None, ""
        except json.JSONDecodeError as exc:
            st.error(f"JSON malformado en el archivo subido (línea {exc.lineno}, columna {exc.colno}): {exc.msg}")
            return None, ""

    try:
        with DEFAULT_DATA_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data, f"Dataset por defecto: `{DEFAULT_DATA_PATH.name}`"
    except Exception as exc:
        st.error(f"No se pudo cargar el dataset por defecto: {exc}")
        return None, ""


def main() -> None:
    st.title("💳 Normalización y Exploración de Transacciones Multifuente")
    st.caption(
        "Ingestión desacoplada, detección automática de origen, validación de calidad y auditoría de cuarentena."
    )

    # --- Sidebar: Carga de archivo y filtros ---
    with st.sidebar:
        st.header("1. Origen de Datos")
        uploaded_file = st.file_uploader(
            "Subir archivo JSON de transacciones",
            type=["json"],
            help="Si no subes ningún archivo, se utilizará data/transactions_sample.json.",
        )

    raw_records, source_label = load_raw_records(uploaded_file)
    if raw_records is None:
        st.stop()

    st.info(source_label)

    # Ejecución del pipeline desacoplado en src/
    try:
        pipeline = TransactionPipeline(RULES_PATH)
        report = pipeline.process_records(raw_records)
        metrics = MetricsCalculator.compute(report)
    except ValueError as exc:
        st.error(f"Estructura de datos inválida: {exc}")
        st.stop()
    except Exception as exc:
        st.error(f"Error crítico inicializando el pipeline: {exc}")
        st.stop()

    # --- Panel Superior de KPIs ---
    st.subheader("Resumen Ejecutivo y Calidad de Datos")
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

    kpi1.metric("Total Procesadas", metrics["total_processed"])
    kpi2.metric(
        "Transacciones Válidas",
        f"{metrics['valid_count']} ({metrics['valid_percentage']}%)",
    )
    kpi3.metric(
        "Inválidas (Cuarentena)",
        f"{metrics['invalid_count']} ({metrics['invalid_percentage']}%)",
    )

    amounts_curr = metrics["amount_by_currency"]
    kpi4.metric("Total Válido USD", f"${amounts_curr.get('USD', 0.0):,.2f}")
    kpi5.metric("Total Válido EUR", f"€{amounts_curr.get('EUR', 0.0):,.2f}")

    # Mostrar monedas adicionales si existen (ej. GBP)
    extra_currencies = {
        k: v for k, v in amounts_curr.items() if k not in {"USD", "EUR"}
    }
    if extra_currencies:
        extra_str = " | ".join(f"{curr}: {val:,.2f}" for curr, val in extra_currencies.items())
        st.caption(f"Otras monedas válidas agregadas: **{extra_str}**")

    # --- Gráficos de Desglose por Estado y Fuente ---
    st.divider()
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("**Distribución por Estado (Válidas)**")
        status_df = pd.DataFrame(
            {
                "Estado": list(metrics["by_status"].keys()),
                "Cantidad": list(metrics["by_status"].values()),
            }
        ).set_index("Estado")
        st.bar_chart(status_df)

    with chart_col2:
        st.markdown("**Distribución por Fuente Detectada (Válidas)**")
        source_df = pd.DataFrame(
            {
                "Fuente": list(metrics["by_source"].keys()),
                "Cantidad": list(metrics["by_source"].values()),
            }
        ).set_index("Fuente")
        st.bar_chart(source_df)

    # --- Preparación de DataFrame de Válidas y Filtros Interactivos ---
    valid_dicts = report.valid_as_dicts()
    df_valid = pd.DataFrame(valid_dicts)

    with st.sidebar:
        st.divider()
        st.header("2. Filtros de Exploración")

        if not df_valid.empty:
            all_statuses = sorted(df_valid["status"].unique().tolist())
            selected_statuses = st.multiselect(
                "Estado",
                options=all_statuses,
                default=all_statuses,
            )

            all_currencies = sorted(df_valid["currency"].unique().tolist())
            selected_currencies = st.multiselect(
                "Moneda",
                options=all_currencies,
                default=all_currencies,
            )

            all_sources = sorted(df_valid["source"].unique().tolist())
            selected_sources = st.multiselect(
                "Fuente",
                options=all_sources,
                default=all_sources,
            )

            min_amt = float(df_valid["amount"].min())
            max_amt = float(df_valid["amount"].max())
            if min_amt < max_amt:
                amount_range = st.slider(
                    "Rango de Monto",
                    min_value=min_amt,
                    max_value=max_amt,
                    value=(min_amt, max_amt),
                )
            else:
                amount_range = (min_amt, max_amt)
                st.caption(f"Monto único disponible: {min_amt:.2f}")

            search_id = st.text_input(
                "Buscar por ID",
                placeholder="Ej. TX-1001, 204, A-77...",
            ).strip()
        else:
            selected_statuses = []
            selected_currencies = []
            selected_sources = []
            amount_range = (0.0, 0.0)
            search_id = ""

    # Aplicar filtros en tiempo real
    if not df_valid.empty:
        filtered_df = df_valid[
            (df_valid["status"].isin(selected_statuses))
            & (df_valid["currency"].isin(selected_currencies))
            & (df_valid["source"].isin(selected_sources))
            & (df_valid["amount"] >= amount_range[0])
            & (df_valid["amount"] <= amount_range[1])
        ]
        if search_id:
            filtered_df = filtered_df[
                filtered_df["id"].str.contains(search_id, case=False, na=False)
            ]
    else:
        filtered_df = df_valid

    # --- Pestañas: Explorador de Normalizadas vs Auditoría de Errores ---
    st.divider()
    tab_valid, tab_invalid = st.tabs(
        [
            f"✅ Transacciones Normalizadas ({len(filtered_df)})",
            f"🚨 Auditoría de Errores / Cuarentena ({metrics['invalid_count']})",
        ]
    )

    with tab_valid:
        if filtered_df.empty:
            st.warning("No hay transacciones válidas que coincidan con los filtros seleccionados.")
        else:
            st.dataframe(
                filtered_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": st.column_config.TextColumn("ID Unificado"),
                    "amount": st.column_config.NumberColumn("Monto", format="%.2f"),
                    "currency": st.column_config.TextColumn("Moneda (ISO)"),
                    "timestamp": st.column_config.TextColumn("Timestamp (UTC ISO-8601)"),
                    "status": st.column_config.TextColumn("Estado"),
                    "source": st.column_config.TextColumn("Fuente"),
                },
            )

        filtered_records_json = json.dumps(
            filtered_df.to_dict(orient="records") if not filtered_df.empty else [],
            indent=2,
            ensure_ascii=False,
        )
        st.download_button(
            label="⬇️ Descargar Transacciones Normalizadas (JSON)",
            data=filtered_records_json,
            file_name="normalized_transactions.json",
            mime="application/json",
        )

    with tab_invalid:
        invalid_dicts = report.invalid_as_dicts()
        if not invalid_dicts:
            st.success("¡Excelente! No se detectaron registros inválidos en este lote.")
        else:
            st.markdown(
                "Los siguientes registros fueron aislados sin detener el flujo principal. "
                "Se conserva el payload original junto con el diagnóstico exacto."
            )
            audit_rows = [
                {
                    "Índice JSON": item["index"],
                    "Fuente Detectada": item["detected_source"],
                    "Motivo del Rechazo": item["error_reason"],
                    "Registro Crudo Original": json.dumps(item["raw_record"], ensure_ascii=False),
                }
                for item in invalid_dicts
            ]
            st.dataframe(
                pd.DataFrame(audit_rows),
                use_container_width=True,
                hide_index=True,
            )

        invalid_records_json = json.dumps(
            invalid_dicts,
            indent=2,
            ensure_ascii=False,
        )
        st.download_button(
            label="⬇️ Descargar Reporte de Errores / Cuarentena (JSON)",
            data=invalid_records_json,
            file_name="invalid_transactions_report.json",
            mime="application/json",
        )


if __name__ == "__main__":
    main()
