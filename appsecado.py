from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, make_response
import mysql.connector
from mysql.connector import pooling
import pyodbc
import time
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
import random
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
import pandas as pd
import os
import contextlib

# --- CONFIGURACIÓN ---
class Config:
    # Clave secreta (Mover a variable de entorno en producción real)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'Datiles2044')
    
    # Configuración de Rutas de Plantillas y Estáticos
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
dash_app = dash.Dash(__name__, server=app, url_base_pathname='/dash/')

# --- POOL DE CONEXIONES MYSQL ---
# Iniciamos el pool una sola vez al arrancar la app
mysql_pool = None
try:
    mysql_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="mypool",
        pool_size=10,
        pool_reset_session=True,
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        connection_timeout=15,
        charset='utf8mb4',
        collation='utf8mb4_general_ci' # Corrección para compatibilidad con MySQL 5.7/MariaDB
    )
    print("Pool de conexiones MySQL iniciado correctamente.")
except Exception as e:
    print(f"Error CRÍTICO al iniciar Pool MySQL: {e}")

# --- GESTORES DE CONTEXTO Y AYUDANTES DB ---

@contextlib.contextmanager
def get_mysql_connection():
    """Obtiene una conexión del pool y asegura su cierre (retorno al pool)."""
    if not mysql_pool:
        raise Exception("El pool de MySQL no está disponible.")
    connection = mysql_pool.get_connection()
    try:
        yield connection
    finally:
        connection.close()

def execute_query(query, params=None, fetchone=False, commit=False):
    """Ejecuta una consulta MySQL de manera segura."""
    try:
        with get_mysql_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(query, params or ())
            
            if commit:
                connection.commit()
                result = None # Operaciones de escritura no retornan filas usualmente
            else:
                result = cursor.fetchone() if fetchone else cursor.fetchall()
            
            cursor.close()
            return result
    except mysql.connector.Error as err:
        print(f"Error MySQL en query: {query}. Error: {err}")
        return None
    except Exception as e:
        print(f"Error general en DB: {e}")
        return None

def get_sql_server_connection():
    """Conecta a SQL Server via ODBC."""
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

def get_peso_total_hoja_verde():
    """Obtiene datos de Hoja Verde desde SQL Server."""
    try:
        conn = get_sql_server_connection()
        cursor = conn.cursor()

        # Hoja Verde Diario
        cursor.execute("""
            SELECT SUM(pesoneto - pesotara) 
            FROM ZTPESAJES 
            WHERE CONVERT(DATE, LEFT(Fechaentrada, 8), 112) = CONVERT(DATE, GETDATE(), 112)
        """)
        row_diario = cursor.fetchone()
        diario = row_diario[0] if row_diario and row_diario[0] else 0

        # Hoja Verde Mensual
        cursor.execute("""
            SELECT SUM(pesoneto - pesotara) 
            FROM ZTPESAJES 
            WHERE MONTH(CONVERT(DATE, LEFT(Fechaentrada, 8), 112)) = MONTH(GETDATE())
              AND YEAR(CONVERT(DATE, LEFT(Fechaentrada, 8), 112)) = YEAR(GETDATE())
        """)
        row_mensual = cursor.fetchone()
        mensual = row_mensual[0] if row_mensual and row_mensual[0] else 0

        conn.close()
        return {"total_hoja_verde_diario": diario, "total_hoja_verde_mensual": mensual}

    except Exception as e:
        print(f"Error conectando a SQL Server: {e}")
        return {"total_hoja_verde_diario": 0, "total_hoja_verde_mensual": 0}

