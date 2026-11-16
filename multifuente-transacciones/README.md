# Nota Técnica: Normalización y Exploración de Transacciones Multifuente

## 1. Objetivo y Arquitectura Desacoplada
Diseñé este sistema para ingestar, unificar y auditar registros financieros provenientes de tres proveedores heterogéneos (`SOURCE_A`, `SOURCE_B` y `SOURCE_C`) hacia un modelo canónico único. Para garantizar mantenibilidad y separación de responsabilidades, dividí la solución en dos capas independientes:
* **Núcleo de dominio (`src/`):** Contiene los modelos inmutables (`models.py`), la detección automática de fuentes y transformaciones (`normalizer.py`), el pipeline de validación y cuarentena (`validator.py`) y el motor de agregaciones (`metrics.py`).
* **Capa de presentación (`app.py`):** Interfaz interactiva en Streamlit desacoplada de las reglas de negocio, dedicada exclusivamente a la carga de archivos, filtrado en memoria, visualización de KPIs y exportación de reportes JSON.
* **Reglas externalizadas (`config/rules.json`):** Permite actualizar equivalencias de estados, símbolos monetarios y formatos de fecha sin modificar el código fuente.

## 2. Decisiones Técnicas y Manejo de Casos Borde
1. **Esquema Canónico Estricto:** Estandaricé todas las salidas válidas a `{id, amount, currency, timestamp, status, source}` con montos `float` positivos redondeados a 2 decimales, divisas ISO-4217 en mayúsculas y marcas de tiempo normalizadas a UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`).
2. **Aritmética Exacta para Centavos (`SOURCE_B`):** Exijo que `total` sea un entero estricto (descartando booleanos o decimales) y realizo la división entre `100` mediante `decimal.Decimal` antes de convertir a `float` con redondeo `ROUND_HALF_UP`, eliminando errores de punto flotante binario.
3. **Extracción de Símbolo y Formato Europeo (`SOURCE_C`):** Separo el prefijo/sufijo monetario (`€`, `$`, `£`) mediante expresiones regulares validadas contra `rules.json`, eliminando separadores de miles (`.`) y transformando la coma decimal (`,`) en punto decimal.
4. **Política de Cuarentena No Destructiva:** Ningún registro corrupto detiene el proceso ni se descarta en silencio. Todo fallo (montos `<= 0`, fechas imposibles como `30/02/2025`, monedas no soportadas o esquemas desconocidos) se encapsula en `invalid_transactions` preservando el payload original y el motivo exacto (`error_reason`).

## 3. Instrucciones de Ejecución
```bash
# 1. Instalar dependencias mínimas
pip install -r requirements.txt

# 2. Ejecutar la aplicación web interactiva
streamlit run app.py
```

## 4. Uso Estratégico de IA y Ajustes Críticos Realizados
Utilicé un asistente de IA como par técnico para acelerar el esqueleto inicial de las clases y los componentes visuales de Streamlit. Sin embargo, tras auditar el código generado contra los criterios de calidad y casos borde, realicé cuatro correcciones fundamentales:
1. **Eliminación de lógica acoplada en la vista:** La propuesta inicial de la IA mezclaba el parsing de JSON y el cálculo de métricas dentro de `app.py`; extraje toda esa lógica hacia `src/validator.py` y `src/metrics.py` para permitir pruebas unitarias independientes.
2. **Sustitución de `float` directo por `Decimal`:** La IA dividía `total / 100` directamente en punto flotante, lo que introducía imprecisiones en sumatorias agregadas; reescribí el cálculo monetario con `decimal.Decimal` y `ROUND_HALF_UP`.
3. **Bloqueo de booleanos como enteros en Python:** En Python `isinstance(True, int)` evalúa a `True`. Añadí comprobaciones explícitas `not isinstance(val, bool)` en `normalizer.py` para evitar que un campo booleano corrupto en `SOURCE_B` se convirtiera en `$0.01`.
4. **Estabilización de controles dinámicos en Streamlit:** Cuando un archivo subido contiene una sola transacción válida (`min == max`), `st.slider` lanza una excepción en tiempo de ejecución; incorporé una guarda condicional en `app.py` para degradar con gracia cuando no existe rango numérico.
