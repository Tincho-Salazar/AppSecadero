from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file
import mysql.connector
import time
from werkzeug.security import generate_password_hash, check_password_hash
import random
import threading
import numpy as np
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.resources import INLINE
from bokeh.models import ColumnDataSource
from bokeh.transform import factor_cmap, cumsum
from bokeh.palettes import Spectral11, Category20
import decimal
from math import pi

import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd


# Inicializar la aplicación Flask
app = Flask(__name__)
app.secret_key = 'Datiles2044'  # Cambia esto por una clave secreta

dash_app = dash.Dash(__name__, server=app, url_base_pathname='/dash/')

# Variables globales de conexión a la base de datos
mydb = None

# Función para conectar a la base de datos MySQL sin pooling
def connect_to_db():
    try:
        connection = mysql.connector.connect(
            host="192.168.30.216",
            user="root",
            password="toor",
            database="secado",  # Asegúrate de que este sea el nombre correcto de la base de datos
            autocommit=True,
            connection_timeout=28800  # Timeout de conexión
        )
        if connection.is_connected():
            # print("Conexión exitosa a la base de datos")
            return connection
    except mysql.connector.Error as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None

# Función para ejecutar consultas SQL
def execute_query(connection, query, params=None, fetchone=False, commit=False):
    try:
        if connection is None or not connection.is_connected():
            print("Error: La conexión es None o no está activa. No se puede ejecutar la consulta.")
            return None

        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())  # Cambiado para usar params como tupla vacía si es None
        if commit:
            connection.commit()
        result = cursor.fetchone() if fetchone else cursor.fetchall()
        return result
    except mysql.connector.Error as err:
        print("Error MySQL:", err)
        if commit:
            connection.rollback()
        return None
    finally:
        cursor.close()  # Asegurarse de cerrar el cursor aquí

        
# Función para reconectar con varios intentos
def connect_with_retry(retries=5, delay=5):
    for _ in range(retries):
        connection = connect_to_db()
        if connection:
            return connection
        print(f"Reintentando conexión en {delay} segundos...")
        time.sleep(delay)
    print("No se pudo conectar a la base de datos después de varios intentos.")
    return None

# Función para mantener la conexión activa (Keep-Alive)
def keep_connection_alive(connection, interval=60):
    while True:
        try:
            if not connection or not connection.is_connected():
                print("Conexión perdida. Intentando reconectar...")
                connection = connect_with_retry()
            else:
                connection.ping(reconnect=True, attempts=3, delay=5)
                # print("Conexión verificada y activa.")
        except mysql.connector.Error as e:
            print(f"Error en keep-alive: {e}")
            connection = connect_with_retry()
        time.sleep(interval)

    try:
        if connection is None or not connection.is_connected():
            print("Error: La conexión es None o no está activa. No se puede ejecutar la consulta.")
            return None

        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params)
        if commit:
            connection.commit()
        result = cursor.fetchone() if fetchone else cursor.fetchall()
        cursor.close()
        return result
    except mysql.connector.Error as err:
        print("Error MySQL:", err)
        if commit:
            connection.rollback()
        return None

# Iniciar conexión y keep-alive
mydb = connect_with_retry()
if mydb:
    keep_alive_thread = threading.Thread(target=keep_connection_alive, args=(mydb,))
    keep_alive_thread.daemon = True
    keep_alive_thread.start()

