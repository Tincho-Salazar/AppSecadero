from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file
import mysql.connector
import time
from werkzeug.security import generate_password_hash, check_password_hash
import matplotlib
matplotlib.use('Agg')  # Usar un backend que no requiere interfaz gráfica
import io
import base64
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = 'Datiles2044'  # Cambia esto por una clave secreta
mydb = None

# Conexión global a la base de datos
def connect_to_db():
    global mydb
    try:
        if mydb is None or not mydb.is_connected():
            mydb = mysql.connector.connect(
                host="192.168.30.216",
                user="root",
                password="toor",
                database="secado"
            )
            print("Conexión exitosa a la base de datos")
        return mydb
    except mysql.connector.Error as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None

# Función para ejecutar consultas SQL
def execute_query(query, params=None, fetchone=False, commit=False):
    connection = connect_to_db()
    try:
        cursor = connection.cursor(dictionary=True)  # Usamos dictionary=True para que las filas devueltas sean diccionarios
        cursor.execute(query, params)
        if commit:
            connection.commit()
        if fetchone:
            result = cursor.fetchone()
        else:
            result = cursor.fetchall()
        cursor.close()
        return result
    except mysql.connector.Error as err:
        print("Error MySQL:", err)
        if commit:
            connection.rollback()
        return None

