"""
Script para vaciar las tablas de productos, historial de precios y alertas
de la base de datos SQLite local.
"""
import sys
from pathlib import Path

# Agregar el directorio raíz al path de importación
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import storage

def clear_db():
    print("Iniciando borrado inteligente de la base de datos...")
    storage.init_db()
    
    with storage.get_conn() as conn:
        print("Borrando historial de precios...")
        conn.execute("DELETE FROM price_history;")
        
        print("Borrando productos...")
        conn.execute("DELETE FROM products;")
        
        print("Borrando alertas enviadas...")
        conn.execute("DELETE FROM alerts_sent;")
        
    print("Optimizando base de datos (VACUUM)...")
    import sqlite3
    conn = sqlite3.connect(storage.DB_PATH)
    try:
        conn.execute("VACUUM;")
    finally:
        conn.close()
        
    print("¡Base de datos limpiada con éxito!")

if __name__ == "__main__":
    clear_db()
