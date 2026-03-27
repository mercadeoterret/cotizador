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
    creds_dict = st.secrets["connections"]["gsheets"]   # ← usa exactamente tu secrets.toml
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    return build('drive', 'v3', credentials=creds)

drive_service = get_drive_service()
FOLDER_ID = st.secrets["drive"]["folder_id"]

# ====================== CARGAR PRODUCTOS ======================
@st.cache_data(ttl=300)
def cargar_productos():
    df = conn.read(worksheet="Productos")
    return df.dropna(how="all")

productos_df = cargar_productos()

# ====================== PRECIO SEGÚN ESCALA (PORTALOFIO 2026) ======================
def obtener_precio(row, cantidad):
    thresholds = [1, 5, 10, 20, 30, 50, 100, 200, 500, 1000, 3000]
    cols = ['precio_1','precio_5','precio_10','precio_20','precio_30',
            'precio_50','precio_100','precio_200','precio_500','precio_1000','precio_3000']
    
    for i, thresh in enumerate(thresholds):
        if cantidad < thresh:
            return float(row[cols[i-1]] if i > 0 else row['precio_1'])
    return float(row['precio_3000'])  # para 3000 o más

# ====================== NÚMERO CONSECUTIVO ======================
def obtener_siguiente_numero():
    df_config = conn.read(worksheet="Config")
    num = int(df_config.iloc[0, 1])  # columna B
    conn.update(worksheet="Config", data=pd.DataFrame([[num + 1]]), range="B1")
    return num

# ====================== PLANTILLA HTML 6 PÁGINAS ======================
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

<!-- PÁGINA 1 - PORTADA -->
<div class="header">Envigado, Colombia<br><strong>{{ fecha }}</strong></div>
<h1 style="text-align:center; margin-top:90px;">Cotización</h1>
<h2 style="text-align:center;">{{ cliente }}</h2>
<p style="text-align:justify; margin-top:60px; font-size:12px;">
En Terret, el proceso de Custom representa la máxima expresión de personalización y pasión en ofrecer productos con un enfoque específico, con alto valor agregado en desarrollo y diseño. Ofrecemos a nuestros clientes la oportunidad de participar activamente en la creación de prendas únicas, desde el diseño inicial hasta la entrega final del producto. Nos comprometemos a acompañar el crecimiento y a brindarles la oportunidad de expresar su individualidad a través de prendas hechas a medida que reflejen su esencia y pasión.
</p>
<div class="footer">www.terret.co • CI. 46A Sur #4881, Zona 1, Envigado, Antioquia, Colombia • @terretsports • info@terret.co</div>

<!-- PÁGINA 2 - PORTAFOLIO -->
<div class="page-break">
    <h2 class="titulo">PORTAFOLIO CAMISETAS 2026</h2>
    <p style="text-align:center;">LÍNEA BOSTON • LÍNEA CHICAGO • ESPECIFICACIONES DE TELA</p>
    <!-- Agrega aquí tus imágenes cuando quieras -->
</div>

<!-- PÁGINA 3 - PROPUESTA COMERCIAL DINÁMICA -->
<div class="page-break">
    <h2 class="titulo">{{ titulo_propuesta }}</h2>
    {{ html_tablas | safe }}
    <p style="text-align:center; font-size:18px; margin-top:30px;">
        <strong>TOTAL GENERAL: ${{ total_general | format_number }}</strong>
    </p>
</div>

<!-- PÁGINA 4 - MERCH CONVENIO ANUAL -->
<div class="page-break">
    <h2 class="titulo">PROPUESTA COMERCIAL MERCH, POR CONVENIO ANUAL</h2>
    <p style="text-align:center;">(Puedes copiar aquí la tabla de tu Canva por ahora)</p>
</div>

<!-- PÁGINA 5 - BENEFICIOS -->
<div class="page-break">
    <h2 class="titulo">BENEFICIOS EXTRAS</h2>
    <ul style="font-size:12px;">
        <li>Terret otorgará código de descuento para todos los inscritos a la carrera, personalizado con un descuento del 20%</li>
        <li>Visualización en las redes sociales de TERRET (40.200 seguidores) y promoción por embajadores</li>
        <li>Diseño del Merch oficial de la carrera con precios especiales y utilidad mínima del 35%</li>
        <li>Banner en página web de TERRET (+25.000 sesiones mensuales)</li>
    </ul>
</div>

