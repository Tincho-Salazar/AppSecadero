from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, make_response
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

def get_peso_total_hoja_verde():
    try:
        conn = get_sql_server_connection()
        if not conn: return {"total_hoja_verde_diario": 0, "total_hoja_verde_mensual": 0}
        cursor = conn.cursor()
        
        cursor.execute("SELECT SUM(pesoneto - pesotara) FROM ZTPESAJES WHERE CONVERT(DATE, LEFT(Fechaentrada, 8), 112) = CONVERT(DATE, GETDATE(), 112)")
        diario = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(pesoneto - pesotara) FROM ZTPESAJES WHERE MONTH(CONVERT(DATE, LEFT(Fechaentrada, 8), 112)) = MONTH(GETDATE()) AND YEAR(CONVERT(DATE, LEFT(Fechaentrada, 8), 112)) = YEAR(GETDATE())")
        mensual = cursor.fetchone()[0] or 0
        
        conn.close()
        return {"total_hoja_verde_diario": diario, "total_hoja_verde_mensual": mensual}
    except:
        return {"total_hoja_verde_diario": 0, "total_hoja_verde_mensual": 0}

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
    execute_query("INSERT INTO productos (nombre_producto, calidad, descripcion) VALUES (%s, %s, %s)",
                  (request.form['nombre'], request.form['calidad'], request.form['descripcion']), commit=True)
    return jsonify({'message': 'Producto creado'})

@app.route('/editar_producto/<int:id>', methods=['POST'])
def editar_producto(id):
    execute_query("UPDATE productos SET nombre_producto=%s, calidad=%s, descripcion=%s WHERE producto_id=%s",
                  (request.form['nombre'], request.form['calidad'], request.form['descripcion'], id), commit=True)
    return jsonify({'message': 'Producto actualizado'})

@app.route('/eliminar_producto/<int:id>', methods=['DELETE'])
def eliminar_producto(id):
    execute_query("DELETE FROM productos WHERE producto_id=%s", (id,), commit=True)
    return jsonify({'message': 'Producto eliminado'})

