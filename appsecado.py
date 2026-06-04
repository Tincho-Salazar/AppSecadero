from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, make_response, send_file
import mysql.connector
from mysql.connector import pooling
import pyodbc
import time
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
# Bokeh imports
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.resources import INLINE
from bokeh.models import ColumnDataSource, HoverTool
from bokeh.transform import factor_cmap
from bokeh.palettes import Spectral11, Category20
# ReportLab imports (PDF)
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from collections import defaultdict
# Dash imports
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import os
import contextlib
import sys
import openpyxl
import webbrowser
import threading 

# --- CONFIGURACIÓN ---
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'Datiles2044')
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
    TEMPLATE_FOLDER = os.path.join(BASE_DIR, 'templates')

    # Configuración MySQL
    MYSQL_HOST = os.environ.get('MYSQL_HOST', '192.168.37.114')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'consultaDB')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'cPindo2024')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'bolsas')
    
    # Configuración SQL Server
    SQL_SERVER = '192.168.30.5\\prd'
    SQL_DATABASE = 'SAPINFO'
    SQL_USER = 'laichi'
    SQL_PASSWORD = 'datiles2044pera%%%'

# Inicializar Flask
app = Flask(__name__, static_folder=Config.STATIC_FOLDER, template_folder=Config.TEMPLATE_FOLDER)
app.config.from_object(Config)

# Inicializar Dash
dash_app = dash.Dash(__name__, server=app, url_base_pathname='/dash/',
                     meta_tags=[{'name': 'viewport', 'content': 'width=device-width, initial-scale=1'}])

# --- POOL DE CONEXIONES MYSQL ---
mysql_pool = None

def init_mysql_pool():
    global mysql_pool
    try:
        import mysql.connector
        from mysql.connector import pooling, errorcode
        
        config = {
            'host': Config.MYSQL_HOST,
            'user': Config.MYSQL_USER,
            'password': Config.MYSQL_PASSWORD,
            'database': Config.MYSQL_DB,
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_general_ci',
            'connection_timeout': 15,
            'pool_name': 'mypool',
            'pool_size': 10,
            'pool_reset_session': True,
            'use_pure': True,
            'autocommit': False
        }
        mysql_pool = pooling.MySQLConnectionPool(**config)
        print("✓ Pool de conexiones MySQL iniciado correctamente.")
        return True
    except Exception as e:
        print(f"✗ Error crítico al iniciar Pool MySQL: {e}")
        return False

# Inicializamos el pool
init_mysql_pool()

# --- GESTORES DE DB ---
@contextlib.contextmanager
def get_mysql_connection():
    global mysql_pool
    if mysql_pool is None:
        if not init_mysql_pool():
            raise Exception("El pool de MySQL no está disponible.")
    connection = mysql_pool.get_connection()
    try:
        yield connection
    finally:
        connection.close()

def execute_query(query, params=None, fetchone=False, commit=False):
    try:
        with get_mysql_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(query, params or ())
            if commit:
                connection.commit()
                result = None
            else:
                result = cursor.fetchone() if fetchone else cursor.fetchall()
            cursor.close()
            return result
    except Exception as e:
        print(f"Error DB: {e}")
        return None

def get_sql_server_connection():
    try:
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={Config.SQL_SERVER};"
            f"DATABASE={Config.SQL_DATABASE};"
            f"UID={Config.SQL_USER};"
            f"PWD={Config.SQL_PASSWORD};"
            "Encrypt=yes;"
            "TrustServerCertificate=yes;"
        )
        return pyodbc.connect(conn_str)
    except Exception as e:
        print(f"Error ODBC: {e}")
        return None

_hoja_verde_cache = {
    'timestamp': 0,
    'data': None
}

def get_peso_total_hoja_verde():
    global _hoja_verde_cache
    now = time.time()
    if _hoja_verde_cache['data'] is not None and (now - _hoja_verde_cache['timestamp']) < 60:
        return _hoja_verde_cache['data']

    try:
        conn = get_sql_server_connection()
        if not conn: 
            return {"total_hoja_verde_diario": 0, "total_hoja_verde_mensual": 0, "online": False}
        cursor = conn.cursor()
        
        cursor.execute("SELECT SUM(pesoneto - pesotara) FROM ZTPESAJES WHERE CONVERT(DATE, LEFT(Fechaentrada, 8), 112) = CONVERT(DATE, GETDATE(), 112)")
        diario = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(pesoneto - pesotara) FROM ZTPESAJES WHERE MONTH(CONVERT(DATE, LEFT(Fechaentrada, 8), 112)) = MONTH(GETDATE()) AND YEAR(CONVERT(DATE, LEFT(Fechaentrada, 8), 112)) = YEAR(GETDATE())")
        mensual = cursor.fetchone()[0] or 0
        
        conn.close()
        res = {"total_hoja_verde_diario": diario, "total_hoja_verde_mensual": mensual, "online": True}
        _hoja_verde_cache['timestamp'] = now
        _hoja_verde_cache['data'] = res
        return res
    except Exception as e:
        print(f"Error pyodbc (SQL Server Balanza): {e}")
        return {"total_hoja_verde_diario": 0, "total_hoja_verde_mensual": 0, "online": False}

