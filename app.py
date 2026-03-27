import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from jinja2 import Template
from weasyprint import HTML
import io
from datetime import datetime

st.set_page_config(page_title="Cotizador Terret 2026", page_icon="📄", layout="wide")

# ====================== CONEXIONES ======================
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_resource
def get_drive_service():
    creds_dict = st.secrets["connections"]["gsheets"]
    scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
    ]
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=scopes
    )
    return build("drive", "v3", credentials=creds)

drive_service = get_drive_service()
ROOT_FOLDER_ID = st.secrets["drive"]["folder_id"]  # Carpeta raíz "Cotizaciones"

# ====================== GESTIÓN DE CARPETAS EN DRIVE ======================
def obtener_o_crear_carpeta(nombre, parent_id):
    """Busca una carpeta por nombre dentro de parent_id. Si no existe, la crea."""
    nombre_escapado = nombre.replace("'", "\\'")
    query = (
        f"name='{nombre_escapado}' "
        f"and '{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    results = drive_service.files().list(
        q=query,
        fields="files(id, name)",
        spaces="drive"
    ).execute()
    archivos = results.get("files", [])
    if archivos:
        return archivos[0]["id"]
    # No existe → crear
    metadata = {
        "name": nombre,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    carpeta = drive_service.files().create(body=metadata, fields="id").execute()
    return carpeta["id"]

def obtener_carpeta_destino(anio, tipo, cliente):
    """Estructura: Cotizaciones / 2026 / Eventos / NOMBRE_CLIENTE"""
    id_anio    = obtener_o_crear_carpeta(str(anio), ROOT_FOLDER_ID)
    id_tipo    = obtener_o_crear_carpeta(tipo,       id_anio)
    id_cliente = obtener_o_crear_carpeta(cliente,    id_tipo)
    return id_cliente

# ====================== LISTAR CLIENTES EXISTENTES DESDE DRIVE ======================
@st.cache_data(ttl=60)
def listar_clientes_en_drive(anio, tipo):
    """Lista las subcarpetas de Cotizaciones/Año/Tipo para mostrar clientes ya creados."""
    try:
        id_anio = obtener_o_crear_carpeta(str(anio), ROOT_FOLDER_ID)
        id_tipo = obtener_o_crear_carpeta(tipo, id_anio)
        query = (
            f"'{id_tipo}' in parents "
            f"and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        results = drive_service.files().list(
            q=query,
            fields="files(name)",
            orderBy="name"
        ).execute()
        return [f["name"] for f in results.get("files", [])]
    except Exception:
        return []

# ====================== CARGAR PRODUCTOS ======================
@st.cache_data(ttl=300)
def cargar_productos():
    df = conn.read(worksheet="Productos")
    df = df.dropna(how="all")
    price_cols = ['precio_1','precio_5','precio_10','precio_20','precio_30',
                  'precio_50','precio_100','precio_200','precio_500',
                  'precio_1000','precio_3000']
    df[price_cols] = df[price_cols].apply(pd.to_numeric, errors='coerce')
    return df

productos_df = cargar_productos()

# ====================== PRECIO SEGÚN ESCALA ======================
def obtener_precio(row, cantidad):
    thresholds = [1, 5, 10, 20, 30, 50, 100, 200, 500, 1000, 3000]
    cols = ['precio_1','precio_5','precio_10','precio_20','precio_30',
            'precio_50','precio_100','precio_200','precio_500',
            'precio_1000','precio_3000']
    for i, thresh in enumerate(thresholds):
        if cantidad < thresh:
            for j in range(i-1, -1, -1):
                val = row[cols[j]]
                if pd.notna(val):
                    return float(val)
            for val in row[cols]:
                if pd.notna(val):
                    return float(val)
            return 0.0
    for j in range(len(cols)-1, -1, -1):
        val = row[cols[j]]
        if pd.notna(val):
            return float(val)
    return 0.0

# ====================== NÚMERO CONSECUTIVO ======================
def obtener_siguiente_numero():
    df_config = conn.read(worksheet="Config", ttl=0, header=None)
    df_config = df_config.dropna(how="all")
    try:
        num = int(float(str(df_config.iloc[0, 1]).strip()))
    except (ValueError, IndexError, TypeError) as e:
        st.error(f"Error leyendo Config: {e}. La celda B1 debe contener el numero consecutivo.")
        st.stop()
    df_updated = pd.DataFrame([[df_config.iloc[0, 0], num + 1]])
    conn.update(worksheet="Config", data=df_updated)
    return num

# ====================== PLANTILLA HTML ======================
html_template = Template("""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
    @page { margin: 0; size: A4 portrait; }
    body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.4; color: #222; }
    .header { text-align: right; font-size: 11px; }
    .titulo { text-align: center; font-size: 22px; font-weight: bold; margin: 40px 0 20px; }
    table { width: 100%; border-collapse: collapse; margin: 15px 0; }
    th, td { border: 1px solid #000; padding: 9px; text-align: left; }
    th { background: #f0f0f0; }
    .footer { position: fixed; bottom: 30px; left: 40px; right: 40px; font-size: 9px; text-align: center; border-top: 1px solid #000; padding-top: 8px; }
    .page-break { page-break-before: always; }
</style></head>
<body>

<div class="header">Envigado, Colombia<br><strong>{{ fecha }}</strong></div>
<h1 style="text-align:center; margin-top:90px;">Cotización</h1>
<h2 style="text-align:center;">{{ cliente }}</h2>
<p style="text-align:justify; margin-top:60px; font-size:12px;">
En Terret, el proceso de Custom representa la máxima expresión de personalización y pasión...
</p>
<div class="footer">www.terret.co • CI. 46A Sur #4881, Zona 1, Envigado, Antioquia, Colombia • @terretsports • info@terret.co</div>

<div class="page-break">
    <h2 class="titulo">PORTAFOLIO CAMISETAS 2026</h2>
    <p style="text-align:center;">LÍNEA BOSTON • LÍNEA CHICAGO • ESPECIFICACIONES DE TELA</p>
</div>

<div class="page-break">
    <h2 class="titulo">{{ titulo_propuesta }}</h2>
    {{ html_tablas | safe }}
    <p style="text-align:center; font-size:18px; margin-top:30px;">
        <strong>TOTAL GENERAL: ${{ total_general_formatted }}</strong>
    </p>
</div>

<div class="page-break">
    <h2 class="titulo">PROPUESTA COMERCIAL MERCH, POR CONVENIO ANUAL</h2>
    <p style="text-align:center;">(Tabla de convenio anual - puedes mejorarla después)</p>
</div>

<div class="page-break">
    <h2 class="titulo">BENEFICIOS EXTRAS</h2>
    <ul style="font-size:12px;">
        <li>Terret otorgará código de descuento del 20% para todos los inscritos</li>
        <li>Visualización en redes sociales de TERRET (40.200 seguidores)</li>
        <li>Diseño del Merch oficial con utilidad mínima del 35%</li>
        <li>Banner en página web de TERRET (+25.000 sesiones mensuales)</li>
    </ul>
</div>

<div class="page-break">
    <h2 class="titulo">Términos y Condiciones del proceso Alianza de Eventos</h2>
    <p style="font-size:11px; text-align:justify;">
        Opciones de Diseño • Insumos de tu parte • Tiempo de Producción 30 días hábiles • Ficha Técnica • Pagos 50% anticipo • Costos de envío no incluidos.
    </p>
    <p style="margin-top:120px; text-align:center;">FIRMA CLIENTE ___________________<br>JUAN FELIPE GÓMEZ – DIRECTOR DE MARCA – TERRET SAS</p>
    <div class="footer">www.terret.co • CI. 46A Sur #4881, Zona 1, Envigado, Antioquia, Colombia • @terretsports • info@terret.co</div>
</div>

</body>
</html>
""")

# ====================== SESSION STATE ======================
if "productos_cotizacion" not in st.session_state:
    st.session_state.productos_cotizacion = []

# ====================== INTERFAZ ======================
st.title("📄 Cotizador Terret 2026")

# --- Tipo, Año y Fecha ---
col_tipo, col_anio, col_fecha = st.columns([2, 1, 2])
with col_tipo:
    tipo_propuesta = st.selectbox(
        "Tipo de propuesta",
        ["Eventos", "Custom"],
        help="Define en qué carpeta de Drive se guardará la cotización"
    )
with col_anio:
    anio = st.number_input("Año", min_value=2024, max_value=2030,
                           value=datetime.today().year, step=1)
with col_fecha:
    fecha = st.date_input("Fecha de cotización", datetime.today())

st.divider()

# --- Selector de cliente ---
st.subheader("👤 Cliente")

clientes_existentes = listar_clientes_en_drive(anio, tipo_propuesta)
opciones_cliente = ["➕ Nuevo cliente"] + clientes_existentes

col_sel, col_nuevo = st.columns([2, 3])
with col_sel:
    seleccion = st.selectbox(
        f"Clientes en {tipo_propuesta} / {anio}",
        opciones_cliente,
        help="Clientes con cotizaciones previas en esta categoría"
    )

if seleccion == "➕ Nuevo cliente":
    with col_nuevo:
        cliente = st.text_input("Nombre del nuevo cliente / Evento", "").strip().upper()
    if not cliente:
        st.warning("✏️ Escribe el nombre del cliente para continuar.")
        cliente = ""
else:
    cliente = seleccion
    with col_nuevo:
        st.info(f"📁 Se guardará en la carpeta existente: **{cliente}**")

st.divider()

# --- Título propuesta ---
titulos_map = {
    "Eventos": ["PROPUESTA COMERCIAL EVENTO", "PROPUESTA COMERCIAL MERCH", "PROPUESTA COMERCIAL KIT"],
    "Custom":  ["PROPUESTA COMERCIAL CUSTOM", "PROPUESTA COMERCIAL CAMISETAS"],
}
titulos_disponibles = titulos_map.get(tipo_propuesta, []) + ["Personalizado..."]
titulo_propuesta = st.selectbox("Título de la propuesta comercial", titulos_disponibles)
if titulo_propuesta == "Personalizado...":
    titulo_propuesta = st.text_input("Escribe el título personalizado")

st.divider()

# --- Agregar productos ---
st.subheader("🛍️ Productos")

col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    producto_sel = st.selectbox("Producto", productos_df["nombre_producto"].tolist())
with col2:
    cantidad = st.number_input("Cantidad", min_value=1, value=1)
with col3:
    st.write("")
    st.write("")
    if st.button("➕ Agregar", use_container_width=True):
        row = productos_df[productos_df["nombre_producto"] == producto_sel].iloc[0]
        precio = obtener_precio(row, cantidad)
        st.session_state.productos_cotizacion.append({
            "referencia": str(row.get("referencia", "")),
            "nombre": str(row["nombre_producto"]),
            "cantidad": cantidad,
            "precio_unitario": precio,
            "total_linea": cantidad * precio
        })
        st.success(f"✅ {producto_sel} agregado")

# --- Tabla de productos ---
total_general = 0.0
if st.session_state.productos_cotizacion:
    df_items = pd.DataFrame(st.session_state.productos_cotizacion)

    col_tabla, col_acciones = st.columns([5, 1])
    with col_tabla:
        st.dataframe(
            df_items[["referencia", "nombre", "cantidad", "precio_unitario", "total_linea"]],
            use_container_width=True
        )
    with col_acciones:
        st.write("Eliminar")
        for i in range(len(st.session_state.productos_cotizacion)):
            if st.button("🗑️", key=f"del_{i}"):
                st.session_state.productos_cotizacion.pop(i)
                st.rerun()

    total_general = float(df_items["total_linea"].sum())
    col_total, col_limpiar = st.columns([3, 1])
    with col_total:
        st.metric("TOTAL GENERAL (antes de IVA)", f"${total_general:,.0f}")
    with col_limpiar:
        st.write("")
        if st.button("🗑️ Limpiar todo", type="secondary", use_container_width=True):
            st.session_state.productos_cotizacion = []
            st.rerun()

st.divider()

# ====================== GENERAR PDF ======================
puede_generar = bool(st.session_state.productos_cotizacion) and bool(cliente)
if not puede_generar:
    st.info("Agrega al menos un producto y selecciona/escribe un cliente para generar la cotización.")

if st.button("🚀 Generar y Guardar PDF", type="primary", disabled=not puede_generar):
    with st.status("Generando cotización...", expanded=True) as status:

        st.write("📄 Construyendo PDF...")
        numero = obtener_siguiente_numero()

        tablas_html = ""
        for item in st.session_state.productos_cotizacion:
            subtotal = item["total_linea"]
            iva = subtotal * 0.19
            total_con_iva = subtotal + iva
            tablas_html += f"""
            <table>
                <tr><th>Referencia</th><th>Producto</th><th>Cantidad</th><th>Valor unitario</th><th>TOTAL</th></tr>
                <tr>
                    <td>{item['referencia']}</td><td>{item['nombre']}</td>
                    <td>{item['cantidad']}</td>
                    <td>${item['precio_unitario']:,.0f}</td>
                    <td>${subtotal:,.0f}</td>
                </tr>
                <tr><td colspan="4" style="text-align:right;">SUBTOTAL</td><td>${subtotal:,.0f}</td></tr>
                <tr><td colspan="4" style="text-align:right;">IVA 19%</td><td>${iva:,.0f}</td></tr>
                <tr><td colspan="4" style="text-align:right;"><strong>TOTAL</strong></td>
                    <td><strong>${total_con_iva:,.0f}</strong></td></tr>
            </table><br>
            """

        html_final = html_template.render(
            fecha=fecha.strftime("%d de %B del %Y").upper(),
            cliente=cliente.upper(),
            titulo_propuesta=titulo_propuesta,
            html_tablas=tablas_html,
            total_general_formatted=f"{total_general:,.0f}"
        )
        pdf_bytes = HTML(string=html_final).write_pdf()

        st.write(f"📁 Creando estructura: Cotizaciones / {anio} / {tipo_propuesta} / {cliente} ...")
        try:
            carpeta_destino_id = obtener_carpeta_destino(anio, tipo_propuesta, cliente)
        except Exception as e:
            st.error(f"❌ Error creando carpeta en Drive: {e}")
            st.stop()

        st.write("☁️ Subiendo PDF a Drive...")
        filename = f"Cotizacion_{numero:04d}_{cliente.replace(' ', '_')}.pdf"
        try:
            file_metadata = {"name": filename, "parents": [carpeta_destino_id]}
            media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype="application/pdf")
            drive_service.files().create(
                body=file_metadata, media_body=media, fields="id"
            ).execute()
        except Exception as e:
            st.error(f"❌ Error subiendo a Drive: {e}")
            st.stop()

        status.update(
            label=f"✅ Cotización #{numero:04d} guardada correctamente",
            state="complete"
        )

    st.success(f"📂 Ruta en Drive: Cotizaciones / {anio} / {tipo_propuesta} / {cliente} / {filename}")
    st.balloons()

    st.download_button(
        "📥 Descargar PDF",
        data=pdf_bytes,
        file_name=filename,
        mime="application/pdf"
    )

    st.session_state.productos_cotizacion = []