# --- REPORTES ---
def obtener_datos_reporte(fecha_inicio, hora_inicio, fecha_final, hora_final):
    """Lógica centralizada para la query compleja de reportes."""
    inicio = f"{fecha_inicio} {hora_inicio}"
    final = f"{fecha_final} {hora_final}"
    
    q = """
    WITH intervalos AS (
        SELECT p.producto_id, pr.nombre_producto AS producto, DATE(p.fecha_hora) AS fecha,
            MIN(p.fecha_hora) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora)) AS primer_pesaje,
            MAX(p.fecha_hora) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora)) AS ultimo_pesaje,
            SUM(p.peso) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora)) AS total_peso,
            TIMESTAMPDIFF(MINUTE, p.fecha_hora, LEAD(p.fecha_hora) OVER (PARTITION BY p.producto_id, DATE(p.fecha_hora) ORDER BY p.fecha_hora)) AS intervalo_minutos
        FROM pesajes p JOIN productos pr ON p.producto_id = pr.producto_id WHERE p.fecha_hora BETWEEN %s AND %s
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
            res = obtener_datos_reporte(
                d['fecha_inicio'], d['hora_inicio'],
                d['fecha_final'], d['hora_final']
            ) or []
            
            json_out = []
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
    f_inicio = request.args.get('fecha_inicio')
    h_inicio = request.args.get('hora_inicio')
    f_final = request.args.get('fecha_final')
    h_final = request.args.get('hora_final')

    if not all([f_inicio, h_inicio, f_final, h_final]):
        flash("Faltan parámetros", "warning")
        return redirect('/admin/reportes')

    try:
        reportes = obtener_datos_reporte(f_inicio, h_inicio, f_final, h_final) or []
        
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        def draw_headers(y):
            logo = os.path.join(app.static_folder, 'png', 'logo.jpg')
            if os.path.exists(logo):
                p.drawImage(logo, 20, height - 65, width=76, height=50, mask='auto')
            
            p.setFont("Helvetica-Bold", 10)
            headers = ["Producto", "Inicio", "Fin", "Bolsas", "Duración", "T. Muerto", "Total KG"]
            xs = [20, 180, 250, 320, 370, 440, 530]
            for t, x in zip(headers, xs): p.drawString(x, y, t)
            p.line(20, y - 5, width - 20, y - 5)

        y = height - 130
        p.setFont("Helvetica", 14)
        p.drawString(100, height - 90, f"Reporte: {f_inicio} al {f_final}")
        draw_headers(y)
        y -= 20
        p.setFont("Helvetica", 10)

        for r in reportes:
            p.drawString(20, y, str(r['producto'])[:30])
            p.drawString(180, y, r['primer_pesaje'].strftime('%H:%M'))
            p.drawString(250, y, r['ultimo_pesaje'].strftime('%H:%M'))
            p.drawString(320, y, str(r['cantidad_pesajes']))
            p.drawString(370, y, str(r['horas_totales']))
            p.drawString(440, y, str(r['tiempo_muerto_horas']))
            p.drawString(530, y, str(r['total_peso_kg']))
            y -= 20
            if y < 50:
                p.showPage()
                y = height - 50
                draw_headers(y)
                y -= 20
                p.setFont("Helvetica", 10)

        total_gen = reportes[0]['total_general'] if reportes else 0
        p.line(20, y, 580, y)
        y -= 20
        p.setFont("Helvetica-Bold", 10)
        p.drawString(400, y, "TOTAL GENERAL:")
        p.drawString(530, y, f"{total_gen:.2f}")
        
        p.save()
        pdf = buffer.getvalue()
        buffer.close()
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename=reporte.pdf'
        return response

    except Exception as e:
        print(f"Error PDF: {e}")
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
    td = execute_query("SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_diario FROM pesajes ps JOIN productos p ON ps.producto_id = p.producto_id WHERE DATE(ps.fecha_hora) = CURDATE() GROUP BY producto")
    tm = execute_query("SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_mensual FROM pesajes ps JOIN productos p ON ps.producto_id = p.producto_id WHERE MONTH(ps.fecha_hora) = MONTH(CURDATE()) AND YEAR(ps.fecha_hora) = YEAR(CURDATE()) GROUP BY producto")
    return jsonify({
        "total_diario": td or [], "total_mensual": tm or [],
        "total_hoja_verde_diario": hv['total_hoja_verde_diario'],
        "total_hoja_verde_mensual": hv['total_hoja_verde_mensual']
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
    html.Div([
        html.H3("Producción Mensual", className="text-center mb-4"),
        # Intervalo: 60 segundos
        dcc.Interval(id='intervalo-dash', interval=60*1000, n_intervals=0),
        html.Div([
            dcc.Dropdown(
                id='grafico-selector',
                options=[
                    {'label': 'Barras Horizontales (Ranking)', 'value': 'barh'},
                    {'label': 'Torta (Distribución)', 'value': 'pie'},
                    {'label': 'Barras Verticales', 'value': 'bar'}
                ],
                value='barh',
                clearable=False,
                className="mb-3"
            ),
            dcc.Graph(id='grafico')
        ], className="card shadow-sm p-3")
    ], className="container-fluid py-3")
])

@dash_app.callback(
    Output('grafico', 'figure'),
    [Input('grafico-selector', 'value'),
     Input('intervalo-dash', 'n_intervals')]
)
def update_graph(tipo, n):
    prods, totals = get_dash_data()
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
if __name__ == '__main__':
    # Eliminada simulación para entorno productivo
    if getattr(sys, 'frozen', False):
        print("INICIANDO MODO EJECUTABLE (PRODUCCIÓN)")
        app.run(debug=False, use_reloader=False, host='0.0.0.0', port=5000)
    else:
        print("INICIANDO MODO DESARROLLO")
        app.run(debug=True, host='0.0.0.0', port=5000)