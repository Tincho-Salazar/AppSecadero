from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response
import mysql.connector
import pyodbc
import time
from datetime import datetime, date, timedelta
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
from reportlab.lib.pagesizes import letter,A4
from reportlab.pdfgen import canvas
import pandas as pd
from io import BytesIO
from collections import defaultdict

import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd
import os


# Inicializar la aplicación Flask
app = Flask(__name__)
app.secret_key = 'Datiles2044'  # Cambia esto por una clave secreta
app._static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app._template_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

dash_app = dash.Dash(__name__, server=app, url_base_pathname='/dash/')

# Variables globales de conexión a la base de datos
mydb = None


def connect_to_sql_server():
    db_config = {
        'server': '192.168.30.5\\prd',
        'database': 'SAPINFO',
        'username': 'laichi',
        'password': 'datiles2044pera%%%'
    }

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={db_config['server']};"
        f"DATABASE={db_config['database']};"
        f"UID={db_config['username']};"
        f"PWD={db_config['password']};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )

    return pyodbc.connect(conn_str)
#Lectura de los datos de Yerba entrada desde Sql Server
def get_peso_total_hoja_verde():
    try:
        conn = connect_to_sql_server()
        cursor = conn.cursor()

        # Consulta diaria para "Hoja Verde"
        query_hoja_verde_diario = """
            SELECT SUM(pesoneto - pesotara) AS total_hoja_verde_diario
            FROM ZTPESAJES
            WHERE CONVERT(DATE, LEFT(Fechaentrada, 8), 112) = CONVERT(DATE, GETDATE(), 112)
        """
        cursor.execute(query_hoja_verde_diario)
        hoja_verde_diario_result = cursor.fetchone()
        hoja_verde_diario = hoja_verde_diario_result[0] if hoja_verde_diario_result and hoja_verde_diario_result[0] else 0

        # Consulta mensual para "Hoja Verde"
        query_hoja_verde_mensual = """
            SELECT SUM(pesoneto - pesotara) AS total_hoja_verde_mensual
            FROM ZTPESAJES
            WHERE MONTH(CONVERT(DATE, LEFT(Fechaentrada, 8), 112)) = MONTH(GETDATE())
              AND YEAR(CONVERT(DATE, LEFT(Fechaentrada, 8), 112)) = YEAR(GETDATE())
        """
        cursor.execute(query_hoja_verde_mensual)
        hoja_verde_mensual_result = cursor.fetchone()
        hoja_verde_mensual = hoja_verde_mensual_result[0] if hoja_verde_mensual_result and hoja_verde_mensual_result[0] else 0

        return {
            "total_hoja_verde_diario": hoja_verde_diario,
            "total_hoja_verde_mensual": hoja_verde_mensual
        }

    except Exception as e:
        print(f"Error al obtener los datos de Hoja Verde: {e}")
        return {
            "total_hoja_verde_diario": 0,
            "total_hoja_verde_mensual": 0
        }
    finally:
        conn.close()