# Decorador para verificar si el usuario está autenticado
def login_required(f):
    def wrap(*args, **kwargs):
        if 'usuario' not in session:
            flash("Por favor, inicia sesión primero", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# Decorador para verificar si el usuario es ADMINISTRADOR
def admin_required(f):
    def wrap(*args, **kwargs):
        if session.get('rol') != 'ADMINISTRADOR':
            flash("Acceso denegado. Debes ser ADMINISTRADOR", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# Ruta principal
@app.route('/')
@login_required
def index():
    return render_template('index.html')

# Ruta para login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        contrasena = request.form['contrasena']
        connection = connect_to_db()

        query = "SELECT * FROM usuarios WHERE usuario = %s"
        resultado = execute_query(connection, query, (usuario,), fetchone=True)

        if resultado and check_password_hash(resultado['contrasena'], contrasena):
            session['usuario'] = resultado['usuario']
            session['rol'] = resultado['rol']
            return jsonify({'status': 'success', 'redirect': url_for('index')})
        else:
            return jsonify({'status': 'error', 'message': 'Usuario o contraseña incorrectos'})

    return render_template('login.html')

# Ruta para CRUD de usuarios (solo ADMINISTRADOR)
@app.route('/admin/usuarios', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar_usuarios():
    connection = connect_to_db()
    query = "SELECT * FROM usuarios"
    usuarios = execute_query(connection, query)
    return render_template('usuario.html', usuarios=usuarios)

# Ruta para CRUD de productos (solo ADMINISTRADOR)
@app.route('/admin/productos', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar_productos():
    connection = connect_to_db()
    query = "SELECT * FROM productos"
    productos = execute_query(connection, query)
    return render_template('productos.html', productos=productos)

# Ruta para cerrar sesión
@app.route('/logout')
@login_required
def logout():
    session.pop('usuario', None)
    session.pop('rol', None)
    flash("Has cerrado sesión con éxito", "success")
    return redirect(url_for('login'))

# Ruta para registrar usuarios
@app.route('/admin/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        new_username = request.form['new_usuario']
        new_password = request.form['new_contrasena']
        hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')
        rol = 'USUARIO'

        connection = connect_to_db()
        if connection is None:
            flash("Error al conectar a la base de datos", "danger")
            return redirect(url_for('register'))

        check_user_query = "SELECT COUNT(*) FROM usuarios WHERE usuario = %s"
        existing_user = execute_query(connection, check_user_query, (new_username,), fetchone=True)

        if existing_user and existing_user['COUNT(*)'] > 0:
            return jsonify({"message": "nombre de usuario ya está registrado."})

        insert_user_query = "INSERT INTO usuarios (usuario, contrasena, rol) VALUES (%s, %s, %s)"
        execute_query(connection, insert_user_query, (new_username, hashed_password, rol), commit=True)
        
        return jsonify({"message": "Registro exitoso"}), 200

    return render_template('register.html')

# Ruta para la obtención de los datos en tiempo real para actualizar la UI
# Modificación en la función obtener_datos
@app.route('/api/datos', methods=['GET'])
@login_required
def obtener_datos():
    connection = connect_to_db()
    if connection is None:
        return jsonify({"error": "Error en la conexión a la base de datos"}), 500

    # Consulta para obtener el producto y pesaje actual
    query_producto_pesaje = """
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS nombre_producto, ps.peso 
        FROM pesajes ps
        JOIN productos p ON ps.producto_id = p.producto_id
        ORDER BY ps.fecha_hora DESC LIMIT 1
    """
    resultado = execute_query(connection, query_producto_pesaje, fetchone=True)

    producto_actual = resultado['nombre_producto'] if resultado else "No disponible"
    pesaje_actual = resultado['peso'] if resultado else 0.0

    # Consulta para obtener los pesajes por cada 1/2 hora
    query_pesajes_hora = """
       SELECT DATE_FORMAT(fecha_hora, '%Y-%m-%d %H:%i') AS tiempo, 
            COUNT(*) AS total_bolsas FROM (
            SELECT 
                fecha_hora,
                CASE
                    WHEN MINUTE(fecha_hora) < 30 THEN DATE_FORMAT(fecha_hora, '%Y-%m-%d %H:00')
                    ELSE DATE_FORMAT(fecha_hora, '%Y-%m-%d %H:30')
                END AS intervalo
            FROM pesajes
            WHERE DATE(fecha_hora) = CURDATE()
        ) AS subquery
        GROUP BY intervalo
        ORDER BY intervalo
    """
    pesajes_por_hora = execute_query(connection, query_pesajes_hora)
    tiempos = [fila['tiempo'] for fila in pesajes_por_hora] if pesajes_por_hora else []
    bolsas_hora = [fila['total_bolsas'] for fila in pesajes_por_hora] if pesajes_por_hora else []

    # Consulta para obtener el rendimiento por empleado (cantidad de bolsas)
    query_rendimiento_empleado = """
        SELECT e.nombre AS empleado, COUNT(ps.pesaje_id) AS bolsas_producidas
        FROM pesajes ps
        JOIN empleados e ON ps.empleado_id = e.id
        WHERE DATE(ps.fecha_hora) = CURDATE()
        GROUP BY e.nombre
        ORDER BY bolsas_producidas DESC
    """
    rendimiento_empleados = execute_query(connection, query_rendimiento_empleado)
    empleados = [fila['empleado'] for fila in rendimiento_empleados] if rendimiento_empleados else []
    rendimiento = [fila['bolsas_producidas'] for fila in rendimiento_empleados] if rendimiento_empleados else []

    # Retornar toda la información como JSON para los gráficos
    return jsonify({
        "producto_actual": producto_actual,
        "pesaje_actual": pesaje_actual,
        "tiempos": tiempos,
        "bolsas_por_hora": bolsas_hora,
        "empleados": empleados,
        "rendimiento_empleados": rendimiento
    }), 200
# Nueva ruta para obtener estadísticas del total diario y mensual por producto
@app.route('/api/estadisticas', methods=['GET'])
@login_required
def obtener_estadisticas():
    connection = connect_to_db()

    # Verifica si la conexión es exitosa
    if connection is None:
        return jsonify({"error": "Error en la conexión a la base de datos"}), 500

    # Totales diarios por producto
    query_total_diario = """
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_diario
        FROM pesajes ps
        JOIN productos p ON ps.producto_id = p.producto_id
        WHERE DATE(ps.fecha_hora) = CURDATE()
        GROUP BY producto
    """
    total_diario = execute_query(connection, query_total_diario)  # Pasar la conexión aquí

    # Totales mensuales por producto
    query_total_mensual = """
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_mensual
        FROM pesajes ps
        JOIN productos p ON ps.producto_id = p.producto_id
        WHERE MONTH(ps.fecha_hora) = MONTH(CURDATE()) AND YEAR(ps.fecha_hora) = YEAR(CURDATE())
        GROUP BY producto;
    """
    total_mensual = execute_query(connection, query_total_mensual)  # Pasar la conexión aquí
 
    return jsonify({
        "total_diario": total_diario,
        "total_mensual": total_mensual,
    })

# Ruta para el gráfico de pesajes usando Bokeh
@app.route('/bokeh/pesajes')
@login_required
def bokeh_pesajes():
    connection = connect_to_db()
    query_pesajes_hora = """
        SELECT 
            DATE_FORMAT(ps.fecha_hora, '%H:00') AS hora, 
            SUM(ps.peso) AS total_peso
        FROM pesajes ps
        GROUP BY hora
        ORDER BY hora
    """
    pesajes_por_hora = execute_query(connection, query_pesajes_hora)
    horas = [fila['hora'] for fila in pesajes_por_hora]
    pesos_hora = [float(fila['total_peso']) for fila in pesajes_por_hora]

    source = ColumnDataSource(data=dict(horas=horas, pesos_hora=pesos_hora))
    p = figure(x_range=horas, height=350, title="Pesajes por Hora", toolbar_location=None, tools="")
    p.vbar(x='horas', top='pesos_hora', width=0.9, source=source, legend_field="horas",
           line_color='white', fill_color=factor_cmap('horas', palette=Spectral11, factors=horas))

    p.xgrid.grid_line_color = None
    p.y_range.start = 0

    script, div = components(p)
    return render_template("bokeh_template.html", script=script, div=div, resources=INLINE.render(), titulo="Gráfico Pesajes")

# Ruta para el gráfico de Rendimiento por Empleado usando Bokeh
@app.route('/bokeh/rendimiento')
@login_required
def bokeh_rendimiento():
    connection = connect_to_db()
    query_rendimiento_empleado = """
        SELECT e.nombre AS empleado, COUNT(ps.pesaje_id) AS bolsas_producidas
        FROM pesajes ps
        JOIN empleados e ON ps.empleado_id = e.id
        GROUP BY e.nombre
        ORDER BY bolsas_producidas DESC
    """
    rendimiento_empleados = execute_query(connection, query_rendimiento_empleado)
    empleados = [fila['empleado'] for fila in rendimiento_empleados]
    bolsas_producidas = [float(fila['bolsas_producidas']) for fila in rendimiento_empleados]

    source = ColumnDataSource(data=dict(empleados=empleados, bolsas_producidas=bolsas_producidas))
    p = figure(x_range=empleados, height=350, title="Rendimiento por Empleado", toolbar_location=None, tools="")
    p.vbar(x='empleados', top='bolsas_producidas', width=0.9, source=source, legend_field="empleados",
           line_color='white', fill_color=factor_cmap('empleados', palette=Category20[len(empleados)], factors=empleados))

    p.xgrid.grid_line_color = None
    p.y_range.start = 0

    script, div = components(p)
    return render_template("bokeh_template.html", script=script, div=div, resources=INLINE.render(), titulo="Gráfico Rendimiento")


def get_data():
    connection = connect_to_db()
    query_total_mensual = """
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, CAST(SUM(ps.peso) AS DOUBLE) AS total_mensual
        FROM pesajes ps
        JOIN productos p ON ps.producto_id = p.producto_id
        WHERE MONTH(ps.fecha_hora) = MONTH(CURDATE()) AND YEAR(ps.fecha_hora) = YEAR(CURDATE())
        GROUP BY producto
    """
    total_mensual = execute_query(connection, query_total_mensual)

    if not total_mensual:
        print("No se encontraron datos para el gráfico.")
        return None

    # Convertir nombres de productos y valores a tipo adecuado
    productos = [fila['producto'] for fila in total_mensual]
    totales = [float(fila['total_mensual']) for fila in total_mensual]

    return productos, totales

# Definir el layout de la aplicación Dash
dash_app.layout = html.Div([
    html.H1("Gráfica de Produccion Mensual por Producto"),
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
        value='pie',  # Valor predeterminado
        clearable=False,
        style={
            'width': '50%',
            'margin': 'auto'
        }
    ),
    dcc.Graph(id='grafico'),
])

# Callback para actualizar el gráfico
@dash_app.callback(
    Output('grafico', 'figure'),
    Input('grafico-selector', 'value')
)

def update_graph(tipo_grafico):
    productos, totales = get_data()
    
    if productos is None:
        return px.pie(title="No hay datos para mostrar")  # Manejo de errores

    # Crear un DataFrame para facilitar la visualización
    df = pd.DataFrame({'productos': productos, 'totales': totales})

    # Definir la paleta de colores
    color_sequence = px.colors.qualitative.Set1  # Puedes cambiar la paleta aquí

    if tipo_grafico == 'pie':
        # Crear un gráfico de torta
        fig = px.pie(df, names='productos', values='totales', title='Total Mensual por Producto',
                     color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'bar':
        # Crear un gráfico de barras
        fig = px.bar(df, x='productos', y='totales', title='Total Mensual por Producto',
                     color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'barh':
        # Crear un gráfico de barras horizontales
        fig = px.bar(df, x='totales', y='productos', orientation='h', title='Total Mensual por Producto',
                     color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'scatter':
        # Crear un gráfico de dispersión
        fig = px.scatter(df, x='productos', y='totales', title='Total Mensual por Producto', size='totales',
                         color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'area':
        # Crear un gráfico de área
        fig = px.area(df, x='productos', y='totales', title='Total Mensual por Producto',
                      color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'histo':
        # Crear un gráfico de histograma
        fig = px.histogram(df, x='totales', title='Total Mensual por Producto',
                           color='productos', color_discrete_sequence=color_sequence)
    elif tipo_grafico == 'linea':
        # Crear un gráfico de líneas
        fig = px.line(df, x='productos', y='totales', title='Total Mensual por Producto',
                      )

    return fig


# Rutina para cargar datos aleatorios cada 5 minutos
pesajes_generados = 0
producto_actual = None
empleado_actual = None
lote_actual = 1

# Función para cargar datos aleatorios
def cargar_datos_aleatorios():
    global pesajes_generados, producto_actual, empleado_actual, lote_actual

    # Intentar reconectar antes de ejecutar cualquier operación de base de datos
    connection = connect_to_db()  # Cambiado para conectarse cada vez
    if connection is None:
        print("Error en la conexión a la base de datos, no se pueden cargar datos.")
        return

    productos_query = "SELECT producto_id, nombre_producto FROM productos"
    empleados_query = "SELECT id, nombre FROM empleados"
    productos = execute_query(connection, productos_query)
    empleados = execute_query(connection, empleados_query)

    # Verificar si hay productos y empleados en la base de datos
    if not productos or not empleados:
        print("No hay productos o empleados cargados en la base de datos.")
        return

    productos_ids = {prod['producto_id']: prod['nombre_producto'] for prod in productos}
    empleados_ids = {emp['id']: emp['nombre'] for emp in empleados}

    if producto_actual is None:
        producto_actual = random.choice(list(productos_ids.keys()))
    if empleado_actual is None:
        empleado_actual = random.choice(list(empleados_ids.keys()))

    peso_aleatorio = round(random.uniform(1, 100), 2)

    insert_pesaje_query = """
        INSERT INTO pesajes (producto_id, peso, lote, empleado_id, fecha_hora)
        VALUES (%s, %s, %s, %s, NOW())
    """
    try:
        # Insertar los datos aleatorios en la base de datos
        execute_query(connection, insert_pesaje_query, (producto_actual, peso_aleatorio, lote_actual, empleado_actual), commit=True)
        pesajes_generados += 1

        # Cambiar de producto y lote cada 250 pesajes
        if pesajes_generados % 250 == 0:
            producto_actual = random.choice(list(productos_ids.keys()))
            empleado_actual = random.choice(list(empleados_ids.keys()))
            lote_actual += 1
            print(f"Producto cambiado a {productos_ids[producto_actual]}, nuevo lote: {lote_actual}")

    except mysql.connector.Error as err:
        print("Error al insertar datos aleatorios:", err)

# Función para iniciar la carga de datos en segundo plano
def iniciar_carga_datos():
    while True:
        cargar_datos_aleatorios()
        time.sleep(300)  # Pausar por 5 minutos

# Iniciar el hilo en segundo plano
data_thread = threading.Thread(target=iniciar_carga_datos)
data_thread.daemon = True  # Hilo en segundo plano que se detiene cuando se cierra la app
data_thread.start()






# Iniciar la app Flask
if __name__ == '__main__':
    app.run(debug=True)
