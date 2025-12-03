# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
import sys
import os

block_cipher = None

# --- CONFIGURACIÓN DE RECURSOS ---
datas = []
binaries = []
hiddenimports = []

# ==================== MYSQL CONNECTOR (SOLUCIÓN ROBUSTA) ====================
print("Recolectando dependencias de MySQL Connector...")

# Opción 1: Recolectar todo
tmp_ret = collect_all('mysql.connector')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# Opción 2: Agregar archivos de datos explícitamente
try:
    datas += collect_data_files('mysql.connector', include_py_files=True)
except:
    pass

# Opción 3: Submódulos críticos explícitos
hiddenimports += [
    'mysql.connector',
    'mysql.connector.pooling',
    'mysql.connector.errors',
    'mysql.connector.errorcode',
    'mysql.connector.cursor',
    'mysql.connector.connection',
    'mysql.connector.abstracts',
    'mysql.connector.constants',
    'mysql.connector.conversion',
    'mysql.connector.protocol',
    'mysql.connector.locales',
    'mysql.connector.locales.eng',
    'mysql.connector.locales.eng.client_error',
    '_mysql_connector',
]

# ==================== PYODBC ====================
tmp_ret = collect_all('pyodbc')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# ==================== FLASK Y WERKZEUG ====================
for module in ['flask', 'werkzeug', 'jinja2', 'click', 'itsdangerous']:
    tmp_ret = collect_all(module)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

# ==================== DASH Y PLOTLY ====================
for module in ['dash', 'plotly', 'dash_core_components', 'dash_html_components']:
    try:
        tmp_ret = collect_all(module)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except:
        pass

# ==================== BOKEH ====================
tmp_ret = collect_all('bokeh')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# ==================== PANDAS Y NUMPY ====================
for module in ['pandas', 'numpy']:
    tmp_ret = collect_all(module)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

# ==================== REPORTLAB ====================
tmp_ret = collect_all('reportlab')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# ==================== TUS ARCHIVOS ====================
datas += [
    ('templates', 'templates'),
    ('static', 'static')
]

# --- ANÁLISIS ---
a = Analysis(
    ['appsecado.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# --- GENERACIÓN DEL EXE ---
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MonitorPesajes',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Mantener en True para ver errores
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='static/favicon.ico' if os.path.exists('static/favicon.ico') else None
)