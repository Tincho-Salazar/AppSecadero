# hooks/hook-mysql.connector.py
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

# Recolectar TODOS los archivos de datos
datas = collect_data_files('mysql.connector', include_py_files=True)

# Recolectar TODOS los submódulos
hiddenimports = collect_submodules('mysql.connector')

# Recolectar bibliotecas dinámicas (si las hay)
binaries = collect_dynamic_libs('mysql.connector')

# Agregar explícitamente módulos críticos
hiddenimports += [
    'mysql.connector.locales',
    'mysql.connector.locales.eng',
    'mysql.connector.locales.eng.client_error',
    'mysql.connector.pooling',
    'mysql.connector.errors',
    'mysql.connector.errorcode',
    'mysql.connector.constants',
    'mysql.connector.conversion',
    'mysql.connector.protocol',
    'mysql.connector.cursor',
    'mysql.connector.connection',
]