<!-- PÁGINA 6 - TÉRMINOS -->
<div class="page-break">
    <h2 class="titulo">Términos y Condiciones del proceso Alianza de Eventos</h2>
    <p style="font-size:11px; text-align:justify;">
        Opciones de Diseño • Insumos de tu parte • Tiempo de Producción 30 días hábiles • Ficha Técnica y Aceptación • Pagos 50% anticipo • Costos de envío no incluidos.
    </p>
    <p style="margin-top:120px; text-align:center;">FIRMA CLIENTE ___________________<br>JUAN FELIPE GÓMEZ – DIRECTOR DE MARCA – TERRET SAS</p>
    <div class="footer">www.terret.co • CI. 46A Sur #4881, Zona 1, Envigado, Antioquia, Colombia • @terretsports • info@terret.co</div>
</div>

</body>
</html>
""")

# ====================== INTERFAZ ======================
st.title("📄 Cotizador Terret 2026")

cliente = st.text_input("Nombre del cliente / Evento", "RUNNING BUCARAMANGA")
fecha = st.date_input("Fecha de cotización", datetime.today())

titulos = ["PROPUESTA COMERCIAL CAMISETAS", "PROPUESTA COMERCIAL MERCH", "PROPUESTA COMERCIAL EVENTO", "PROPUESTA COMERCIAL KIT"]
titulo_propuesta = st.selectbox("Título de la propuesta comercial", titulos + ["Personalizado..."])
if titulo_propuesta == "Personalizado...":
    titulo_propuesta = st.text_input("Escribe el título personalizado")

st.subheader("Agregar productos")
if "items" not in st.session_state:
    st.session_state.items = []

col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    producto_sel = st.selectbox("Producto", productos_df["nombre_producto"].tolist())
with col2:
    cantidad = st.number_input("Cantidad", min_value=1, value=1)
with col3:
    if st.button("➕ Agregar"):
        row = productos_df[productos_df["nombre_producto"] == producto_sel].iloc[0]
        precio = obtener_precio(row, cantidad)
        st.session_state.items.append({
            "referencia": row.get("referencia", ""),
            "nombre": row["nombre_producto"],
            "cantidad": cantidad,
            "precio_unitario": precio,
            "total_linea": cantidad * precio
        })
        st.success(f"{producto_sel} agregado – precio según escala aplicada")

if st.session_state.items:
    df_items = pd.DataFrame(st.session_state.items)
    st.dataframe(df_items, use_container_width=True)
    total_general = df_items["total_linea"].sum()
    st.metric("TOTAL GENERAL (antes de IVA)", f"${total_general:,.0f}")

# ====================== GENERAR PDF ======================
if st.button("🚀 Generar y Guardar PDF completo (6 páginas)", type="primary") and st.session_state.items:
    numero = obtener_siguiente_numero()

    tablas_html = ""
    for item in st.session_state.items:
        subtotal = item["total_linea"]
        iva = subtotal * 0.19
        total_con_iva = subtotal + iva
        tablas_html += f"""
        <table>
            <tr><th>Referencia</th><th>Cantidad</th><th>Valor unitario</th><th>TOTAL</th></tr>
            <tr><td>{item['referencia']}</td><td>{item['cantidad']}</td><td>${item['precio_unitario']:,.0f}</td><td>${subtotal:,.0f}</td></tr>
            <tr><td colspan="3" style="text-align:right;">SUBTOTAL</td><td>${subtotal:,.0f}</td></tr>
            <tr><td colspan="3" style="text-align:right;">IVA 19%</td><td>${iva:,.0f}</td></tr>
            <tr><td colspan="3" style="text-align:right;"><strong>TOTAL</strong></td><td><strong>${total_con_iva:,.0f}</strong></td></tr>
        </table><br>
        """

    html_final = html_template.render(
        fecha=fecha.strftime("%d de %B del %Y").upper(),
        cliente=cliente.upper(),
        titulo_propuesta=titulo_propuesta,
        html_tablas=tablas_html,
        total_general=total_general
    )

    pdf_bytes = HTML(string=html_final).write_pdf()

    filename = f"Cotizacion_{numero:04d}_{cliente.replace(' ', '_')}.pdf"

    # Subir a carpeta Cotizador
    file_metadata = {'name': filename, 'parents': [FOLDER_ID]}
    media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype='application/pdf')
    drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    st.success(f"✅ Cotización #{numero:04d} generada y guardada en la carpeta Cotizador")
    st.balloons()

    st.download_button("📥 Descargar PDF ahora", data=pdf_bytes, file_name=filename, mime="application/pdf")

    st.session_state.items = []
