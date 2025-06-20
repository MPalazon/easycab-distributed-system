from flask import Flask, request, jsonify
import sqlite3, threading, os

app = Flask(__name__)
DB_PATH = "easycab_state.db"
db_lock = threading.Lock()

def setup_database():
    with db_lock:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS registered_taxis (id TEXT PRIMARY KEY)')
            conn.commit()

@app.route('/register', methods=['POST'])
def register_taxi():
    data = request.get_json()
    if not data or 'taxi_id' not in data: return jsonify({"status": "error", "message": "Falta taxi_id"}), 400
    taxi_id = str(data['taxi_id'])
    with db_lock:
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                conn.execute("INSERT INTO registered_taxis (id) VALUES (?)", (taxi_id,)); conn.commit()
            return jsonify({"status": "ok", "message": f"Taxi {taxi_id} registrado"}), 201
        except sqlite3.IntegrityError: return jsonify({"status": "error", "message": "El taxi ya está registrado"}), 409
        except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    setup_database()
    print("Servicio EC_Registry (con BD y HTTPS) iniciado en https://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001, ssl_context='adhoc')