# Función para conectar a la base de datos MySQL sin pooling
def connect_to_db():
    try:
        connection = mysql.connector.connect(
            host="192.168.37.114",
            user="consultaDB",
            password="cPindo2024",
            database="bolsas",  # Asegúrate de que este sea el nombre correcto de la base de datos
            autocommit=True,
            charset="utf8mb4",
            collation="utf8mb4_general_ci",
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
    if not connection:
        flash("No se pudo conectar a la base de datos", "danger")
        return render_template('usuario.html', usuarios=[])
    
    query = "SELECT * FROM usuarios"
    usuarios = execute_query(connection, query)
    
    if not usuarios:
        print("No se encontraron usuarios en la base de datos.")  # Agrega esta línea para verificar
    else:
        print("Usuarios encontrados:", usuarios)  # Imprime los usuarios encontrados

    return render_template('usuario.html', usuarios=usuarios)

# Eliminacion de usuarios
@app.route('/eliminar_usuario/<int:id>', methods=['DELETE'])
def eliminar_usuario(id):
    sql = 'DELETE FROM usuarios WHERE id = %s'
    val = (id,)
    execute_query(mydb, sql, params=val, commit=True)

    return jsonify({'message': 'Usuario eliminado exitosamente'})

@app.route('/crear_usuario', methods=['POST'])
def crear_usuario():
    usuario = request.form['usuario']
    contrasena = request.form['contrasena']
    rol = request.form['rol']

    hashed_password = generate_password_hash(contrasena, method='pbkdf2:sha256')
    
    sql = 'INSERT INTO usuarios (usuario, contrasena, rol) VALUES (%s, %s, %s)'
    val = (usuario, hashed_password, rol)
    execute_query(mydb, sql, params=val, commit=True)
    
    return jsonify({'message': 'Usuario creado exitosamente'})

@app.route('/editar_usuario/<int:id>', methods=['POST'])
def editar_usuario(id):
    usuario = request.form['usuario']
    contrasena = request.form['contrasena']
    rol = request.form['rol']

    hashed_password = generate_password_hash(contrasena, method='pbkdf2:sha256')
    
    sql = 'UPDATE usuarios SET usuario = %s, contrasena = %s, rol = %s WHERE id = %s'
    val = (usuario, hashed_password, rol, id)
    execute_query(mydb, sql, params=val, commit=True)
    
    return jsonify({'message': 'Usuario actualizado exitosamente'})

# Ruta para CRUD de empleados (solo ADMINISTRADOR)
@app.route('/admin/empleados', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar_empleados():
    connection = connect_to_db()
    if not connection:
        flash("No se pudo conectar a la base de datos", "danger")
        return render_template('empleado.html', empleados=[])
    
    query = "SELECT * FROM empleados"
    empleados = execute_query(connection, query)
    
    if not empleados:
        print("No se encontraron empleados en la base de datos.")  # Agrega esta línea para verificar
    else:
        print("empleados encontrados:", empleados)  # Imprime los empleados encontrados

    return render_template('empleado.html', empleados=empleados)

# Eliminacion de empleados
@app.route('/eliminar_empleado/<int:id>', methods=['DELETE'])
def eliminar_empleado(id):
    sql = 'DELETE FROM empleados WHERE id = %s'
    val = (id,)
    execute_query(mydb, sql, params=val, commit=True)

    return jsonify({'message': 'empleado eliminado exitosamente'})

@app.route('/crear_empleado', methods=['POST'])
def crear_empleado():
    nombre = request.form['empleado']  # Cambia 'empleado' por 'nombre'
    puesto = request.form['rol']       # Cambia 'rol' por 'puesto'

    sql = 'INSERT INTO empleados (nombre, puesto) VALUES (%s, %s)'
    val = (nombre, puesto)  # Solo usa nombre y puesto, elimina hashed_password
    execute_query(mydb, sql, params=val, commit=True)

    return jsonify({'message': 'Empleado creado exitosamente'})

@app.route('/editar_empleado/<int:id>', methods=['POST'])
def editar_empleado(id):
    nombre = request.form['empleado']  # Cambia 'empleado' por 'nombre'
    puesto = request.form['rol']       # Cambia 'rol' por 'puesto'

    sql = 'UPDATE empleados SET nombre = %s, puesto = %s WHERE id = %s'
    val = (nombre, puesto, id)
    execute_query(mydb, sql, params=val, commit=True)

    return jsonify({'message': 'Empleado actualizado exitosamente'})



# Ruta para CRUD de productos (solo ADMINISTRADOR)
@app.route('/admin/productos', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar_productos():
    connection = connect_to_db()
    if not connection:
        flash("No se pudo conectar a la base de datos", "danger")
        return render_template('productos.html', productos=[])
    
    query = "SELECT * FROM productos"
    productos = execute_query(connection, query)
    
    if not productos:
        print("No se encontraron productos en la base de datos.")
    else:
        print("Productos encontrados:", productos)

    return render_template('productos.html', productos=productos)

# Crear nuevo producto
@app.route('/crear_producto', methods=['POST'])
@login_required
@admin_required
def crear_producto():
    nombre = request.form['nombre']
    calidad = request.form['calidad']
    descripcion = request.form['descripcion']  # Nuevo campo descripción

    sql = 'INSERT INTO productos (nombre_producto, calidad, descripcion) VALUES (%s, %s, %s)'
    val = (nombre, calidad, descripcion)
    execute_query(mydb, sql, params=val, commit=True)
    
    return jsonify({'message': 'Producto creado exitosamente'})

# Editar producto existente
@app.route('/editar_producto/<int:id>', methods=['POST'])
@login_required
@admin_required
def editar_producto(id):
    nombre = request.form['nombre']
    calidad = request.form['calidad']
    descripcion = request.form['descripcion']  # Nuevo campo descripción

    sql = 'UPDATE productos SET nombre_producto = %s, calidad = %s, descripcion = %s WHERE producto_id = %s'
    val = (nombre, calidad, descripcion, id)
    execute_query(mydb, sql, params=val, commit=True)
    
    return jsonify({'message': 'Producto actualizado exitosamente'})

# Eliminar producto
@app.route('/eliminar_producto/<int:id>', methods=['DELETE'])
@login_required
@admin_required
def eliminar_producto(id):
    sql = 'DELETE FROM productos WHERE producto_id = %s'
    val = (id,)
    execute_query(mydb, sql, params=val, commit=True)

    return jsonify({'message': 'Producto eliminado exitosamente'})


# Modificaciones para incluir los nuevos datos en el reporte
@app.route('/admin/reportes', methods=['GET', 'POST'])
@login_required
@admin_required
def reportes():
    connection = connect_to_db()
    if connection is None:
        flash("Error al conectar a la base de datos", "danger")
        return render_template('reportes.html', resultados=[])

    if request.method == 'POST':
        try:
            data = request.get_json()

            if not data:
                return jsonify({"error": "No se recibieron datos"}), 400

            fecha_inicio = data.get('fecha_inicio')
            hora_inicio = data.get('hora_inicio')
            fecha_final = data.get('fecha_final')
            hora_final = data.get('hora_final')

            if not fecha_inicio or not fecha_final or not hora_inicio or not hora_final:
                return jsonify({"error": "Faltan parámetros"}), 400

            inicio = datetime.strptime(f"{fecha_inicio} {hora_inicio}", "%Y-%m-%d %H:%M")
            final = datetime.strptime(f"{fecha_final} {hora_final}", "%Y-%m-%d %H:%M")

            inicio_str = inicio.strftime('%Y-%m-%d %H:%M:%S')
            final_str = final.strftime('%Y-%m-%d %H:%M:%S')

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
                FROM 
                    pesajes p
                JOIN 
                    productos pr ON p.producto_id = pr.producto_id
                WHERE 
                    p.fecha_hora BETWEEN %s AND %s
            )
            SELECT 
                fecha,
                producto,
                MIN(primer_pesaje) AS primer_pesaje,
                MAX(ultimo_pesaje) AS ultimo_pesaje,
                TIMESTAMPDIFF(HOUR, MIN(primer_pesaje), MAX(ultimo_pesaje)) AS horas_totales,
                ROUND(
                    SUM(
                        CASE 
                            WHEN intervalo_minutos >= 30 THEN 
                                CASE 
                                    WHEN intervalo_minutos % 30 >= 15 THEN CEIL(intervalo_minutos / 30) * 0.5 
                                    ELSE FLOOR(intervalo_minutos / 30) * 0.5 
                                END
                            ELSE 0 
                        END
                    ), 1) AS tiempo_muerto_horas,
                MAX(total_peso) AS total_peso_kg,
                SUM(MAX(total_peso)) OVER () AS total_general,
                COUNT(*) AS cantidad_pesajes
            FROM 
                intervalos
            WHERE 
                intervalo_minutos IS NOT NULL
            GROUP BY 
                fecha, producto
            ORDER BY 
                fecha, producto;
            """

            reportes = execute_query(connection, query, (inicio_str, final_str))

            resultados_json = []
            for row in reportes:
                
                resultados_json.append({
                    "producto": row['producto'],
                    "primer_pesaje": row['primer_pesaje'].strftime("%d-%m-%Y %H:%M:%S") ,
                    "ultimo_pesaje": row['ultimo_pesaje'].strftime("%d-%m-%Y %H:%M:%S") ,
                    "cantidad_pesajes": row['cantidad_pesajes'],
                    "horas_totales": row['horas_totales'],
                    "tiempo_muerto_horas": row['tiempo_muerto_horas'],
                    "total_peso_kg": row['total_peso_kg'],
                    "total_general": row['total_general']
                })

            return jsonify({"resultados": resultados_json})

        except Exception as e:
            return jsonify({"error": f"Error interno: {str(e)}"}), 500

    return render_template('reportes.html', resultados=[])



# Ruta para generar el reporte PDF
@app.route('/admin/reportes/pdf', methods=['GET'])
@login_required
@admin_required
def reportes_pdf():
    connection = connect_to_db()
    if connection is None:
        flash("Error al conectar a la base de datos", "danger")
        return redirect('/admin/reportes')

    fecha_inicio = request.args.get('fecha_inicio')
    hora_inicio = request.args.get('hora_inicio')
    fecha_final = request.args.get('fecha_final')
    hora_final = request.args.get('hora_final')
    print(fecha_inicio)
    print(fecha_final)
    
    # Validar que los parámetros no están vacíos
    if not fecha_inicio or not hora_inicio or not fecha_final or not hora_final:
        flash("Los parámetros de fecha y hora son requeridos", "warning")
        return redirect('/admin/reportes')
    
    try:
        inicio = datetime.strptime(f"{fecha_inicio} {hora_inicio}", "%Y-%m-%d %H:%M")
        final = datetime.strptime(f"{fecha_final} {hora_final}", "%Y-%m-%d %H:%M")
        inicio_str = inicio.strftime('%Y-%m-%d %H:%M:%S')
        final_str = final.strftime('%Y-%m-%d %H:%M:%S')
        desde = inicio.strftime('%d-%m-%Y')
        hasta = final.strftime('%d-%m-%Y')
        
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
                FROM 
                    pesajes p
                JOIN 
                    productos pr ON p.producto_id = pr.producto_id
                WHERE 
                    p.fecha_hora BETWEEN %s AND %s
            )
            SELECT 
                fecha,
                producto,
                MIN(primer_pesaje) AS primer_pesaje,
                MAX(ultimo_pesaje) AS ultimo_pesaje,
                TIMESTAMPDIFF(HOUR, MIN(primer_pesaje), MAX(ultimo_pesaje)) AS horas_totales,
                ROUND(
                    SUM(
                        CASE 
                            WHEN intervalo_minutos >= 30 THEN 
                                CASE 
                                    WHEN intervalo_minutos % 30 >= 15 THEN CEIL(intervalo_minutos / 30) * 0.5 
                                    ELSE FLOOR(intervalo_minutos / 30) * 0.5 
                                END
                            ELSE 0 
                        END
                    ), 1) AS tiempo_muerto_horas,
                MAX(total_peso) AS total_peso_kg,
                SUM(MAX(total_peso)) OVER () AS total_general,
                COUNT(*) AS cantidad_pesajes  -- Nueva columna
            FROM 
                intervalos
            WHERE 
                intervalo_minutos IS NOT NULL
            GROUP BY 
                fecha, producto
            ORDER BY 
                fecha, producto;
        """

        reportes = execute_query(connection, query, (inicio_str, final_str))

        if not reportes:
            flash("No hay datos para las fechas seleccionadas", "warning")
            return redirect('/admin/reportes')

        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        def draw_headers(y_position):
            """Dibuja los encabezados en cada página con el logo"""
            logo_path = 'static/png/logo.jpg'
            try:
                p.drawImage(logo_path, 20, height - 65, width=76, height=50, mask='auto')
            except Exception as e:
                print(f"Error al cargar el logo: {e}")
            
            p.setFont("Helvetica-Bold", 10)
            """Dibuja los encabezados en cada página"""
            p.setFont("Helvetica-Bold", 10)
            headers = ["Producto", "Primer Pesaje", "Último Pesaje", "Bolsas", "Duración (Hs)", "T. Muerto (Hs)", "Total KG"]
            positions = [20, 170, 250, 320, 370, 440, 530]
            for text, x in zip(headers, positions):
                p.drawString(x, y_position, text)
            p.line(20, y_position - 5, width - 20, y_position - 5)

        # Título del reporte
        p.setFont("Helvetica", 14)
        p.drawString(100, height - 90, f"Reporte de Pesajes ({desde} al {hasta})")
        p.line(20, height - 110, 580, height - 110)
        y_position = height - 130
        draw_headers(y_position)
        y_position -= 20
        p.setFont("Helvetica", 10)

        # Datos
        y_position = height - 150
        for row in reportes:
            producto = row['producto']
            primer_pesaje = row['primer_pesaje'].strftime('%H:%M:%S')
            ultimo_pesaje = row['ultimo_pesaje'].strftime('%H:%M:%S')
            bolsa_pesaje = str(row['cantidad_pesajes'])
            horas_totales = str(row['horas_totales'])
            tiempo_muerto_horas = str(row['tiempo_muerto_horas'])
            total_peso_kg = str(row['total_peso_kg'])
            # y_position-= 15

            p.drawString(20, y_position, producto)
            p.drawString(180, y_position, primer_pesaje)
            p.drawString(260, y_position, ultimo_pesaje)
            p.drawString(330, y_position, bolsa_pesaje)
            p.drawString(385, y_position, horas_totales)
            p.drawString(460, y_position, tiempo_muerto_horas)
            p.drawString(535, y_position, total_peso_kg)
            y_position -= 20

            if y_position < 50:
                p.showPage()
                p.setFont("Helvetica", 10)
                y_position = height - 130
                draw_headers(y_position)
                p.setFont("Helvetica", 10)
                y_position -= 20

        # Calcular los totales por producto
        totales_por_producto = defaultdict(float)
        for row in reportes:
            totales_por_producto[row['producto']] += float(row['total_peso_kg'])
        # Total General
        total_general = reportes[0]['total_general'] if 'total_general' in reportes[0] else 0
        p.line(20, y_position, 580, y_position)
        y_position -= 20
        p.drawString(420, y_position, "TOTAL GENERAL (KG)")
        p.drawString(530, y_position, f"{total_general:.2f}")
        y_position-=20
        if y_position < 100:
            p.showPage()
            p.setFont("Helvetica", 10)
            y_position = height - 130
            draw_headers(y_position)
            p.setFont("Helvetica", 10)
            y_position -= 20

        p.setFont("Helvetica-Bold", 12)
        p.drawString(20, y_position, "Resumen por Producto")
        p.line(20, y_position - 5, width - 20, y_position - 5)
        y_position -= 20

        p.setFont("Helvetica", 10)
        for producto, total_kg in totales_por_producto.items():
            p.drawString(20, y_position, producto)
            p.drawString(530, y_position, f"{total_kg:.2f}")
            y_position -= 20

            if y_position < 50:
                p.showPage()
                p.setFont("Helvetica", 10)
                y_position = height - 130
                draw_headers(y_position)
                p.setFont("Helvetica", 10)
                y_position -= 20

        p.save()
        pdf = buffer.getvalue()
        buffer.close()

        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename=reportes.pdf'
        return response
        
    except ValueError as e:
        flash(f"Error en formato de fecha/hora: {str(e)}", "danger")
        return redirect('/admin/reportes')
    except Exception as e:
        flash(f"Error interno: {str(e)}", "danger")
        return redirect('/admin/reportes')

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
        SELECT 
            CONCAT(p.nombre_producto, ' ', p.calidad) AS nombre_producto, 
            ps.peso, 
            ps.lote, 
            ps.pesaje_id
        FROM 
            pesajes ps
        JOIN 
            productos p ON ps.producto_id = p.producto_id
        ORDER BY 
            ps.fecha_hora DESC
        LIMIT 1;
    """
    resultado = execute_query(connection, query_producto_pesaje, fetchone=True)

    producto_actual = resultado['nombre_producto'] if resultado else "No disponible"
    pesaje_actual = resultado['peso'] if resultado else 0.0
    lote_actual = resultado['lote'] if resultado else "No disponible"
    pesaje_id = resultado['pesaje_id'] if resultado else "No disponible"

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
        "lote_actual": lote_actual,
        "pesaje_id": pesaje_id,
        "tiempos": tiempos,
        "bolsas_por_hora": bolsas_hora,
        "empleados": empleados,
        "rendimiento_empleados": rendimiento
    }), 200



# Nueva ruta para obtener estadísticas del total diario y mensual por producto
@app.route('/api/estadisticas', methods=['GET'])
@login_required
def obtener_estadisticas():
    # Obtener datos de SQL Server para "Hoja Verde"
    hoja_verde_data = get_peso_total_hoja_verde()

    # Obtener datos de MySQL para totales generales
    connection = connect_to_db()
    if connection is None:
        return jsonify({"error": "Error en la conexión a la base de datos MySQL"}), 500

    # Consulta diaria de MySQL
    query_total_diario = """
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_diario
        FROM pesajes ps
        JOIN productos p ON ps.producto_id = p.producto_id
        WHERE DATE(ps.fecha_hora) = CURDATE()
        GROUP BY producto
    """
    total_diario = execute_query(connection, query_total_diario)

    # Consulta mensual de MySQL
    query_total_mensual = """
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_mensual
        FROM pesajes ps
        JOIN productos p ON ps.producto_id = p.producto_id
        WHERE MONTH(ps.fecha_hora) = MONTH(CURDATE()) AND YEAR(ps.fecha_hora) = YEAR(CURDATE())
        GROUP BY producto
    """
    total_mensual = execute_query(connection, query_total_mensual)

    # Retornar resultados combinados
    return jsonify({
        "total_diario": total_diario,
        "total_mensual": total_mensual,
        "total_hoja_verde_diario": hoja_verde_data["total_hoja_verde_diario"],
        "total_hoja_verde_mensual": hoja_verde_data["total_hoja_verde_mensual"]
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
        # cargar_datos_aleatorios() appsecado.py
        time.sleep(300)  # Pausar por 5 minutos

# Iniciar el hilo en segundo plano
# data_thread = threading.Thread(target=iniciar_carga_datos)
# data_thread.daemon = True  # Hilo en segundo plano que se detiene cuando se cierra la app
# data_thread.start()






# Iniciar la app Flask
if __name__ == '__main__':
    app.run(debug=True)