# --- DECORADORES DE SEGURIDAD ---

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'usuario' not in session:
            flash("Por favor, inicia sesión primero", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrap(*args, **kwargs):
        if session.get('rol') != 'ADMINISTRADOR':
            flash("Acceso denegado. Debes ser ADMINISTRADOR", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrap

# --- RUTAS PRINCIPALES ---

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        contrasena = request.form['contrasena']
        
        user_data = execute_query("SELECT * FROM usuarios WHERE usuario = %s", (usuario,), fetchone=True)

        if user_data and check_password_hash(user_data['contrasena'], contrasena):
            session['usuario'] = user_data['usuario']
            session['rol'] = user_data['rol']
            return jsonify({'status': 'success', 'redirect': url_for('index')})
        else:
            return jsonify({'status': 'error', 'message': 'Usuario o contraseña incorrectos'})

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash("Has cerrado sesión con éxito", "success")
    return redirect(url_for('login'))

@app.route('/admin/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        new_username = request.form['new_usuario']
        new_password = request.form['new_contrasena']
        
        # Verificar existencia
        existing = execute_query("SELECT COUNT(*) as count FROM usuarios WHERE usuario = %s", (new_username,), fetchone=True)
        if existing and existing['count'] > 0:
            return jsonify({"message": "El nombre de usuario ya está registrado."})

        hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')
        execute_query(
            "INSERT INTO usuarios (usuario, contrasena, rol) VALUES (%s, %s, %s)",
            (new_username, hashed_password, 'USUARIO'),
            commit=True
        )
        return jsonify({"message": "Registro exitoso"}), 200

    return render_template('register.html') # Asegúrate de tener este archivo o usar login.html con opción de registro

# --- CRUD USUARIOS ---

@app.route('/admin/usuarios', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar_usuarios():
    usuarios = execute_query("SELECT * FROM usuarios") or []
    return render_template('usuario.html', usuarios=usuarios)

@app.route('/crear_usuario', methods=['POST'])
def crear_usuario():
    # Nota: Idealmente proteger esta ruta con @admin_required si es para uso interno
    usuario = request.form['usuario']
    contrasena = request.form['contrasena']
    rol = request.form['rol']
    hashed = generate_password_hash(contrasena, method='pbkdf2:sha256')
    
    execute_query(
        "INSERT INTO usuarios (usuario, contrasena, rol) VALUES (%s, %s, %s)",
        (usuario, hashed, rol),
        commit=True
    )
    return jsonify({'message': 'Usuario creado exitosamente'})

@app.route('/editar_usuario/<int:id>', methods=['POST'])
def editar_usuario(id):
    usuario = request.form['usuario']
    contrasena = request.form['contrasena']
    rol = request.form['rol']
    hashed = generate_password_hash(contrasena, method='pbkdf2:sha256')
    
    execute_query(
        "UPDATE usuarios SET usuario = %s, contrasena = %s, rol = %s WHERE id = %s",
        (usuario, hashed, rol, id),
        commit=True
    )
    return jsonify({'message': 'Usuario actualizado exitosamente'})

@app.route('/eliminar_usuario/<int:id>', methods=['DELETE'])
def eliminar_usuario(id):
    execute_query("DELETE FROM usuarios WHERE id = %s", (id,), commit=True)
    return jsonify({'message': 'Usuario eliminado exitosamente'})

# --- CRUD EMPLEADOS ---

@app.route('/admin/empleados', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar_empleados():
    empleados = execute_query("SELECT * FROM empleados") or []
    return render_template('empleado.html', empleados=empleados)

@app.route('/crear_empleado', methods=['POST'])
def crear_empleado():
    nombre = request.form['empleado']
    puesto = request.form['rol']
    execute_query(
        "INSERT INTO empleados (nombre, puesto) VALUES (%s, %s)",
        (nombre, puesto),
        commit=True
    )
    return jsonify({'message': 'Empleado creado exitosamente'})

@app.route('/editar_empleado/<int:id>', methods=['POST'])
def editar_empleado(id):
    nombre = request.form['empleado']
    puesto = request.form['rol']
    execute_query(
        "UPDATE empleados SET nombre = %s, puesto = %s WHERE id = %s",
        (nombre, puesto, id),
        commit=True
    )
    return jsonify({'message': 'Empleado actualizado exitosamente'})

@app.route('/eliminar_empleado/<int:id>', methods=['DELETE'])
def eliminar_empleado(id):
    execute_query("DELETE FROM empleados WHERE id = %s", (id,), commit=True)
    return jsonify({'message': 'Empleado eliminado exitosamente'})

# --- CRUD PRODUCTOS ---

@app.route('/admin/productos', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar_productos():
    productos = execute_query("SELECT * FROM productos") or []
    return render_template('productos.html', productos=productos)

@app.route('/crear_producto', methods=['POST'])
@login_required
@admin_required
def crear_producto():
    nombre = request.form['nombre']
    calidad = request.form['calidad']
    descripcion = request.form['descripcion']
    
    execute_query(
        "INSERT INTO productos (nombre_producto, calidad, descripcion) VALUES (%s, %s, %s)",
        (nombre, calidad, descripcion),
        commit=True
    )
    return jsonify({'message': 'Producto creado exitosamente'})

@app.route('/editar_producto/<int:id>', methods=['POST'])
@login_required
@admin_required
def editar_producto(id):
    nombre = request.form['nombre']
    calidad = request.form['calidad']
    descripcion = request.form['descripcion']
    
    execute_query(
        "UPDATE productos SET nombre_producto = %s, calidad = %s, descripcion = %s WHERE producto_id = %s",
        (nombre, calidad, descripcion, id),
        commit=True
    )
    return jsonify({'message': 'Producto actualizado exitosamente'})

@app.route('/eliminar_producto/<int:id>', methods=['DELETE'])
@login_required
@admin_required
def eliminar_producto(id):
    execute_query("DELETE FROM productos WHERE producto_id = %s", (id,), commit=True)
    return jsonify({'message': 'Producto eliminado exitosamente'})

# --- REPORTES (JSON y PDF) ---

def obtener_datos_reporte(fecha_inicio, hora_inicio, fecha_final, hora_final):
    """Lógica centralizada para la query compleja de reportes."""
    inicio = datetime.strptime(f"{fecha_inicio} {hora_inicio}", "%Y-%m-%d %H:%M").strftime('%Y-%m-%d %H:%M:%S')
    final = datetime.strptime(f"{fecha_final} {hora_final}", "%Y-%m-%d %H:%M").strftime('%Y-%m-%d %H:%M:%S')
    
    query = """
    WITH intervalos AS (
        SELECT 
            p.producto_id,
            pr.nombre_producto AS producto,
            DATE(p.fecha_hora) AS fecha,
            MIN(p.fecha_hora) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora)) AS primer_pesaje,
            MAX(p.fecha_hora) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora)) AS ultimo_pesaje,
            SUM(p.peso) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora)) AS total_peso,
            TIMESTAMPDIFF(MINUTE, p.fecha_hora, 
                        LEAD(p.fecha_hora) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora) ORDER BY p.fecha_hora)) AS intervalo_minutos
        FROM pesajes p
        JOIN productos pr ON p.producto_id = pr.producto_id
        WHERE p.fecha_hora BETWEEN %s AND %s
    )
    SELECT 
        fecha, producto,
        MIN(primer_pesaje) AS primer_pesaje,
        MAX(ultimo_pesaje) AS ultimo_pesaje,
        TIMESTAMPDIFF(HOUR, MIN(primer_pesaje), MAX(ultimo_pesaje)) AS horas_totales,
        ROUND(SUM(CASE 
                    WHEN intervalo_minutos >= 30 THEN 
                        CASE WHEN intervalo_minutos % 30 >= 15 THEN CEIL(intervalo_minutos / 30) * 0.5 
                             ELSE FLOOR(intervalo_minutos / 30) * 0.5 END
                    ELSE 0 END), 1) AS tiempo_muerto_horas,
        MAX(total_peso) AS total_peso_kg,
        SUM(MAX(total_peso)) OVER () AS total_general,
        COUNT(*) AS cantidad_pesajes
    FROM intervalos
    WHERE intervalo_minutos IS NOT NULL
    GROUP BY fecha, producto
    ORDER BY fecha, producto;
    """
    return execute_query(query, (inicio, final))

@app.route('/admin/reportes', methods=['GET', 'POST'])
@login_required
@admin_required
def reportes():
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data: return jsonify({"error": "No se recibieron datos"}), 400

            res = obtener_datos_reporte(
                data.get('fecha_inicio'), data.get('hora_inicio'),
                data.get('fecha_final'), data.get('hora_final')
            ) or []

            # Serializar fechas para JSON
            resultados_json = []
            for row in res:
                resultados_json.append({
                    "producto": row['producto'],
                    "primer_pesaje": row['primer_pesaje'].strftime("%d-%m-%Y %H:%M:%S"),
                    "ultimo_pesaje": row['ultimo_pesaje'].strftime("%d-%m-%Y %H:%M:%S"),
                    "cantidad_pesajes": row['cantidad_pesajes'],
                    "horas_totales": row['horas_totales'],
                    "tiempo_muerto_horas": row['tiempo_muerto_horas'],
                    "total_peso_kg": float(row['total_peso_kg']),
                    "total_general": float(row['total_general'])
                })

            return jsonify({"resultados": resultados_json})
        except Exception as e:
            return jsonify({"error": f"Error interno: {str(e)}"}), 500

    return render_template('reportes.html', resultados=[])

@app.route('/admin/reportes/pdf', methods=['GET'])
@login_required
@admin_required
def reportes_pdf():
    f_inicio = request.args.get('fecha_inicio')
    h_inicio = request.args.get('hora_inicio')
    f_final = request.args.get('fecha_final')
    h_final = request.args.get('hora_final')

    if not all([f_inicio, h_inicio, f_final, h_final]):
        flash("Los parámetros de fecha y hora son requeridos", "warning")
        return redirect('/admin/reportes')

    try:
        reportes = obtener_datos_reporte(f_inicio, h_inicio, f_final, h_final)
        
        if not reportes:
            flash("No hay datos para las fechas seleccionadas", "warning")
            return redirect('/admin/reportes')

        # Generación PDF con ReportLab
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        desde = datetime.strptime(f_inicio, "%Y-%m-%d").strftime('%d-%m-%Y')
        hasta = datetime.strptime(f_final, "%Y-%m-%d").strftime('%d-%m-%Y')

        def draw_headers(y_pos):
            logo_path = os.path.join(app.static_folder, 'png', 'logo.jpg')
            if os.path.exists(logo_path):
                p.drawImage(logo_path, 20, height - 65, width=76, height=50, mask='auto')
            
            p.setFont("Helvetica-Bold", 10)
            headers = ["Producto", "Primer Pesaje", "Último Pesaje", "Bolsas", "Duración (Hs)", "T. Muerto (Hs)", "Total KG"]
            positions = [20, 170, 250, 320, 370, 440, 530]
            for text, x in zip(headers, positions):
                p.drawString(x, y_pos, text)
            p.line(20, y_pos - 5, width - 20, y_pos - 5)

        # Primera página
        p.setFont("Helvetica", 14)
        p.drawString(100, height - 90, f"Reporte de Pesajes ({desde} al {hasta})")
        p.line(20, height - 110, 580, height - 110)
        
        y_position = height - 130
        draw_headers(y_position)
        y_position -= 20
        p.setFont("Helvetica", 10)

        for row in reportes:
            p.drawString(20, y_position, str(row['producto']))
            p.drawString(180, y_position, row['primer_pesaje'].strftime('%H:%M:%S'))
            p.drawString(260, y_position, row['ultimo_pesaje'].strftime('%H:%M:%S'))
            p.drawString(330, y_position, str(row['cantidad_pesajes']))
            p.drawString(385, y_position, str(row['horas_totales']))
            p.drawString(460, y_position, str(row['tiempo_muerto_horas']))
            p.drawString(535, y_position, str(row['total_peso_kg']))
            y_position -= 20

            if y_position < 50:
                p.showPage()
                y_position = height - 130
                draw_headers(y_position)
                y_position -= 20
                p.setFont("Helvetica", 10)

        # Total General
        total_general = reportes[0]['total_general'] if reportes and 'total_general' in reportes[0] else 0
        p.line(20, y_position, 580, y_position)
        y_position -= 20
        p.drawString(420, y_position, "TOTAL GENERAL (KG)")
        p.drawString(530, y_position, f"{total_general:.2f}")

        # Resumen por producto
        totales_por_producto = defaultdict(float)
        for row in reportes:
            totales_por_producto[row['producto']] += float(row['total_peso_kg'])
        
        y_position -= 40
        if y_position < 100:
            p.showPage()
            y_position = height - 50

        p.setFont("Helvetica-Bold", 12)
        p.drawString(20, y_position, "Resumen por Producto")
        p.line(20, y_position - 5, width - 20, y_position - 5)
        y_position -= 20
        p.setFont("Helvetica", 10)

        for prod, total in totales_por_producto.items():
            p.drawString(20, y_position, prod)
            p.drawString(530, y_position, f"{total:.2f}")
            y_position -= 20

        p.save()
        pdf_out = buffer.getvalue()
        buffer.close()

        response = make_response(pdf_out)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename=reportes.pdf'
        return response

    except Exception as e:
        flash(f"Error interno generando PDF: {str(e)}", "danger")
        return redirect('/admin/reportes')

# --- API DE DATOS (Realtime) ---

@app.route('/api/datos', methods=['GET'])
@login_required
def obtener_datos():
    # 1. Producto Actual
    actual = execute_query("""
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS nombre_producto, 
               ps.peso, ps.lote, ps.pesaje_id
        FROM pesajes ps
        JOIN productos p ON ps.producto_id = p.producto_id
        ORDER BY ps.fecha_hora DESC LIMIT 1;
    """, fetchone=True)

    # 2. Pesajes por Hora
    query_horas = """
        SELECT DATE_FORMAT(fecha_hora, '%Y-%m-%d %H:%i') AS tiempo, COUNT(*) AS total_bolsas 
        FROM (
            SELECT fecha_hora,
                CASE WHEN MINUTE(fecha_hora) < 30 THEN DATE_FORMAT(fecha_hora, '%Y-%m-%d %H:00')
                     ELSE DATE_FORMAT(fecha_hora, '%Y-%m-%d %H:30') END AS intervalo
            FROM pesajes WHERE DATE(fecha_hora) = CURDATE()
        ) AS subquery
        GROUP BY intervalo ORDER BY intervalo
    """
    horas_data = execute_query(query_horas) or []

    # 3. Rendimiento Empleados
    query_emp = """
        SELECT e.nombre AS empleado, COUNT(ps.pesaje_id) AS bolsas_producidas
        FROM pesajes ps
        JOIN empleados e ON ps.empleado_id = e.id
        WHERE DATE(ps.fecha_hora) = CURDATE()
        GROUP BY e.nombre ORDER BY bolsas_producidas DESC
    """
    emp_data = execute_query(query_emp) or []

    return jsonify({
        "producto_actual": actual['nombre_producto'] if actual else "No disponible",
        "pesaje_actual": actual['peso'] if actual else 0.0,
        "lote_actual": actual['lote'] if actual else "No disponible",
        "pesaje_id": actual['pesaje_id'] if actual else "No disponible",
        "tiempos": [x['tiempo'] for x in horas_data],
        "bolsas_por_hora": [x['total_bolsas'] for x in horas_data],
        "empleados": [x['empleado'] for x in emp_data],
        "rendimiento_empleados": [x['bolsas_producidas'] for x in emp_data]
    })

@app.route('/api/estadisticas', methods=['GET'])
@login_required
def obtener_estadisticas():
    # Datos externos
    hoja_verde = get_peso_total_hoja_verde()

    # Datos MySQL
    total_diario = execute_query("""
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_diario
        FROM pesajes ps JOIN productos p ON ps.producto_id = p.producto_id
        WHERE DATE(ps.fecha_hora) = CURDATE() GROUP BY producto
    """)

    total_mensual = execute_query("""
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_mensual
        FROM pesajes ps JOIN productos p ON ps.producto_id = p.producto_id
        WHERE MONTH(ps.fecha_hora) = MONTH(CURDATE()) AND YEAR(ps.fecha_hora) = YEAR(CURDATE())
        GROUP BY producto
    """)

    return jsonify({
        "total_diario": total_diario,
        "total_mensual": total_mensual,
        "total_hoja_verde_diario": hoja_verde["total_hoja_verde_diario"],
        "total_hoja_verde_mensual": hoja_verde["total_hoja_verde_mensual"]
    })

# --- BOKEH ROUTES ---

@app.route('/bokeh/pesajes')
@login_required
def bokeh_pesajes():
    # Obtener fecha del request (o usar hoy por defecto)
    fecha_param = request.args.get('fecha')
    if not fecha_param:
        fecha_str = date.today().strftime('%Y-%m-%d')
    else:
        fecha_str = fecha_param

    # Consulta filtrada por fecha
    data = execute_query("""
        SELECT DATE_FORMAT(fecha_hora, '%H:00') AS hora, SUM(peso) AS total_peso
        FROM pesajes WHERE DATE(fecha_hora) = %s
        GROUP BY hora ORDER BY hora
    """, (fecha_str,)) or []
    
    # Manejo de gráfico vacío si no hay datos
    if not data:
        mensaje = f"<div class='alert alert-warning text-center m-5'>No hay registros para la fecha: {fecha_str}</div>"
        return render_template("bokeh_template.html", script="", div=mensaje, resources="", titulo="Sin Datos")

    horas = [d['hora'] for d in data]
    pesos = [float(d['total_peso']) for d in data]

    source = ColumnDataSource(data=dict(horas=horas, pesos_hora=pesos))
    
    # Tooltips para mejor UX
    hover = HoverTool(tooltips=[("Hora", "@horas"), ("Kg", "@pesos_hora{0.00}")])
    
    p = figure(x_range=horas, height=350, title=f"Producción por Hora ({fecha_str})", 
               toolbar_location=None, tools=[hover])
    
    # CORRECCIÓN 1: Eliminamos 'legend_field="horas"' para que no cree la leyenda gigante que tapa el gráfico
    p.vbar(x='horas', top='pesos_hora', width=0.9, source=source, 
           line_color='white', fill_color=factor_cmap('horas', palette=Spectral11, factors=horas))
    
    p.xgrid.grid_line_color = None
    p.y_range.start = 0
    
    # CORRECCIÓN 2: Rotamos las etiquetas del eje X a vertical para evitar solapamiento entre horas
    p.xaxis.major_label_orientation = "vertical"
    
    script, div = components(p)
    return render_template("bokeh_template.html", script=script, div=div, resources=INLINE.render(), titulo="Gráfico Pesajes")

@app.route('/bokeh/rendimiento')
@login_required
def bokeh_rendimiento():
    data = execute_query("""
        SELECT e.nombre AS empleado, COUNT(ps.pesaje_id) AS bolsas_producidas
        FROM pesajes ps JOIN empleados e ON ps.empleado_id = e.id
        GROUP BY e.nombre ORDER BY bolsas_producidas DESC
    """) or []

    empleados = [d['empleado'] for d in data]
    bolsas = [float(d['bolsas_producidas']) for d in data]
    
    # Manejo seguro de paleta si hay más empleados que colores
    palette = Category20[20] if len(empleados) > 2 else ["#1f77b4", "#aec7e8"]
    if len(empleados) > 0 and len(empleados) <= 20:
        palette = Category20[len(empleados)]

    source = ColumnDataSource(data=dict(empleados=empleados, bolsas_producidas=bolsas))
    p = figure(x_range=empleados, height=350, title="Rendimiento por Empleado", toolbar_location=None, tools="")
    
    p.vbar(x='empleados', top='bolsas_producidas', width=0.9, source=source, legend_field="empleados",
           line_color='white', fill_color=factor_cmap('empleados', palette=palette, factors=empleados))

    p.xgrid.grid_line_color = None
    p.y_range.start = 0

    script, div = components(p)
    return render_template("bokeh_template.html", script=script, div=div, resources=INLINE.render(), titulo="Gráfico Rendimiento")

# --- DASH APP ---

def get_dash_data():
    data = execute_query("""
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_mensual
        FROM pesajes ps JOIN productos p ON ps.producto_id = p.producto_id
        WHERE MONTH(ps.fecha_hora) = MONTH(CURDATE()) AND YEAR(ps.fecha_hora) = YEAR(CURDATE())
        GROUP BY producto
    """)
    if not data: return None, None
    return [d['producto'] for d in data], [float(d['total_mensual']) for d in data]

dash_app.layout = html.Div([
    html.H1("Gráfica de Produccion Mensual por Producto", style={'textAlign': 'center'}),
    dcc.Dropdown(
        id='grafico-selector',
        options=[
            {'label': 'Gráfico de Torta', 'value': 'pie'},
            {'label': 'Barras Verticales', 'value': 'bar'},
            {'label': 'Barras Horizontal', 'value': 'barh'},
            {'label': 'Gráfico de linea', 'value': 'linea'},
            {'label': 'Gráfico de Dispersión', 'value': 'scatter'},
            {'label': 'Gráfico de Area', 'value': 'area'},
            {'label': 'Histograma', 'value': 'histo'},
        ],
        value='pie',
        clearable=False,
        style={'width': '50%', 'margin': 'auto'}
    ),
    dcc.Graph(id='grafico'),
])

@dash_app.callback(Output('grafico', 'figure'), Input('grafico-selector', 'value'))
def update_graph(tipo_grafico):
    productos, totales = get_dash_data()
    
    if productos is None:
        return px.pie(title="No hay datos para mostrar")

    df = pd.DataFrame({'productos': productos, 'totales': totales})
    color_sequence = px.colors.qualitative.Set1

    if tipo_grafico == 'pie':
        fig = px.pie(df, names='productos', values='totales', title='Total Mensual por Producto',
                     color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'bar':
        fig = px.bar(df, x='productos', y='totales', title='Total Mensual por Producto',
                     color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'barh':
        fig = px.bar(df, x='totales', y='productos', orientation='h', title='Total Mensual por Producto',
                     color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'scatter':
        fig = px.scatter(df, x='productos', y='totales', title='Total Mensual por Producto', size='totales',
                         color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'area':
        fig = px.area(df, x='productos', y='totales', title='Total Mensual por Producto',
                      color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'histo':
        fig = px.histogram(df, x='totales', title='Total Mensual por Producto',
                           color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'linea':
        fig = px.line(df, x='productos', y='totales', title='Total Mensual por Producto')
    
    return fig

if __name__ == '__main__':
    # Hilo de datos aleatorios REMOVIDO para producción/optimización.
    # Si lo necesitas para testing, descomenta las líneas correspondientes
    # en la versión original, pero se recomienda insertar datos manualmente o por script externo.
    app.run(debug=True, host='0.0.0.0', port=5000)