# Decorador para verificar si el usuario está autenticado
def login_required(f):
    def wrap(*args, **kwargs):
        if 'usuario' not in session:
            flash("Por favor, inicia sesión primero", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__  # Necesario para mantener el nombre de la función original
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

# Ruta principal para la visualización de datos y gráficos
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
        resultado = execute_query(query, (usuario,), fetchone=True)

        if resultado and check_password_hash(resultado['contrasena'], contrasena):
            session['usuario'] = resultado['usuario']
            session['rol'] = resultado['rol']  # Guardamos el rol en la sesión
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
    usuarios = execute_query(query)
    return render_template('usuario.html', usuarios=usuarios)

# Ruta para CRUD de productos (solo ADMINISTRADOR)
@app.route('/admin/productos', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar_productos():
    connection = connect_to_db()
    query = "SELECT * FROM productos"
    productos = execute_query(query)
    return render_template('productos.html', productos=productos)

# Ruta para cerrar sesión
@app.route('/logout')
@login_required
def logout():
    session.pop('usuario', None)
    session.pop('rol', None)  # También eliminamos el rol de la sesión
    flash("Has cerrado sesión con éxito", "success")
    return redirect(url_for('login'))

# Ruta para registrar usuarios del sistema 
@app.route('/admin/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        new_username = request.form['new_usuario']
        new_password = request.form['new_contrasena']
        hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')
        
        connection = connect_to_db()  # Obtener la conexión aquí
        if connection is None:
            flash("Error al conectar a la base de datos", "danger")
            return redirect(url_for('register'))

        # Insertar nuevo usuario en la base de datos
        sql = "INSERT INTO usuarios (usuario, contrasena, rol) VALUES (%s, %s, 'user')"
        execute_query(sql, params=(new_username, hashed_password), commit=True)
        flash('Registro exitoso', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Ruta para obtener datos de usuarios
@app.route('/admin/usuarios')
@login_required
def admin_usuarios():
    query = "SELECT * FROM usuarios"
    usuarios = execute_query(query)
    return render_template('usuario.html', usuarios=usuarios)

# Ruta para la obtención de los datos en tiempo real para actualizar la UI
@app.route('/api/datos', methods=['GET'])
@login_required
def obtener_datos():
    connection = connect_to_db()
    if connection is None:
        return jsonify({"error": "Error en la conexión a la base de datos"}), 500

    # Consulta para obtener el producto y pesaje actual
    query_producto_pesaje = """
        SELECT p.nombre_producto, ps.peso 
        FROM pesajes ps
        JOIN productos p ON ps.producto_id = p.producto_id
        ORDER BY ps.fecha_hora DESC LIMIT 1
    """
    resultado = execute_query(query_producto_pesaje, fetchone=True)

    producto_actual = resultado['nombre_producto'] if resultado else "No disponible"
    pesaje_actual = resultado['peso'] if resultado else 0.0

    # Consulta para obtener los pesajes por hora
    query_pesajes_hora = """
        SELECT DATE_FORMAT(ps.fecha_hora, '%H:00') AS hora, SUM(ps.peso) AS total_peso
        FROM pesajes ps
        GROUP BY hora
        ORDER BY hora
    """
    pesajes_por_hora = execute_query(query_pesajes_hora)
    horas = [fila['hora'] for fila in pesajes_por_hora] if pesajes_por_hora else []
    pesos_hora = [float(fila['total_peso']) for fila in pesajes_por_hora] if pesajes_por_hora else []

    # Consulta para obtener el rendimiento por empleado (cantidad de bolsas)
    query_rendimiento_empleado = """
        SELECT e.nombre AS empleado, COUNT(ps.pesaje_id) AS bolsas_producidas
        FROM pesajes ps
        JOIN empleados e ON ps.empleado_id = e.id
        GROUP BY e.nombre
        ORDER BY bolsas_producidas DESC
    """
    rendimiento_empleados = execute_query(query_rendimiento_empleado)
    empleados = [fila['empleado'] for fila in rendimiento_empleados] if rendimiento_empleados else []
    rendimiento = [fila['bolsas_producidas'] for fila in rendimiento_empleados] if rendimiento_empleados else []

    # Retornar toda la información como JSON para los gráficos
    return jsonify({
        "producto_actual": producto_actual,
        "pesaje_actual": pesaje_actual,
        "horas": horas,
        "pesajes_por_hora": pesos_hora,
        "empleados": empleados,
        "rendimiento_empleados": rendimiento
    }), 200

# Nueva ruta para obtener estadísticas del total diario y mensual por producto
@app.route('/api/estadisticas', methods=['GET'])
@login_required
def obtener_estadisticas():
    connection = connect_to_db()

    # Totales diarios por producto
    query_total_diario = """
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_diario
        FROM pesajes ps
        JOIN productos p ON ps.producto_id = p.producto_id
        WHERE DATE(ps.fecha_hora) = CURDATE()
        GROUP BY producto
    """
    total_diario = execute_query(query_total_diario)

    # Totales mensuales por producto
    query_total_mensual = """
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_mensual
        FROM pesajes ps
        JOIN productos p ON ps.producto_id = p.producto_id
        WHERE MONTH(ps.fecha_hora) = MONTH(CURDATE()) AND YEAR(ps.fecha_hora) = YEAR(CURDATE())
        GROUP BY producto;
    """
    total_mensual = execute_query(query_total_mensual)
 
    return jsonify({
        "total_diario": total_diario,
        "total_mensual": total_mensual,
    })

# Ruta para mostrar el gráfico de pesajes por hora
@app.route('/grafico/pesajes')
@login_required
def grafico_pesajes():
    connection = connect_to_db()
    query_pesajes_hora = """
        SELECT DATE_FORMAT(ps.fecha_hora, '%H:00') AS hora, SUM(ps.peso) AS total_peso
        FROM pesajes ps
        GROUP BY hora
        ORDER BY hora
    """
    pesajes_por_hora = execute_query(query_pesajes_hora)
    horas = [fila['hora'] for fila in pesajes_por_hora] if pesajes_por_hora else []
    pesos_hora = [float(fila['total_peso']) for fila in pesajes_por_hora] if pesajes_por_hora else []

    try:
        plt.figure(figsize=(10, 5))
        plt.plot(horas, pesos_hora, marker='o', color='teal', linestyle='-', linewidth=2, markersize=8, markerfacecolor='orange')
        plt.title('Pesajes por Hora')
        plt.xlabel('Hora')
        plt.ylabel('Pesaje (kg)')
        plt.grid(True)

        # Añadir etiquetas a cada punto en la gráfica de línea
        for i, peso in enumerate(pesos_hora):
            plt.text(horas[i], peso, f'{peso:.2f}', ha='center', va='bottom', fontsize=10, color='black')

        # Guardar la figura en un objeto BytesIO
        img = io.BytesIO()
        plt.savefig(img, format='png')
        plt.close()  # Cerrar la figura para liberar memoria
        img.seek(0)

        return send_file(img, mimetype='image/png')
    except Exception as e:
        print(f"Error al crear o enviar el gráfico: {e}")
        return f"Error al generar el gráfico: {str(e)}", 500


# Ruta para mostrar el gráfico de rendimiento por empleado
@app.route('/grafico/rendimiento')
@login_required
def grafico_rendimiento():
    connection = connect_to_db()
    query_rendimiento_empleado = """
        SELECT e.nombre AS empleado, COUNT(ps.pesaje_id) AS bolsas_producidas
        FROM pesajes ps
        JOIN empleados e ON ps.empleado_id = e.id
        GROUP BY e.nombre
        ORDER BY bolsas_producidas DESC
    """
    rendimiento_empleados = execute_query(query_rendimiento_empleado)
    empleados = [fila['empleado'] for fila in rendimiento_empleados] if rendimiento_empleados else []
    rendimiento = [fila['bolsas_producidas'] for fila in rendimiento_empleados] if rendimiento_empleados else []

    # Crear el gráfico usando matplotlib
    try:
        plt.figure(figsize=(10, 8))
        
        # Crear el gráfico de torta
        plt.pie(rendimiento, labels=empleados, autopct='%1.1f%%', startangle=140, colors=plt.cm.Paired(range(len(empleados))))
        plt.title('Rendimiento por Empleado (Porcentaje de Bolsas Producidas)')

        # Guardar la figura en un objeto BytesIO
        img = io.BytesIO()
        plt.savefig(img, format='png')
        plt.close()  # Cerrar la figura
        img.seek(0)

        return send_file(img, mimetype='image/png')
    except Exception as e:
        print(f"Error al crear o enviar el gráfico: {e}")
        return f"Error al generar el gráfico: {str(e)}", 500

# Ruta para mostrar el gráfico de total mensual por producto en barras
@app.route('/grafico/mensual-productos')
@login_required
def grafico_mensual_productos():
    connection = connect_to_db()
    query_total_mensual = """
        SELECT CONCAT(p.nombre_producto, ' ', p.calidad) AS producto, SUM(ps.peso) AS total_mensual
        FROM pesajes ps
        JOIN productos p ON ps.producto_id = p.producto_id
        WHERE MONTH(ps.fecha_hora) = MONTH(CURDATE()) AND YEAR(ps.fecha_hora) = YEAR(CURDATE())
        GROUP BY producto
    """
    total_mensual = execute_query(query_total_mensual)
    productos = [fila['producto'] for fila in total_mensual] if total_mensual else []
    totales = [fila['total_mensual'] for fila in total_mensual] if total_mensual else []

    # Crear el gráfico de barras usando matplotlib
    try:
        plt.figure(figsize=(12, 6))

        # Colores atractivos para las barras
        colores = plt.cm.get_cmap('Set2', len(productos))  # Usar la paleta de colores 'Set2' de Matplotlib

        # Crear el gráfico de barras
        barras = plt.bar(productos, totales, color=[colores(i) for i in range(len(productos))])

        plt.title('Total Mensual por Producto')
        plt.xlabel('Productos')
        plt.ylabel('Total (kg)')
        plt.xticks(rotation=45)  # Rotar las etiquetas de los productos en el eje X para mejor visualización
        plt.grid(axis='y')  # Mostrar sólo las líneas horizontales del grid

        # Añadir etiquetas con los valores sobre cada barra
        for barra in barras:
            altura = barra.get_height()
            plt.text(barra.get_x() + barra.get_width() / 2, altura, f'{altura:.2f} kg', ha='center', va='bottom', fontsize=10, color='black')

        # Guardar la figura en un objeto BytesIO para devolverla como imagen
        img = io.BytesIO()
        plt.savefig(img, format='png')
        plt.close()  # Cerrar la figura para liberar memoria
        img.seek(0)

        return send_file(img, mimetype='image/png')
    except Exception as e:
        print(f"Error al crear o enviar el gráfico: {e}")
        return f"Error al generar el gráfico: {str(e)}", 500
        



if __name__ == '__main__':
    app.run(debug=True)
