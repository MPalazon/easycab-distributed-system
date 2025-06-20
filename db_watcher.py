# db_watcher.py
import sqlite3
import time
import os

DB_PATH = "easycab_state.db"
TAXI_ID_TO_WATCH = "1"

print("--- Iniciando Observador de Base de Datos (DB Watcher) ---")
print(f"Vigilando el estado del Taxi '{TAXI_ID_TO_WATCH}' en el fichero '{DB_PATH}'...")
print("Presiona Ctrl+C para detener.")

while True:
    try:
        if not os.path.exists(DB_PATH):
            print(f"({time.strftime('%H:%M:%S')}) - Esperando a que se cree el fichero de la base de datos...")
            time.sleep(2)
            continue
    
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        # Obtener el estado del taxi
        cursor.execute("SELECT status, last_heartbeat FROM taxis WHERE id = ?", (TAXI_ID_TO_WATCH,))
        result = cursor.fetchone()
        
        conn.close()

        if result:
            status, last_hb = result
            hb_ago_str = f"{(time.time() - last_hb):.2f} seg" if last_hb else "Nunca"
            print(f"({time.strftime('%H:%M:%S')}) | Taxi {TAXI_ID_TO_WATCH} -> Estado en BD: {status:<20} | Último Latido hace: {hb_ago_str}")
        else:
            print(f"({time.strftime('%H:%M:%S')}) | Taxi {TAXI_ID_TO_WATCH} -> No encontrado en la tabla 'taxis'.")
    
    except Exception as e:
        print(f"({time.strftime('%H:%M:%S')}) - Error al leer la base de datos: {e}")

    time.sleep(1)