# --- RUTAS DE LA APP ---

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrap(*args, **kwargs):
        if session.get('rol') != 'ADMINISTRADOR':
            flash("Acceso denegado.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrap

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        contrasena = request.form['contrasena']
        user = execute_query("SELECT * FROM usuarios WHERE usuario = %s", (usuario,), fetchone=True)
        if user and check_password_hash(user['contrasena'], contrasena):
            session['usuario'] = user['usuario']
            session['rol'] = user['rol']
            return jsonify({'status': 'success', 'redirect': url_for('index')})
        return jsonify({'status': 'error', 'message': 'Credenciales incorrectas'})
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        contrasena = request.form.get('contrasena')
        
        existe = execute_query("SELECT * FROM usuarios WHERE usuario = %s", (usuario,), fetchone=True)
        if existe:
            return jsonify({'status': 'error', 'message': 'El usuario ya existe'})

        hashed = generate_password_hash(contrasena)
        execute_query("INSERT INTO usuarios (usuario, contrasena, rol) VALUES (%s, %s, 'USUARIO')", 
                     (usuario, hashed), commit=True)
        return jsonify({'status': 'success', 'redirect': url_for('login')})
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- CRUDs ---
@app.route('/admin/usuarios')
@login_required
@admin_required
def gestionar_usuarios():
    return render_template('usuario.html', usuarios=execute_query("SELECT * FROM usuarios") or [])

@app.route('/crear_usuario', methods=['POST'])
def crear_usuario():
    h = generate_password_hash(request.form['contrasena'])
    execute_query("INSERT INTO usuarios (usuario, contrasena, rol) VALUES (%s, %s, %s)",
                  (request.form['usuario'], h, request.form['rol']), commit=True)
    return jsonify({'message': 'Usuario creado'})

@app.route('/editar_usuario/<int:id>', methods=['POST'])
def editar_usuario(id):
    contrasena = request.form.get('contrasena')
    usuario = request.form['usuario']
    rol = request.form['rol']
    
    if contrasena:
        h = generate_password_hash(contrasena)
        execute_query("UPDATE usuarios SET usuario=%s, contrasena=%s, rol=%s WHERE id=%s",
                      (usuario, h, rol, id), commit=True)
    else:
        execute_query("UPDATE usuarios SET usuario=%s, rol=%s WHERE id=%s",
                      (usuario, rol, id), commit=True)
                      
    return jsonify({'message': 'Usuario editado'})

@app.route('/eliminar_usuario/<int:id>', methods=['DELETE'])
def eliminar_usuario(id):
    execute_query("DELETE FROM usuarios WHERE id=%s", (id,), commit=True)
    return jsonify({'message': 'Usuario eliminado'})

@app.route('/admin/empleados')
@login_required
@admin_required
def gestionar_empleados():
    return render_template('empleado.html', empleados=execute_query("SELECT * FROM empleados") or [])

@app.route('/crear_empleado', methods=['POST'])
def crear_empleado():
    execute_query("INSERT INTO empleados (nombre, puesto) VALUES (%s, %s)",
                  (request.form['empleado'], request.form['rol']), commit=True)
    return jsonify({'message': 'Empleado creado'})

@app.route('/editar_empleado/<int:id>', methods=['POST'])
def editar_empleado(id):
    execute_query("UPDATE empleados SET nombre=%s, puesto=%s WHERE id=%s",
                  (request.form['empleado'], request.form['rol'], id), commit=True)
    return jsonify({'message': 'Empleado actualizado'})

@app.route('/eliminar_empleado/<int:id>', methods=['DELETE'])
def eliminar_empleado(id):
    execute_query("DELETE FROM empleados WHERE id=%s", (id,), commit=True)
    return jsonify({'message': 'Empleado eliminado'})

@app.route('/admin/productos')
@login_required
@admin_required
def gestionar_productos():
    return render_template('productos.html', productos=execute_query("SELECT * FROM productos") or [])

@app.route('/crear_producto', methods=['POST'])
def crear_producto():
    propio = 1 if request.form.get('propio') == '1' else 0
    execute_query("INSERT INTO productos (nombre_producto, calidad, descripcion, propio) VALUES (%s, %s, %s, %s)",
                  (request.form['nombre'], request.form['calidad'], request.form['descripcion'], propio), commit=True)
    return jsonify({'message': 'Producto creado'})

@app.route('/editar_producto/<int:id>', methods=['POST'])
def editar_producto(id):
    propio = 1 if request.form.get('propio') == '1' else 0
    execute_query("UPDATE productos SET nombre_producto=%s, calidad=%s, descripcion=%s, propio=%s WHERE producto_id=%s",
                  (request.form['nombre'], request.form['calidad'], request.form['descripcion'], propio, id), commit=True)
    return jsonify({'message': 'Producto actualizado'})

@app.route('/eliminar_producto/<int:id>', methods=['DELETE'])
def eliminar_producto(id):
    execute_query("DELETE FROM productos WHERE producto_id=%s", (id,), commit=True)
    return jsonify({'message': 'Producto eliminado'})

# --- REPORTES ---
def obtener_datos_reporte(fecha_inicio, hora_inicio, fecha_final, hora_final, origen='todos', tipo='general'):
    """Lógica centralizada para la query compleja de reportes."""
    inicio = f"{fecha_inicio} {hora_inicio}"
    final = f"{fecha_final} {hora_final}"
    
    if tipo == 'detallado_tercero':
        q = """
        SELECT 
            y.bolsa,
            y.tiempo,
            y.peso,
            y.nprod,
            y.parcela,
            y.carga,
            y.zafra,
            p.nom AS prod_nombre,
            p.ape AS prod_apellido,
            p.cd,
            CONCAT(IFNULL(p.nom, ''), ' ', IFNULL(p.ape, '')) AS productor_nombre
        FROM YMA_pesajes y
        LEFT JOIN YMA_productores p ON y.nprod = p.id
        WHERE y.tiempo BETWEEN %s AND %s
        ORDER BY p.nom, p.ape, DATE(y.tiempo), y.tiempo
        """
        return execute_query(q, (inicio, final))
        
    elif tipo == 'detallado_propio':
        q = """
        SELECT 
            p.pesaje_id,
            pr.nombre_producto AS producto,
            pr.calidad,
            CONCAT(pr.nombre_producto, ' ', IFNULL(pr.calidad, '')) AS producto_completo,
            e.nombre AS empleado,
            p.peso,
            p.lote,
            p.fecha_hora AS tiempo
        FROM pesajes p
        JOIN productos pr ON p.producto_id = pr.producto_id
        LEFT JOIN empleados e ON p.empleado_id = e.id
        WHERE pr.propio = 1 AND p.fecha_hora BETWEEN %s AND %s
        ORDER BY DATE(p.fecha_hora), pr.nombre_producto, p.lote, p.fecha_hora
        """
        return execute_query(q, (inicio, final))
        
    cond_origen = ""
    if origen == 'propio':
        cond_origen = "AND pr.propio = 1"
    elif origen == 'tercero':
        cond_origen = "AND pr.propio = 0"
        
    q = f"""
    WITH intervalos AS (
        SELECT p.producto_id, pr.nombre_producto AS producto, DATE(p.fecha_hora) AS fecha,
            MIN(p.fecha_hora) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora)) AS primer_pesaje,
            MAX(p.fecha_hora) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora)) AS ultimo_pesaje,
            SUM(p.peso) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora)) AS total_peso,
            TIMESTAMPDIFF(MINUTE, p.fecha_hora, LEAD(p.fecha_hora) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora) ORDER BY p.fecha_hora)) AS intervalo_minutos
        FROM pesajes p JOIN productos pr ON p.producto_id = pr.producto_id WHERE p.fecha_hora BETWEEN %s AND %s {cond_origen}
    )
    SELECT fecha, producto, MIN(primer_pesaje) AS primer_pesaje, MAX(ultimo_pesaje) AS ultimo_pesaje,
        TIMESTAMPDIFF(HOUR, MIN(primer_pesaje), MAX(ultimo_pesaje)) AS horas_totales,
        ROUND(SUM(CASE WHEN intervalo_minutos >= 30 THEN (CASE WHEN intervalo_minutos % 30 >= 15 THEN CEIL(intervalo_minutos/30)*0.5 ELSE FLOOR(intervalo_minutos/30)*0.5 END) ELSE 0 END), 1) AS tiempo_muerto_horas,
        MAX(total_peso) AS total_peso_kg, SUM(MAX(total_peso)) OVER () AS total_general, COUNT(*) AS cantidad_pesajes
    FROM intervalos WHERE intervalo_minutos IS NOT NULL GROUP BY fecha, producto ORDER BY fecha, producto;
    """
    return execute_query(q, (inicio, final))

@app.route('/admin/reportes', methods=['GET', 'POST'])
def reportes():
    if request.method == 'POST':
        try:
            d = request.get_json()
            tipo = d.get('tipo', 'general')
            res = obtener_datos_reporte(
                d['fecha_inicio'], d['hora_inicio'],
                d['fecha_final'], d['hora_final'],
                d.get('origen', 'todos'),
                tipo
            ) or []
            
            json_out = []
            if tipo == 'detallado_propio':
                for r in res:
                    json_out.append({
                        "fecha": r['tiempo'].strftime("%Y-%m-%d"),
                        "lote": r['lote'],
                        "producto": f"{r['producto']} {r['calidad'] or ''}".strip(),
                        "hora": r['tiempo'].strftime("%H:%M"),
                        "empleado": r['empleado'],
                        "peso": float(r['peso'])
                    })
            elif tipo == 'detallado_tercero':
                for r in res:
                    prod_nombre = f"{r['prod_nombre'] or ''} {r['prod_apellido'] or ''}".strip()
                    if not prod_nombre:
                        prod_nombre = f"Desconocido (ID: {r['nprod']})"
                    json_out.append({
                        "productor_nombre": prod_nombre,
                        "fecha": r['tiempo'].strftime("%Y-%m-%d"),
                        "bolsa": r['bolsa'],
                        "hora": r['tiempo'].strftime("%H:%M"),
                        "cd": r['cd'],
                        "parcela": r['parcela'],
                        "carga": r['carga'],
                        "zafra": r['zafra'],
                        "peso": float(r['peso'])
                    })
            else:
                for r in res:
                    json_out.append({
                        "producto": r['producto'], "primer_pesaje": r['primer_pesaje'].strftime("%d-%m %H:%M"),
                        "ultimo_pesaje": r['ultimo_pesaje'].strftime("%d-%m %H:%M"), "cantidad_pesajes": r['cantidad_pesajes'],
                        "horas_totales": r['horas_totales'], "tiempo_muerto_horas": r['tiempo_muerto_horas'],
                        "total_peso_kg": float(r['total_peso_kg']), "total_general": float(r['total_general'])
                    })
            return jsonify({"resultados": json_out})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('reportes.html')

@app.route('/admin/reportes/pdf', methods=['GET'])
@login_required
@admin_required
def reportes_pdf():
    # Obtener parámetros
    f_inicio = request.args.get('fecha_inicio')
    h_inicio = request.args.get('hora_inicio')
    f_final = request.args.get('fecha_final')
    h_final = request.args.get('hora_final')
    tipo_reporte = request.args.get('tipo', 'general')
    origen = request.args.get('origen', 'todos')

    if not all([f_inicio, h_inicio, f_final, h_final]):
        flash("Faltan parámetros", "warning")
        return redirect('/admin/reportes')

    try:
        reportes = obtener_datos_reporte(f_inicio, h_inicio, f_final, h_final, origen, tipo_reporte) or []
        
        totales_por_producto = defaultdict(float)
        for r in reportes:
            if tipo_reporte == 'detallado_propio':
                p_str = f"{r['producto']} {r['calidad'] or ''}".strip()
                totales_por_producto[p_str] += float(r['peso'])
            elif tipo_reporte == 'detallado_tercero':
                prod_nombre = f"{r['prod_nombre'] or ''} {r['prod_apellido'] or ''}".strip()
                if not prod_nombre:
                    prod_nombre = f"Desconocido (ID: {r['nprod']})"
                totales_por_producto[prod_nombre] += float(r['peso'])
            else:
                totales_por_producto[r['producto']] += float(r['total_peso_kg'])

        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 50

        def draw_headers(y_pos):
            p.setFont("Helvetica-Bold", 9)
            p.setFillColorRGB(0.2, 0.2, 0.2)
            headers = ["Producto", "Inicio", "Fin", "Bolsas", "Hs Tot", "T. Muerto", "Total KG"]
            xs = [20, 200, 260, 320, 370, 430, 500]
            for t, x in zip(headers, xs): p.drawString(x, y_pos, t)
            p.setLineWidth(1)
            p.line(20, y_pos - 5, width - 20, y_pos - 5)
            p.setFillColorRGB(0, 0, 0)
            return y_pos - 20

        logo = os.path.join(app.static_folder, 'png', 'logo.jpg')
        if os.path.exists(logo):
            p.drawImage(logo, 20, height - 60, width=60, height=40, mask='auto')
        
        p.setFont("Helvetica-Bold", 14)
        if tipo_reporte == 'detallado_propio':
            titulo = "Reporte Detallado de Pesajes Propios"
        elif tipo_reporte == 'detallado_tercero':
            titulo = "Reporte Detallado de Pesajes Terceros"
        else:
            titulo = "Reporte Detallado" if tipo_reporte == 'detallado' else "Reporte General"
            
        tipo_lbl = " - Propios" if origen == 'propio' else (" - Terceros" if origen == 'tercero' else "")
        if tipo_reporte in ['detallado_propio', 'detallado_tercero']:
            p.drawString(100, height - 40, titulo)
        else:
            p.drawString(100, height - 40, f"{titulo} de Pesajes{tipo_lbl}")
            
        p.setFont("Helvetica", 10)
        p.drawString(100, height - 55, f"Rango: {f_inicio} {h_inicio} al {f_final} {h_final}")
        
        y -= 80

        if tipo_reporte == 'detallado_propio':
            # Group by Date, then by Product
            datos_agrupados = defaultdict(lambda: defaultdict(list))
            for r in reportes:
                f_str = r['tiempo'].strftime("%Y-%m-%d")
                p_str = f"{r['producto']} {r['calidad'] or ''}".strip()
                datos_agrupados[f_str][p_str].append(r)
            
            fechas_ordenadas = sorted(datos_agrupados.keys())
            
            def draw_propio_headers(y_pos):
                p.setFont("Helvetica-Bold", 9)
                p.setFillColorRGB(0.2, 0.2, 0.2)
                headers = ["Lote", "Hora", "Operario", "Peso KG"]
                xs = [40, 120, 220, 480]
                for t, x in zip(headers, xs):
                    if t == "Peso KG":
                        p.drawRightString(x, y_pos, t)
                    else:
                        p.drawString(x, y_pos, t)
                p.setLineWidth(0.5)
                p.line(40, y_pos - 4, width - 40, y_pos - 4)
                p.setFillColorRGB(0, 0, 0)
                return y_pos - 15

            for fecha in fechas_ordenadas:
                if y < 80:
                    p.showPage()
                    y = height - 50
                
                p.setFont("Helvetica-Bold", 11)
                p.setFillColorRGB(0, 0.4, 0.8)
                p.drawString(20, y, f"Fecha: {fecha}")
                p.setFillColorRGB(0, 0, 0)
                y -= 15
                
                for prod in sorted(datos_agrupados[fecha].keys()):
                    if y < 80:
                        p.showPage()
                        y = height - 50
                    
                    p.setFont("Helvetica-Bold", 10)
                    p.drawString(30, y, f"Producto: {prod}")
                    y -= 12
                    
                    y = draw_propio_headers(y)
                    p.setFont("Helvetica", 9)
                    
                    subtotal_prod = 0
                    for r in datos_agrupados[fecha][prod]:
                        if y < 50:
                            p.showPage()
                            y = height - 50
                            y = draw_propio_headers(y)
                            p.setFont("Helvetica", 9)
                            
                        p.drawString(40, y, str(r['lote']))
                        p.drawString(120, y, r['tiempo'].strftime('%H:%M'))
                        p.drawString(220, y, str(r['empleado'] or '-')[:40])
                        p.drawRightString(480, y, f"{float(r['peso']):,.1f}")
                        subtotal_prod += float(r['peso'])
                        y -= 12
                        
                    y -= 3
                    p.setLineWidth(0.5)
                    p.line(400, y, 480, y)
                    y -= 10
                    p.setFont("Helvetica-Bold", 9)
                    p.drawString(320, y, "Total Producto:")
                    p.drawRightString(480, y, f"{subtotal_prod:,.1f} KG")
                    p.setFont("Helvetica", 9)
                    y -= 15

        elif tipo_reporte == 'detallado_tercero':
            # Group by Producer, then by Date
            datos_agrupados = defaultdict(lambda: defaultdict(list))
            for r in reportes:
                prod_nombre = f"{r['prod_nombre'] or ''} {r['prod_apellido'] or ''}".strip()
                if not prod_nombre:
                    prod_nombre = f"Desconocido (ID: {r['nprod']})"
                f_str = r['tiempo'].strftime("%Y-%m-%d")
                datos_agrupados[prod_nombre][f_str].append(r)
                
            prods_ordenados = sorted(datos_agrupados.keys())
            
            def draw_tercero_headers(y_pos):
                p.setFont("Helvetica-Bold", 9)
                p.setFillColorRGB(0.2, 0.2, 0.2)
                headers = ["Bolsa", "Hora", "Lote", "Parcela", "Carga", "Zafra", "Peso KG"]
                xs = [40, 90, 140, 200, 260, 320, 480]
                for t, x in zip(headers, xs):
                    if t == "Peso KG":
                        p.drawRightString(x, y_pos, t)
                    else:
                        p.drawString(x, y_pos, t)
                p.setLineWidth(0.5)
                p.line(40, y_pos - 4, width - 40, y_pos - 4)
                p.setFillColorRGB(0, 0, 0)
                return y_pos - 15
                
            for prod in prods_ordenados:
                if y < 100:
                    p.showPage()
                    y = height - 50
                    
                p.setFont("Helvetica-Bold", 11)
                p.setFillColorRGB(0.6, 0.2, 0)
                p.drawString(20, y, f"Productor: {prod}")
                p.setFillColorRGB(0, 0, 0)
                y -= 15
                
                for fecha in sorted(datos_agrupados[prod].keys()):
                    if y < 80:
                        p.showPage()
                        y = height - 50
                        
                    p.setFont("Helvetica-Bold", 10)
                    p.drawString(30, y, f"Fecha: {fecha}")
                    y -= 12
                    
                    y = draw_tercero_headers(y)
                    p.setFont("Helvetica", 9)
                    
                    subtotal_dia = 0
                    for r in datos_agrupados[prod][fecha]:
                        if y < 50:
                            p.showPage()
                            y = height - 50
                            y = draw_tercero_headers(y)
                            p.setFont("Helvetica", 9)
                            
                        p.drawString(40, y, str(r['bolsa']))
                        p.drawString(90, y, r['tiempo'].strftime('%H:%M'))
                        p.drawString(140, y, str(r['cd'] or '-')[:10])
                        p.drawString(200, y, str(r['parcela']))
                        p.drawString(260, y, str(r['carga']))
                        p.drawString(320, y, str(r['zafra']))
                        p.drawRightString(480, y, f"{float(r['peso']):,.1f}")
                        subtotal_dia += float(r['peso'])
                        y -= 12
                        
                    y -= 3
                    p.setLineWidth(0.5)
                    p.line(400, y, 480, y)
                    y -= 10
                    p.setFont("Helvetica-Bold", 9)
                    p.drawString(320, y, "Total Día:")
                    p.drawRightString(480, y, f"{subtotal_dia:,.1f} KG")
                    p.setFont("Helvetica", 9)
                    y -= 15

        elif tipo_reporte == 'detallado':
            datos_por_fecha = defaultdict(list)
            for r in reportes:
                datos_por_fecha[r['fecha']].append(r)
            
            fechas_ordenadas = sorted(datos_por_fecha.keys())

            for fecha in fechas_ordenadas:
                if y < 80:
                    p.showPage()
                    y = height - 50
                
                p.setFont("Helvetica-Bold", 11)
                p.setFillColorRGB(0, 0.5, 0)
                p.drawString(20, y, f"Fecha: {fecha}")
                p.setFillColorRGB(0, 0, 0)
                y -= 15
                
                y = draw_headers(y)
                p.setFont("Helvetica", 9)

                subtotal_dia = 0 # Inicializar subtotal del día
                
                for r in datos_por_fecha[fecha]:
                    kg_producto = float(r['total_peso_kg'])
                    subtotal_dia += kg_producto
                    
                    p.drawString(20, y, str(r['producto'])[:35])
                    p.drawString(200, y, r['primer_pesaje'].strftime('%H:%M'))
                    p.drawString(260, y, r['ultimo_pesaje'].strftime('%H:%M'))
                    p.drawString(325, y, str(r['cantidad_pesajes']))
                    p.drawString(375, y, str(r['horas_totales']))
                    p.drawString(440, y, str(r['tiempo_muerto_horas']))
                    p.drawString(500, y, f"{kg_producto:,.2f}")
                    y -= 15
                    
                    if y < 50:
                        p.showPage()
                        y = height - 50
                        y = draw_headers(y)
                        p.setFont("Helvetica", 9)
                
                # --- SUBTOTAL POR DÍA ---
                y -= 5
                p.setLineWidth(0.5)
                p.line(450, y, 560, y) # Línea divisoria sobre el subtotal
                y -= 12
                p.setFont("Helvetica-Bold", 9)
                p.drawString(420, y, f"Total Día :")
                p.drawString(500, y, f"{subtotal_dia:,.2f}")
                p.setFont("Helvetica", 9) # Restaurar fuente normal
                y -= 20 # Espacio extra para separar días

        else:
            y = draw_headers(y)
            p.setFont("Helvetica", 9)
            
            for r in reportes:
                p.drawString(20, y, str(r['producto'])[:35])
                p.drawString(200, y, r['primer_pesaje'].strftime('%d/%m %H:%M'))
                p.drawString(260, y, r['ultimo_pesaje'].strftime('%d/%m %H:%M'))
                p.drawString(325, y, str(r['cantidad_pesajes']))
                p.drawString(375, y, str(r['horas_totales']))
                p.drawString(440, y, str(r['tiempo_muerto_horas']))
                p.drawString(500, y, f"{r['total_peso_kg']:,.2f}")
                y -= 15
                
                if y < 50:
                    p.showPage()
                    y = height - 50
                    y = draw_headers(y)
                    p.setFont("Helvetica", 9)

        if y < 100 + (len(totales_por_producto) * 15):
            p.showPage()
            y = height - 50

        y -= 20
        p.setLineWidth(1)
        p.line(20, y, width - 20, y)
        y -= 20
        p.setFont("Helvetica-Bold", 12)
        if tipo_reporte == 'detallado_tercero':
            p.drawString(20, y, "Resumen de Totales por Productor")
        else:
            p.drawString(20, y, "Resumen de Totales por Producto")
        y -= 20
        
        p.setFont("Helvetica", 10)
        total_global = 0
        for prod, total in totales_por_producto.items():
            p.drawString(40, y, f"- {prod}")
            p.drawRightString(550, y, f"{total:,.2f} KG")
            total_global += total
            y -= 15
        
        y -= 10
        p.line(250, y, 560, y)
        y -= 20
        p.setFont("Helvetica-Bold", 12)
        p.drawString(250, y, "TOTAL PROCESADO:")
        p.drawRightString(550, y, f"{total_global:,.2f} KG")

        p.save()
        pdf = buffer.getvalue()
        buffer.close()
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=reporte_{tipo_reporte}.pdf'
        return response

    except Exception as e:
        print(f"Error PDF: {e}")
        return redirect('/admin/reportes')

@app.route('/admin/reportes/excel', methods=['GET'])
@login_required
@admin_required
def reportes_excel():
    f_inicio = request.args.get('fecha_inicio')
    h_inicio = request.args.get('hora_inicio')
    f_final = request.args.get('fecha_final')
    h_final = request.args.get('hora_final')
    origen = request.args.get('origen', 'todos')
    tipo = request.args.get('tipo', 'general')

    if not all([f_inicio, h_inicio, f_final, h_final]):
        flash("Faltan parámetros", "warning")
        return redirect('/admin/reportes')

    try:
        data = obtener_datos_reporte(f_inicio, h_inicio, f_final, h_final, origen, tipo)
        if not data:
            flash("No hay datos para exportar", "warning")
            return redirect('/admin/reportes')

        df = pd.DataFrame(data)
        
        if tipo == 'detallado_propio':
            df['Fecha'] = df['tiempo'].apply(lambda x: x.strftime('%Y-%m-%d'))
            df['Hora'] = df['tiempo'].apply(lambda x: x.strftime('%H:%M'))
            df['Producto'] = df['producto_completo']
            df['Lote'] = df['lote']
            df['Operario'] = df['empleado']
            df['Peso KG'] = df['peso'].astype(float)
            
            df_out = df[['Fecha', 'Hora', 'Producto', 'Lote', 'Operario', 'Peso KG']]
            
            totales = df.groupby('Producto')['Peso KG'].sum().reset_index()
            totales.columns = ['Producto', 'Total Acumulado KG']
            
        elif tipo == 'detallado_tercero':
            def format_prod(row):
                name = f"{row['prod_nombre'] or ''} {row['prod_apellido'] or ''}".strip()
                return name if name else f"Desconocido (ID: {row['nprod']})"
                
            df['Productor'] = df.apply(format_prod, axis=1)
            df['Fecha'] = df['tiempo'].apply(lambda x: x.strftime('%Y-%m-%d'))
            df['Bolsa'] = df['bolsa']
            df['Hora'] = df['tiempo'].apply(lambda x: x.strftime('%H:%M'))
            df['Lote'] = df['cd']
            df['Parcela'] = df['parcela']
            df['Carga'] = df['carga']
            df['Zafra'] = df['zafra']
            df['Peso KG'] = df['peso'].astype(float)
            
            df_out = df[['Productor', 'Fecha', 'Bolsa', 'Hora', 'Lote', 'Parcela', 'Carga', 'Zafra', 'Peso KG']]
            
            totales = df.groupby('Productor')['Peso KG'].sum().reset_index()
            totales.columns = ['Productor', 'Total Acumulado KG']
            
        else:
            df_out = df[['fecha', 'producto', 'primer_pesaje', 'ultimo_pesaje', 'cantidad_pesajes', 
                     'horas_totales', 'tiempo_muerto_horas', 'total_peso_kg']]
            df_out.columns = ['Fecha', 'Producto', 'Inicio', 'Fin', 'Cant. Bolsas', 
                          'Horas Totales', 'Tiempo Muerto', 'Total KG']

            totales = df_out.groupby('Producto')['Total KG'].sum().reset_index()
            totales.columns = ['Producto', 'Total Acumulado KG']

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_out.to_excel(writer, sheet_name='Detalle', index=False)
            totales.to_excel(writer, sheet_name='Totales', index=False)
            
        output.seek(0)
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f"reporte_{f_inicio}_{f_final}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        print(f"Error Excel: {e}")
        flash(f"Error generando Excel: {str(e)}", "danger")
        return redirect('/admin/reportes')

# --- API y BOKEH ---
@app.route('/api/datos')
def api_datos():
    act = execute_query("SELECT ps.peso, ps.lote, ps.pesaje_id, CONCAT(p.nombre_producto, ' ', p.calidad) as nom FROM pesajes ps JOIN productos p ON ps.producto_id = p.producto_id ORDER BY ps.fecha_hora DESC LIMIT 1", fetchone=True)
    return jsonify({
        "producto_actual": act['nom'] if act else "Esperando...",
        "pesaje_actual": act['peso'] if act else 0,
        "lote_actual": act['lote'] if act else "-",
        "pesaje_id": act['pesaje_id'] if act else "-"
    })

@app.route('/api/estadisticas')
def api_stats():
    hv = get_peso_total_hoja_verde()
    td_propio = execute_query("SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_diario FROM pesajes ps JOIN productos p ON ps.producto_id = p.producto_id WHERE DATE(ps.fecha_hora) = CURDATE() AND p.propio = 1 GROUP BY producto")
    td_terceros = execute_query("SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_diario FROM pesajes ps JOIN productos p ON ps.producto_id = p.producto_id WHERE DATE(ps.fecha_hora) = CURDATE() AND p.propio = 0 GROUP BY producto")
    
    tm_propio = execute_query("SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_mensual FROM pesajes ps JOIN productos p ON ps.producto_id = p.producto_id WHERE MONTH(ps.fecha_hora) = MONTH(CURDATE()) AND YEAR(ps.fecha_hora) = YEAR(CURDATE()) AND p.propio = 1 GROUP BY producto")
    tm_terceros = execute_query("SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_mensual FROM pesajes ps JOIN productos p ON ps.producto_id = p.producto_id WHERE MONTH(ps.fecha_hora) = MONTH(CURDATE()) AND YEAR(ps.fecha_hora) = YEAR(CURDATE()) AND p.propio = 0 GROUP BY producto")
    
    return jsonify({
        "total_diario": td_propio or [],
        "total_mensual": tm_propio or [],
        "total_diario_terceros": td_terceros or [],
        "total_mensual_terceros": tm_terceros or [],
        "total_hoja_verde_diario": hv['total_hoja_verde_diario'],
        "total_hoja_verde_mensual": hv['total_hoja_verde_mensual'],
        "balanza_online": hv.get('online', False)
    })

@app.route('/bokeh/pesajes')
def bokeh_pesajes():
    f = request.args.get('fecha', date.today().strftime('%Y-%m-%d'))
    data = execute_query("SELECT DATE_FORMAT(fecha_hora, '%H:00') AS hora, SUM(peso) AS total FROM pesajes WHERE DATE(fecha_hora) = %s GROUP BY hora ORDER BY hora", (f,))
    
    if not data: return render_template("bokeh_template.html", div="<div class='alert alert-warning text-center'>Sin datos para la fecha</div>", script="", titulo="Sin Datos")
    
    horas = [d['hora'] for d in data]
    pesos = [float(d['total']) for d in data]
    
    source = ColumnDataSource(data=dict(horas=horas, pesos=pesos))
    hover = HoverTool(tooltips=[("Hora", "@horas"), ("Total Kg", "@pesos{0.00}")])
    
    p = figure(x_range=horas, height=350, title=f"Pesajes por Hora ({f})", toolbar_location=None, tools=[hover])
    
    palette = Spectral11 * 3
    p.vbar(x='horas', top='pesos', width=0.9, source=source, 
           line_color='white', 
           fill_color=factor_cmap('horas', palette=palette, factors=horas))
           
    p.xaxis.major_label_orientation = "vertical"
    p.y_range.start = 0
    p.xgrid.grid_line_color = None
    
    script, div = components(p)
    return render_template("bokeh_template.html", script=script, div=div, resources=INLINE.render(), titulo="Pesajes por Hora")

# --- DASH APP (CON AUTO-REFRESH) ---
def get_dash_data(origen='propio'):
    cond_origen = ""
    if origen == 'propio':
        cond_origen = "AND p.propio = 1"
    elif origen == 'tercero':
        cond_origen = "AND p.propio = 0"
        
    data = execute_query(f"""
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_mensual
        FROM pesajes ps JOIN productos p ON ps.producto_id = p.producto_id
        WHERE MONTH(ps.fecha_hora) = MONTH(CURDATE()) AND YEAR(ps.fecha_hora) = YEAR(CURDATE()) {cond_origen}
        GROUP BY producto
    """)
    if not data: return None, None
    return [d['producto'] for d in data], [float(d['total_mensual']) for d in data]

dash_app.layout = html.Div([
    html.Div([
        html.H3("Producción Mensual", className="text-center mb-4"),
        # Intervalo: 60 segundos
        dcc.Interval(id='intervalo-dash', interval=60*1000, n_intervals=0),
        html.Div([
            html.Div([
                html.Label("Tipo de Gráfico:", className="fw-bold me-2"),
                dcc.Dropdown(
                    id='grafico-selector',
                    options=[
                        {'label': 'Barras Horizontales', 'value': 'barh'},
                        {'label': 'Torta (Distribución)', 'value': 'pie'},
                        {'label': 'Barras Verticales', 'value': 'bar'}
                    ],
                    value='barh',
                    clearable=False,
                    style={'width': '100%'}
                ),
            ], className="mb-3"),
            html.Div([
                html.Label("Origen del Producto:", className="fw-bold me-2"),
                dcc.RadioItems(
                    id='origen-selector',
                    options=[
                        {'label': ' Propios ', 'value': 'propio'},
                        {'label': ' Terceros ', 'value': 'tercero'},
                        {'label': ' Todos ', 'value': 'todos'}
                    ],
                    value='propio',
                    inline=True,
                    labelStyle={'display': 'inline-block', 'margin-right': '15px'},
                    inputStyle={'margin-right': '5px'}
                )
            ], className="mb-3"),
            dcc.Graph(id='grafico')
        ], className="card shadow-sm p-3")
    ], className="container-fluid py-3")
])

@dash_app.callback(
    Output('grafico', 'figure'),
    [Input('grafico-selector', 'value'),
     Input('origen-selector', 'value'),
     Input('intervalo-dash', 'n_intervals')]
)
def update_graph(tipo, origen, n):
    prods, totals = get_dash_data(origen)
    if not prods: 
        fig = go.Figure()
        fig.add_annotation(text="Sin datos este mes", showarrow=False, font={"size": 20})
        return fig

    df = pd.DataFrame({'Producto': prods, 'Kg': totals}).sort_values('Kg', ascending=True)
    
    if tipo == 'pie':
        fig = px.pie(df, names='Producto', values='Kg', title='Distribución %', color='Producto')
        fig.update_traces(textposition='inside', textinfo='percent+label')
    elif tipo == 'barh':
        fig = px.bar(df, x='Kg', y='Producto', orientation='h', title='Total Kg', text='Kg', color='Kg')
        fig.update_traces(texttemplate='%{text:.2s}', textposition='outside')
    else:
        fig = px.bar(df, x='Producto', y='Kg', title='Total Kg', color='Producto')
        fig.update_layout(xaxis_tickangle=-45)

    fig.update_layout(height=500, margin=dict(l=10, r=10, t=50, b=50), paper_bgcolor='rgba(0,0,0,0)')
    return fig

# --- EJECUCIÓN ---
def open_browser():
    # Esperar 1.5 segundos a que el servidor Flask se inicie y comience a escuchar
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == '__main__':
    # Eliminada simulación para entorno productivo
    if getattr(sys, 'frozen', False):
        print("INICIANDO MODO EJECUTABLE (PRODUCCIÓN)")
        # Iniciar el navegador automáticamente en segundo plano
        threading.Thread(target=open_browser, daemon=True).start()
        app.run(debug=False, use_reloader=False, host='0.0.0.0', port=5000)
    else:
        print("INICIANDO MODO DESARROLLO")
        app.run(debug=True, host='0.0.0.0', port=5000)