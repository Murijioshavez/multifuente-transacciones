# Nota Técnica: Normalización y Exploración de Transacciones Multifuente

## 1. ¿De qué trata el proyecto y cómo lo organicé?

La idea de este proyecto es trabajar con transacciones que vienen de tres fuentes diferentes (`SOURCE_A`, `SOURCE_B` y `SOURCE_C`). Como cada una maneja sus datos a su manera, lo que hice fue crear un sistema que los recibe, identifica de dónde vienen y los convierte a un mismo formato. Así es mucho más fácil trabajar con ellos y analizarlos después.

Para no tener todo el código amontonado en un solo archivo, decidí dividirlo según lo que hace cada parte:

- **Carpeta `src/`:** Aquí está lo que hace funcionar al sistema. Se encarga de reconocer las fuentes, transformar los datos, revisar que estén correctos y calcular las estadísticas.
- **Archivo `app.py`:** Es la interfaz que se abre con Streamlit. Desde aquí se pueden subir archivos, aplicar filtros, ver los resultados y descargar los reportes. La idea es que la interfaz se encargue de mostrar la información, no de procesarla.
- **Archivo `config/rules.json`:** Aquí guardé las reglas que utiliza el sistema para reconocer monedas, estados y formatos de fecha. Esto permite cambiar ciertas configuraciones sin tener que meterse a modificar el código.

## 2. Decisiones que tomé durante el desarrollo

Mientras desarrollaba el proyecto, me encontré con algunos detalles que había que tomar en cuenta para evitar errores al procesar los datos. Estas fueron las decisiones más importantes:

1. **Unificar el formato de las transacciones:** Como cada fuente tiene una estructura diferente, decidí que todas las transacciones válidas terminaran con los mismos campos: `id`, `amount`, `currency`, `timestamp`, `status` y `source`. También establecí que los montos fueran positivos y tuvieran dos decimales, que las monedas utilizaran su código correspondiente y que todas las fechas se convirtieran a UTC. De esta forma, después de normalizar los datos, ya no importa de qué fuente venían porque todos tienen la misma estructura.

2. **Convertir correctamente los centavos de SOURCE_B:** En esta fuente los montos vienen en centavos. Por ejemplo, si recibo `12550`, realmente significa `$125.50`. Para hacer esa conversión utilicé `Decimal`, porque trabajar directamente con `float` puede provocar pequeñas diferencias en los resultados cuando se manejan decimales. También agregué una validación para evitar que Python acepte valores como `True` como si fueran números enteros.

3. **Procesar los símbolos de moneda de SOURCE_C:** Esta fuente presenta los montos de una forma diferente, por ejemplo: `€45,90`. Para resolverlo, primero identifico el símbolo de la moneda y después convierto el número al formato que utiliza el sistema. También tengo en cuenta los separadores de miles para evitar que una cantidad se interprete incorrectamente.

4. **¿Qué pasa cuando un registro viene mal?** No quería que un solo dato incorrecto hiciera que todo el proceso fallara. Por eso implementé una cuarentena donde se guardan los registros que no cumplen con las reglas. Por ejemplo, si llega un monto negativo, una fecha imposible o una moneda que el sistema no reconoce, el registro se marca como inválido y se guarda junto con sus datos originales y la razón del error. Así puedo revisar qué pasó sin perder la información.

## 3. ¿Cómo ejecutar el proyecto?

Primero hay que instalar las dependencias desde la terminal:

```bash
pip install -r requirements.txt
```

Después, desde la carpeta principal del proyecto, se ejecuta:

```bash
streamlit run app.py
```

Con eso se abre la aplicación en el navegador. Al entrar, se puede trabajar con el archivo de ejemplo que incluye el proyecto o subir un JSON propio. Después de procesarlo, se pueden consultar las estadísticas, filtrar las transacciones y descargar los resultados.

## 4. ¿Cómo utilicé la IA y qué tuve que corregir?

Durante el desarrollo utilicé IA como apoyo para avanzar más rápido, principalmente para crear la estructura inicial del proyecto y algunos elementos de la interfaz en Streamlit. Sin embargo, no me limité a copiar lo que generaba. Fui revisando el código y encontré algunas cosas que necesitaban corregirse o mejorarse.

Estos fueron algunos de los cambios que hice:

1. **Separé mejor el código:** Al principio había demasiadas operaciones dentro de `app.py`, incluso cosas como procesar los JSON y calcular las estadísticas. Decidí mover esas funciones a los archivos correspondientes para que cada parte del proyecto tuviera una responsabilidad más clara.
2. **Corregí el manejo de los decimales:** La primera propuesta utilizaba `float` directamente para convertir los centavos de `SOURCE_B`. Lo cambié por `Decimal` y `ROUND_HALF_UP`, ya que es una opción más adecuada cuando se trabaja con cantidades de dinero.
3. **Evité que los booleanos se aceptaran como números:** Encontré un detalle de Python que podía causar problemas: `True` puede ser interpretado como un número entero. Por eso agregué una validación adicional para evitar que un valor de ese tipo pasara como una cantidad válida.
4. **Solucioné un problema con los filtros:** También tuve que contemplar un caso en Streamlit donde el filtro `st.slider` podía fallar si solo había una transacción válida, porque el valor mínimo y máximo terminaban siendo iguales. Agregué una condición para que la aplicación pudiera manejar ese escenario sin detenerse.
En general, la IA me ayudó a avanzar con la estructura y algunas partes del código, pero fue necesario revisar sus propuestas, entender cómo funcionaban y hacer los cambios necesarios para que el proyecto cumpliera con lo que se pedía.