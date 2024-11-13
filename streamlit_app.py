import pandas as pd 
import streamlit as st
import sqlite3
import numpy as np
from io import BytesIO
import unicodedata
import tempfile

# Configuración de la página
st.set_page_config(
    page_title="Comparador de Datos",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Funciones auxiliares
def remove_accents(input_str):
    """
    Elimina los acentos de una cadena de texto.
    """
    try:
        nfkd_form = unicodedata.normalize('NFKD', input_str)
        only_ascii = nfkd_form.encode('ASCII', 'ignore')
        return only_ascii.decode('ASCII')
    except Exception:
        return input_str

def normalize_value(value, trim_start=0, trim_end=0):
    """
    Normaliza un valor individual.
    """
    try:
        if pd.isna(value):
            return ''
        
        value_str = str(value)
        
        if trim_start > 0:
            value_str = value_str[trim_start:]
        if trim_end > 0:
            value_str = value_str[:-trim_end] if trim_end < len(value_str) else ''
        
        value_str = value_str.strip().lower()
        value_str = ' '.join(value_str.split())
        value_str = remove_accents(value_str)
        
        if isinstance(value, (float, np.float64, np.float32)):
            if value.is_integer():
                value_str = str(int(value))
        
        return value_str
    
    except Exception:
        return str(value).strip().lower()

def normalize_column(df, column_name, new_column_name=None, trim_start=0, trim_end=0):
    """Normaliza una columna específica y la añade como una nueva columna manteniendo el DataFrame original"""
    df_copy = df.copy()
    if new_column_name:
        df_copy[new_column_name] = df_copy[column_name].apply(lambda x: normalize_value(x, trim_start, trim_end))
    else:
        df_copy[column_name] = df_copy[column_name].apply(lambda x: normalize_value(x, trim_start, trim_end))
    return df_copy

def get_unique_records(df, column_name):
    """Obtiene registros únicos basados en una columna"""
    return df.drop_duplicates(subset=[column_name])

@st.cache_data
def load_data(uploaded_file, file_type, sheet_name=None):
    """Carga datos desde archivo subido"""
    try:
        if file_type == "CSV":
            return pd.read_csv(uploaded_file)
        elif file_type == "Excel":
            return pd.read_excel(uploaded_file, sheet_name=sheet_name)
    except Exception as e:
        st.error(f"Error al cargar el archivo: {e}")
        return None

@st.cache_data
def load_db_data(uploaded_file, query="SELECT * FROM ConsolidatedData;"):
    """Carga datos desde una base de datos SQLite subida"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite') as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name
        conn = sqlite3.connect(tmp_path)
        db_data = pd.read_sql(query, conn)
        conn.close()
        return db_data
    except Exception as e:
        st.error(f"Error al cargar la base de datos: {e}")
        return None

def apply_filters(df, table_name):
    """
    Aplica filtros interactivos a un DataFrame.
    """
    st.write(f"### Filtros para {table_name}")

    filter_columns = [col for col in df.columns if len(df[col].dropna().unique()) > 0 and len(df[col].dropna().unique()) <= 100]
    filter_keys = [f"filter_{table_name}_{col}" for col in filter_columns]

    for key in filter_keys:
        if key not in st.session_state:
            st.session_state[key] = []

    filters_applied = any(len(st.session_state[key]) > 0 for key in filter_keys)

    with st.expander(f"Aplicar filtros a {table_name}", expanded=filters_applied):
        for column, key in zip(filter_columns, filter_keys):
            selected_values = st.multiselect(
                f"Filtrar por {column}",
                options=sorted(df[column].dropna().unique()),
                default=st.session_state[key],
                key=key
            )

    filtered_df = df.copy()
    for column, key in zip(filter_columns, filter_keys):
        selected_values = st.session_state.get(key, [])
        if selected_values:
            filtered_df = filtered_df[filtered_df[column].astype(str).isin(selected_values)]

    st.write(f"**Total de registros después de filtrar:** {len(filtered_df)}")
    return filtered_df

def calculate_length_stats(series):
    """Calcula estadísticas de longitud para una serie de texto"""
    lengths = series.dropna().astype(str).apply(len)
    if lengths.empty:
        return {"min": 0, "max": 0, "mean": 0}
    return {
        "min": lengths.min(),
        "max": lengths.max(),
        "mean": round(lengths.mean(), 2)
    }

# Función principal
def main():
    st.title("📊 Comparador de Datos")
    st.markdown("""
    Esta aplicación permite comparar dos conjuntos de datos provenientes de archivos Excel/CSV o bases de datos SQLite.
    Selecciona las fuentes de datos, especifica las columnas a comparar y obtén coincidencias y no coincidencias de manera sencilla.
    """)

    # Uso de pestañas para separar las fuentes de datos
    tabs = st.tabs(["🔹 Fuente de Datos 1", "🔹 Fuente de Datos 2"])

    data_sources = {}
    for idx, tab in enumerate(tabs, start=1):
        with tab:
            st.header(f"Fuente de Datos {idx}")
            data_source = st.selectbox(
                f"Selecciona el tipo de fuente para el dataset {idx}:",
                ["Archivo Excel/CSV", "Base de Datos SQLite"],
                key=f'source{idx}_selectbox'
            )

            data = None
            selected_column = None
            additional_columns = []
            trim_options = {"enable": False, "trim_start": 0, "trim_end": 0}

            if data_source == "Archivo Excel/CSV":
                uploaded_file = st.file_uploader(
                    f"Sube el archivo Excel/CSV para el dataset {idx}:",
                    type=["csv", "xlsx", "xls"],
                    key=f'upload{idx}_file_uploader'
                )
                if uploaded_file is not None:
                    file_details = {"filename": uploaded_file.name, "filetype": uploaded_file.type, "filesize": uploaded_file.size}
                    st.success(f"Archivo cargado: {file_details['filename']}")

                    # Determinar el tipo de archivo
                    if uploaded_file.name.endswith(".csv"):
                        file_type = "CSV"
                        sheet_name = None
                    else:
                        file_type = "Excel"
                        # Leer las hojas disponibles
                        try:
                            excel = pd.ExcelFile(uploaded_file)
                            sheets = excel.sheet_names
                            sheet_name = st.selectbox(
                                f"Selecciona la hoja del archivo Excel para el dataset {idx}:",
                                sheets,
                                key=f'sheet{idx}_selectbox'
                            )
                        except Exception as e:
                            st.error(f"Error al leer las hojas del archivo Excel: {e}")
                            sheet_name = None

                    # Cargar datos y almacenarlos en session_state
                    if f'data{idx}' not in st.session_state or st.session_state[f'data{idx}_file_type'] != file_type or (file_type == "Excel" and st.session_state.get(f'data{idx}_sheet_name') != sheet_name):
                        data_loaded = load_data(uploaded_file, file_type, sheet_name=sheet_name)
                        st.session_state[f'data{idx}'] = data_loaded
                        st.session_state[f'data{idx}_file_type'] = file_type
                        st.session_state[f'data{idx}_sheet_name'] = sheet_name
                    data = st.session_state.get(f'data{idx}')

                    if data is not None:
                        st.success("Datos cargados exitosamente.")
                        st.dataframe(data.head(5), height=200)

                        selected_column = st.selectbox(
                            f"Selecciona la columna para comparar del dataset {idx}:",
                            data.columns,
                            key=f'col{idx}_selectbox'
                        )

                        additional_columns = st.multiselect(
                            f"Selecciona las columnas adicionales del dataset {idx} para incluir en el output:",
                            options=[col for col in data.columns if col != selected_column],
                            key=f'add_cols{idx}_multiselect'
                        )
            elif data_source == "Base de Datos SQLite":
                uploaded_db = st.file_uploader(
                    f"Sube la base de datos SQLite para el dataset {idx}:",
                    type=["sqlite", "db", "sqlite3"],
                    key=f'upload_db{idx}_file_uploader'
                )
                if uploaded_db is not None:
                    file_details = {"filename": uploaded_db.name, "filetype": uploaded_db.type, "filesize": uploaded_db.size}
                    st.success(f"Base de datos cargada: {file_details['filename']}")

                    # Leer la consulta SQL
                    query = st.text_area(
                        f"Consulta SQL para el dataset {idx} (opcional):",
                        "SELECT * FROM ConsolidatedData;",
                        key=f'query{idx}_input'
                    )

                    # Cargar datos y almacenarlos en session_state
                    if f'data{idx}' not in st.session_state or st.session_state[f'data{idx}_db_name'] != uploaded_db.name or st.session_state.get(f'data{idx}_query') != query:
                        data_loaded = load_db_data(uploaded_db, query)
                        st.session_state[f'data{idx}'] = data_loaded
                        st.session_state[f'data{idx}_db_name'] = uploaded_db.name
                        st.session_state[f'data{idx}_query'] = query
                    data = st.session_state.get(f'data{idx}')

                    if data is not None:
                        st.success("Base de datos cargada exitosamente.")
                        st.dataframe(data.head(5), height=200)

                        selected_column = st.selectbox(
                            f"Selecciona la columna para comparar del dataset {idx}:",
                            data.columns,
                            key=f'col{idx}_db_selectbox'
                        )

                        additional_columns = st.multiselect(
                            f"Selecciona las columnas adicionales del dataset {idx} para incluir en el output:",
                            options=[col for col in data.columns if col != selected_column],
                            key=f'add_cols{idx}_db_multiselect'
                        )
                elif uploaded_db is not None:
                    st.warning("Por favor, sube una base de datos válida.")

            # Opcional: Trimming
            if selected_column and data is not None:
                with st.expander(f"🔧 Opciones de limpieza para Fuente de Datos {idx}"):
                    trim_enable = st.checkbox(f"Habilitar ajuste de longitud para Fuente de Datos {idx}", key=f'trim_enable{idx}')
                    if trim_enable:
                        trim_start = st.number_input("Eliminar caracteres al inicio:", min_value=0, value=0, key=f'trim_start{idx}')
                        trim_end = st.number_input("Eliminar caracteres al final:", min_value=0, value=0, key=f'trim_end{idx}')
                        trim_options = {"enable": True, "trim_start": trim_start, "trim_end": trim_end}
                    else:
                        trim_options = {"enable": False, "trim_start": 0, "trim_end": 0}

            # Almacenar selecciones en session_state
            if selected_column:
                st.session_state[f'selected_column{idx}'] = selected_column
            if additional_columns:
                st.session_state[f'additional_columns{idx}'] = additional_columns
            if trim_options:
                st.session_state[f'trim_options{idx}'] = trim_options

            data_sources[idx] = {
                "data": data,
                "selected_column": selected_column,
                "additional_columns": additional_columns,
                "trim_options": trim_options
            }

    st.markdown("---")

    # Botón para iniciar la comparación
    if st.button("🔍 Comparar Datos"):
        if all([
            data_sources[1]["data"] is not None,
            data_sources[2]["data"] is not None,
            data_sources[1]["selected_column"],
            data_sources[2]["selected_column"]
        ]):
            data1 = data_sources[1]["data"]
            data2 = data_sources[2]["data"]
            selected_column1 = data_sources[1]["selected_column"]
            selected_column2 = data_sources[2]["selected_column"]
            additional_columns1 = data_sources[1]["additional_columns"]
            additional_columns2 = data_sources[2]["additional_columns"]
            trim_options1 = data_sources[1]["trim_options"]
            trim_options2 = data_sources[2]["trim_options"]

            with st.spinner("Comparando datos..."):
                # Mostrar ajustes aplicados
                adjustments = []
                if trim_options1["enable"]:
                    adjustments.append(f"Dataset 1: Eliminar {trim_options1['trim_start']} caracteres al inicio y {trim_options1['trim_end']} al final.")
                if trim_options2["enable"]:
                    adjustments.append(f"Dataset 2: Eliminar {trim_options2['trim_start']} caracteres al inicio y {trim_options2['trim_end']} al final.")
                if adjustments:
                    st.info("Ajustes aplicados:\n" + "\n".join(adjustments))

                # Normalizar las columnas seleccionadas
                normalized_data1 = normalize_column(
                    data1, 
                    selected_column1, 
                    new_column_name='normalized_key',
                    trim_start=trim_options1["trim_start"] if trim_options1["enable"] else 0,
                    trim_end=trim_options1["trim_end"] if trim_options1["enable"] else 0
                )
                normalized_data2 = normalize_column(
                    data2, 
                    selected_column2, 
                    new_column_name='normalized_key',
                    trim_start=trim_options2["trim_start"] if trim_options2["enable"] else 0,
                    trim_end=trim_options2["trim_end"] if trim_options2["enable"] else 0
                )

                # Seleccionar y renombrar columnas adicionales
                selected_cols1 = additional_columns1 if additional_columns1 else []
                selected_cols2 = additional_columns2 if additional_columns2 else []

                if selected_cols1:
                    selected_cols1_renamed = [f"{col}_dataset1" for col in selected_cols1]
                    merge_data1 = normalized_data1[['normalized_key'] + selected_cols1]
                    merge_data1.columns = ['normalized_key'] + selected_cols1_renamed
                else:
                    merge_data1 = normalized_data1[['normalized_key']]

                if selected_cols2:
                    selected_cols2_renamed = [f"{col}_dataset2" for col in selected_cols2]
                    merge_data2 = normalized_data2[['normalized_key'] + selected_cols2]
                    merge_data2.columns = ['normalized_key'] + selected_cols2_renamed
                else:
                    merge_data2 = normalized_data2[['normalized_key']]

                # Realizar la fusión para obtener coincidencias
                matches = pd.merge(
                    merge_data2,
                    merge_data1,
                    on='normalized_key',
                    how='inner'
                )

                # Identificar no coincidencias
                non_matches = merge_data2[~merge_data2['normalized_key'].isin(merge_data1['normalized_key'])].copy()

                # Agregar columnas adicionales del dataset 1 con valores NaN
                for col_renamed in selected_cols1_renamed if selected_cols1 else []:
                    non_matches[col_renamed] = np.nan

                # Ordenar las columnas
                columns_order = ['normalized_key'] + (selected_cols2_renamed if selected_cols2 else []) + (selected_cols1_renamed if selected_cols1 else [])
                non_matches = non_matches[columns_order]

                # Obtener registros únicos
                unique_matches = get_unique_records(matches, 'normalized_key')
                unique_non_matches = get_unique_records(non_matches, 'normalized_key')

                # Eliminar acentos en las columnas de salida
                for df_out in [unique_matches, unique_non_matches]:
                    for col in df_out.select_dtypes(include=['object']).columns:
                        df_out[col] = df_out[col].apply(remove_accents)

                # Convertir a cadenas de texto para evitar notación científica
                unique_matches = unique_matches.astype(str)
                unique_non_matches = unique_non_matches.astype(str)

                # Crear archivo Excel en memoria
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    unique_matches.to_excel(writer, sheet_name=f'Coincidencias_unicas_{len(unique_matches)}', index=False)
                    unique_non_matches.to_excel(writer, sheet_name=f'No_coincidencias_unicas_{len(unique_non_matches)}', index=False)
                processed_data = output.getvalue()

                # Almacenar resultados en session_state
                st.session_state['unique_matches'] = unique_matches
                st.session_state['unique_non_matches'] = unique_non_matches
                st.session_state['processed_data'] = processed_data

                # Guardar estadísticas
                st.session_state['statistics'] = {
                    "total_records": len(data2),
                    "total_unique": len(get_unique_records(data2, selected_column2)),
                    "unique_matches": len(unique_matches),
                    "unique_non_matches": len(unique_non_matches),
                    "duplicate_matches": len(matches) - len(unique_matches),
                    "duplicate_non_matches": len(non_matches) - len(unique_non_matches)
                }

                # Calcular estadísticas de longitud final
                final_length_stats1 = calculate_length_stats(unique_matches['normalized_key'])
                final_length_stats2 = calculate_length_stats(unique_non_matches['normalized_key'])
                st.session_state['final_length_stats1'] = final_length_stats1
                st.session_state['final_length_stats2'] = final_length_stats2

                st.success("Comparación completada y resultados almacenados.")

    # Mostrar resultados si están disponibles
    if all([
        'unique_matches' in st.session_state,
        'unique_non_matches' in st.session_state,
        'processed_data' in st.session_state,
        'statistics' in st.session_state
    ]):
        unique_matches = st.session_state['unique_matches']
        unique_non_matches = st.session_state['unique_non_matches']
        processed_data = st.session_state['processed_data']
        statistics = st.session_state['statistics']
        final_length_stats1 = st.session_state.get('final_length_stats1', {"min": 0, "max": 0, "mean": 0})
        final_length_stats2 = st.session_state.get('final_length_stats2', {"min": 0, "max": 0, "mean": 0})

        st.markdown("---")
        st.header("📈 Resultados de la Comparación")

        # Mostrar estadísticas principales
        st.subheader("🔢 Estadísticas de la Comparación")
        stats_col1, stats_col2, stats_col3, stats_col4 = st.columns(4)
        stats_col1.metric("Total de registros", statistics["total_records"])
        stats_col2.metric("Total únicos", statistics["total_unique"])
        stats_col3.metric("Coincidencias únicas", statistics["unique_matches"])
        stats_col4.metric("No coincidencias únicas", statistics["unique_non_matches"])

        # Sección de Coincidencias Únicas
        st.subheader("✅ Coincidencias Únicas")
        if not unique_matches.empty:
            filtered_matches = apply_filters(unique_matches, "Coincidencias_Unicas")
            st.dataframe(filtered_matches, height=300)
            st.info(f"Duplicados en coincidencias: {statistics['duplicate_matches']}")
            st.markdown("##### Estadísticas de longitud en Coincidencias únicas")
            st.write(f"**Mínima:** {final_length_stats1['min']} caracteres")
            st.write(f"**Máxima:** {final_length_stats1['max']} caracteres")
            st.write(f"**Promedio:** {final_length_stats1['mean']} caracteres")
        else:
            st.warning("No se encontraron coincidencias.")

        st.markdown("---")

        # Sección de No Coincidencias Únicas
        st.subheader("❌ No Coincidencias Únicas")
        if not unique_non_matches.empty:
            filtered_non_matches = apply_filters(unique_non_matches, "No_Coincidencias_Unicas")
            st.dataframe(filtered_non_matches, height=300)
            st.info(f"Duplicados en no coincidencias: {statistics['duplicate_non_matches']}")
            st.markdown("##### Estadísticas de longitud en No coincidencias únicas")
            st.write(f"**Mínima:** {final_length_stats2['min']} caracteres")
            st.write(f"**Máxima:** {final_length_stats2['max']} caracteres")
            st.write(f"**Promedio:** {final_length_stats2['mean']} caracteres")
        else:
            st.warning("No se encontraron registros sin coincidencias.")

        # Sección de Descargas
        st.markdown("---")
        st.subheader("📥 Descargar Resultados")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="Descargar Excel con Resultados",
                data=processed_data,
                file_name="Resultados_comparacion.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with col2:
            resumen = (
                f"**Resumen de la comparación**\n\n"
                f"**Fecha:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"**Total de registros:** {statistics['total_records']}\n"
                f"**Total registros únicos:** {statistics['total_unique']}\n"
                f"**Coincidencias únicas:** {statistics['unique_matches']}\n"
                f"**No coincidencias únicas:** {statistics['unique_non_matches']}\n"
                f"**Duplicados en coincidencias:** {statistics['duplicate_matches']}\n"
                f"**Duplicados en no coincidencias:** {statistics['duplicate_non_matches']}\n\n"
                f"**Estadísticas de longitud en Coincidencias únicas:**\n"
                f"- Mínima: {final_length_stats1['min']} caracteres\n"
                f"- Máxima: {final_length_stats1['max']} caracteres\n"
                f"- Promedio: {final_length_stats1['mean']} caracteres\n\n"
                f"**Estadísticas de longitud en No coincidencias únicas:**\n"
                f"- Mínima: {final_length_stats2['min']} caracteres\n"
                f"- Máxima: {final_length_stats2['max']} caracteres\n"
                f"- Promedio: {final_length_stats2['mean']} caracteres\n"
            )
            resumen_bytes = resumen.encode('utf-8')
            st.download_button(
                label="Descargar Resumen",
                data=resumen_bytes,
                file_name="Resumen_comparacion.txt",
                mime="text/plain",
            )

    # Mostrar ejemplos de registros recortados y normalizados antes de la comparación
    if not ('unique_matches' in st.session_state or 'unique_non_matches' in st.session_state):
        st.markdown("---")
        st.header("🔍 Ejemplos de Procesamiento de Datos")
        if data_sources.get(1, {}).get("selected_column") and data_sources.get(1, {}).get("data") is not None:
            st.subheader("📁 Fuente de Datos 1")
            with st.expander("Ver ejemplos de registros procesados"):
                if data_sources[1]["trim_options"]["enable"]:
                    sample_trimmed1 = data_sources[1]["data"][data_sources[1]["selected_column"]].dropna().astype(str).head(5).apply(
                        lambda x: x[data_sources[1]["trim_options"]["trim_start"]:] if data_sources[1]["trim_options"]["trim_start"] > 0 else x
                    ).apply(
                        lambda x: x[:-data_sources[1]["trim_options"]["trim_end"]] if data_sources[1]["trim_options"]["trim_end"] > 0 else x
                    )
                    sample_normalized1 = sample_trimmed1.apply(lambda x: normalize_value(x, data_sources[1]["trim_options"]["trim_start"], data_sources[1]["trim_options"]["trim_end"]))
                else:
                    sample_normalized1 = data_sources[1]["data"][data_sources[1]["selected_column"]].dropna().astype(str).head(5).apply(
                        lambda x: normalize_value(x)
                    )
                st.write("**Registros originales:**")
                st.write(data_sources[1]["data"][data_sources[1]["selected_column"]].dropna().astype(str).head(5))
                st.write("**Registros recortados y normalizados:**")
                st.write(sample_normalized1)

        if data_sources.get(2, {}).get("selected_column") and data_sources.get(2, {}).get("data") is not None:
            st.subheader("📁 Fuente de Datos 2")
            with st.expander("Ver ejemplos de registros procesados"):
                if data_sources[2]["trim_options"]["enable"]:
                    sample_trimmed2 = data_sources[2]["data"][data_sources[2]["selected_column"]].dropna().astype(str).head(5).apply(
                        lambda x: x[data_sources[2]["trim_options"]["trim_start"]:] if data_sources[2]["trim_options"]["trim_start"] > 0 else x
                    ).apply(
                        lambda x: x[:-data_sources[2]["trim_options"]["trim_end"]] if data_sources[2]["trim_options"]["trim_end"] > 0 else x
                    )
                    sample_normalized2 = sample_trimmed2.apply(lambda x: normalize_value(x, data_sources[2]["trim_options"]["trim_start"], data_sources[2]["trim_options"]["trim_end"]))
                else:
                    sample_normalized2 = data_sources[2]["data"][data_sources[2]["selected_column"]].dropna().astype(str).head(5).apply(
                        lambda x: normalize_value(x)
                    )
                st.write("**Registros originales:**")
                st.write(data_sources[2]["data"][data_sources[2]["selected_column"]].dropna().astype(str).head(5))
                st.write("**Registros recortados y normalizados:**")
                st.write(sample_normalized2)

    # Información de uso
    with st.expander("ℹ️ Información de uso"):
        st.markdown("""
        ### **Instrucciones de Uso**

        1. **Fuente de Datos 1 y 2**:
            - Selecciona el tipo de fuente de datos (Archivo Excel/CSV o Base de Datos SQLite).
            - **Si es un archivo**:
                - Sube el archivo utilizando el botón de carga.
                - Si es Excel, selecciona la hoja correspondiente.
                - Selecciona la columna que deseas comparar.
                - **Opcional**: Selecciona columnas adicionales para incluir en el resultado.
                - **Opcional**: Ajusta la longitud de los registros eliminando caracteres al inicio o al final.
            - **Si es una base de datos SQLite**:
                - Sube la base de datos utilizando el botón de carga.
                - **Opcional**: Ingresa una consulta SQL personalizada.
                - Selecciona la columna que deseas comparar.
                - **Opcional**: Selecciona columnas adicionales para incluir en el resultado.
                - **Opcional**: Ajusta la longitud de los registros eliminando caracteres al inicio o al final.

        2. **Comparación**:
            - Una vez seleccionadas ambas fuentes de datos y configuradas las opciones deseadas, haz clic en el botón **"Comparar Datos"**.
            - La aplicación procesará los datos y mostrará las coincidencias y no coincidencias.

        3. **Resultados**:
            - Revisa las tablas de coincidencias y no coincidencias.
            - Utiliza los filtros interactivos para explorar los datos.
            - Consulta las estadísticas de longitud para asegurar que los ajustes se han aplicado correctamente.

        4. **Descargas**:
            - Descarga el archivo Excel con los resultados completos.
            - Descarga un resumen de la comparación en formato de texto.

        ### **Consejos**
        - Asegúrate de que los archivos subidos sean válidos y correspondan al tipo seleccionado.
        - Las columnas seleccionadas para la comparación deben contener datos relevantes y compatibles.
        - Utiliza las opciones de trimming para mejorar la precisión de la comparación eliminando espacios o caracteres innecesarios.
        """)

if __name__ == "__main__":
    main()
