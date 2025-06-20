import socket, argparse, threading, time, requests, json
from kafka import KafkaProducer, KafkaConsumer
import security, protocol, byte_protocol as bp
import os

STATUS_TO_CODE = {
    "IDLE": bp.STATUS_IDLE, "GOING_TO_PICKUP": bp.STATUS_GOING_TO_PICKUP,
    "GOING_TO_DROPOFF": bp.STATUS_GOING_TO_DROPOFF, "ARRIVED_PICKUP": bp.STATUS_ARRIVED_PICKUP,
    "STOPPED_SENSOR": bp.STOPPED_SENSOR, "STOPPED_BY_CENTRAL": bp.STOPPED_BY_CENTRAL,
    "UNREGISTERED": bp.STATUS_UNAVAILABLE, "SENSOR_FAIL": bp.STATUS_SENSOR_FAIL,
    "TAXI_LOST": bp.STATUS_TAXI_LOST
}

class DigitalEngineClient:
    def __init__(self, central_ip, central_port, kafka_broker, sensor_port, taxi_id):
        self.central_address = (central_ip, central_port)
        self.kafka_broker = kafka_broker; self.sensor_port = sensor_port; self.taxi_id = taxi_id
        self.status = "UNREGISTERED"; self.token, self.session_key = None, None
        self.position, self.destination = [1, 1], None # La posición siempre será una lista de enteros
        self.sensor_status = "OK"; self.producer = KafkaProducer(bootstrap_servers=self.kafka_broker)
        self.state_file = f"taxi_{self.taxi_id}_state.json"
        self._load_state()
        
    def _save_state(self):
        state = {
            "status": self.status,
            "destination": self.destination,
            "position": self.position,
            "token": self.token,
            "session_key": self.session_key
        }
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=4)
            print(f"DEBUG (Taxi {self.taxi_id}): Estado guardado en {self.state_file}")
        except Exception as e:
            print(f"ERROR (Taxi {self.taxi_id}): No se pudo guardar el estado. {e}")
            
    def _load_state(self):
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                self.status = state.get("status", "UNREGISTERED")
                self.destination = tuple(state["destination"]) if state.get("destination") else None
                self.position = state.get("position", [1, 1])
                self.token = state.get("token")
                self.session_key = state.get("session_key")
                print(f"INFO (Taxi {self.taxi_id}): Estado recuperado de {self.state_file}. Status: {self.status}")
        except Exception as e:
            print(f"ERROR (Taxi {self.taxi_id}): No se pudo cargar el estado desde {self.state_file}. Empezando de cero. {e}")
            os.remove(self.state_file)
            
    def _publish_error(self, error_text: str):
        try:
            error_msg = f"EC_DE_{self.taxi_id}: {error_text}"; print(f"ERROR: {error_msg}")
            self.producer.send('system_errors', error_msg.encode('utf-8')); self.producer.flush()
        except Exception as e: print(f"FATAL: No se pudo reportar error a Kafka: {e}")

    def register_taxi(self):
        print(f"INFO (Taxi {self.taxi_id}): Intentando registrar...")
        try:
            response = requests.post("https://localhost:5001/register", json={"taxi_id": self.taxi_id}, timeout=5, verify=False)
            print(f"INFO (Taxi {self.taxi_id}): Respuesta del registro: {response.status_code} - {response.json()}")
        except requests.RequestException as e: self._publish_error(f"Fallo al conectar con registro: {e}")

    def authenticate_and_get_token(self):
        max_retries = 5
        retry_delay = 10 # segundos
        for attempt in range(max_retries):
            print(f"INFO (Taxi {self.taxi_id}): Intentando autenticar (Intento {attempt + 1}/{max_retries})...")
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(5.0) # Timeout para la conexión
                    sock.connect(self.central_address)
                    sock.sendall(protocol.ENQ)
                    if sock.recv(1024) != protocol.ACK:
                        # No lanzar error, continuar al siguiente reintento
                        print("WARN (Taxi {self.taxi_id}): Fallo de conexión inicial (ACK no recibido).")
                        time.sleep(retry_delay)
                        continue

                    sock.sendall(protocol.wrap_message(f"AUTH#{self.taxi_id}"))
                    response = sock.recv(1024).decode()
                    if response.startswith("OK:"):
                        parts = response.split(':')
                        if len(parts) == 3:
                            self.token, self.session_key, self.status = parts[1], parts[2], "IDLE"
                            print(f"INFO (Taxi {self.taxi_id}): Autenticación CORRECTA.")
                            self.send_update()
                            return True # Retornar éxito
                        else:
                            self._publish_error(f"Respuesta de Auth mal formada: {response}")
                    else:
                        self._publish_error(f"Autenticación DENEGADA: {response}")
                
                # Si la autenticación es denegada, no tiene sentido reintentar
                return False

            except (socket.timeout, ConnectionRefusedError, ConnectionResetError) as e:
                print(f"WARN (Taxi {self.taxi_id}): No se pudo conectar a EC_Central: {e}. Reintentando en {retry_delay}s...")
                time.sleep(retry_delay)
            except Exception as e:
                self._publish_error(f"Fallo inesperado al autenticar: {e}")
                time.sleep(retry_delay)
        
        print(f"ERROR (Taxi {self.taxi_id}): No se pudo autenticar después de {max_retries} intentos.")
        return False

    def handle_sensor_connection(self, conn):
        conn.settimeout(5.0)
        while True:
            try:
                data = conn.recv(1024)
                if not data: break
                self.sensor_status = data.decode('utf-8')
            except (socket.timeout, ConnectionResetError): break
        self.sensor_status = "SENSOR_FAIL"; conn.close()

    def listen_to_sensors(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM); server_socket.bind(('0.0.0.0', self.sensor_port)); server_socket.listen()
        print(f"INFO (Taxi {self.taxi_id}): Escuchando sensores en puerto {self.sensor_port}...")
        while True: conn, _ = server_socket.accept(); self.handle_sensor_connection(conn)

    def listen_for_orders(self):
        consumer = KafkaConsumer(f'taxi_orders_{self.taxi_id}', bootstrap_servers=self.kafka_broker, auto_offset_reset='latest')
        for msg in consumer:
            if not self.session_key: continue
            payload = security.decrypt(msg.value, self.session_key)
            if not payload or payload[0] != bp.MSG_TYPE_TAXI_ORDER: continue
            cmd, dest = payload[1], (payload[2], payload[3])
            if cmd == bp.CMD_GOTO:
                self.destination = dest
                self.status = "GOING_TO_DROPOFF" if self.status == "ARRIVED_PICKUP" else "GOING_TO_PICKUP"
            elif cmd == bp.CMD_PARAR: self.status = "STOPPED_BY_CENTRAL"
            elif cmd == bp.CMD_REANUDAR: self.status = "GOING_TO_DROPOFF" if self.destination else "IDLE"
            elif cmd == bp.CMD_VOLVERABASE: self.destination, self.status = (1, 1), "GOING_TO_DROPOFF"
            self.send_update()

    def send_update(self):
        if not self.token or not self.session_key: return
        status_code = STATUS_TO_CODE.get(self.status, bp.STATUS_IDLE)
        payload = bp.encode_taxi_payload(int(self.taxi_id), tuple(self.position), status_code)
        message = self.token.encode() + security.encrypt(payload, self.session_key)
        self.producer.send('taxi_updates', message); self.producer.flush()

    def move(self):
        """Mueve el taxi una coordenada y gestiona las llegadas usando solo enteros."""
        moving_states = ["GOING_TO_PICKUP", "GOING_TO_DROPOFF"]
        if self.status not in moving_states or not self.destination:
            return

        # La comparación es ahora exacta entre enteros
        if tuple(self.position) == self.destination:
            if self.status == "GOING_TO_PICKUP":
                print(f"INFO (Taxi {self.taxi_id}): Cliente recogido en {self.position}.")
                self.status = "ARRIVED_PICKUP"
            elif self.status == "GOING_TO_DROPOFF":
                print(f"INFO (Taxi {self.taxi_id}): Destino final alcanzado en {self.position}.")
                self.status = "IDLE"
            self.destination = None
            self.send_update()
            return
        
        grid_size=20
        dx = self.destination[0] - self.position[0]
        dy = self.destination[1] - self.position[1]

        if abs(dx) > grid_size/2: dx = -1 * (dx//abs(dx)) * (grid_size-abs(dx)) if dx!=0 else 0
        if abs(dy) > grid_size/2: dy = -1 * (dy//abs(dy)) * (grid_size-abs(dy)) if dy!=0 else 0
        
        # El movimiento es siempre un entero: +1, -1, o 0
        move_x = dx//abs(dx) if dx!=0 else 0
        move_y = dy//abs(dy) if dy!=0 else 0
        
        # --- INICIO DE LA CORRECCIÓN ---
        # Se calculan las nuevas coordenadas
        new_x = self.position[0] + move_x
        new_y = self.position[1] + move_y
        
        # Se aplica el wrapping esférico para asegurar que estén en el rango [1, 20]
        self.position[0] = (new_x - 1 + grid_size) % grid_size + 1
        self.position[1] = (new_y - 1 + grid_size) % grid_size + 1
        # --- FIN DE LA CORRECCIÓN ---
        
        self.send_update()

    def run(self):
        threading.Thread(target=self.listen_to_sensors, daemon=True).start()
        threading.Thread(target=self.listen_for_orders, daemon=True).start()
        while True:
            original_status = self.status
            is_moving = self.status in ["GOING_TO_PICKUP", "GOING_TO_DROPOFF"]
            if self.sensor_status == "SENSOR_FAIL" and self.status != "SENSOR_FAIL": self.status = "SENSOR_FAIL"
            elif self.sensor_status == "KO" and is_moving: self.status = "STOPPED_SENSOR"
            elif self.sensor_status == "OK" and self.status == "STOPPED_SENSOR":
                self.status = "GOING_TO_DROPOFF" if self.destination else "IDLE"
            if self.status != original_status: self.send_update()
            if is_moving: self.move()
            time.sleep(1)

    def main_menu(self):
        while True:
            print("\n--- Menú Taxi ---"); print("1. Registrar Taxi"); print("2. Iniciar Operación"); print("3. Salir")
            choice = input("> ")
            if choice == '1': self.register_taxi()
            elif choice == '2':
                if not self.token:
                    # Si la autenticación falla, no continúa a run()
                    if not self.authenticate_and_get_token():
                        print("ERROR: Autenticación fallida. No se puede iniciar la operación.")
                        continue # Vuelve al menú

                self.run()
                break
            elif choice == '3': break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DE Taxi EasyCab (R2)"); parser.add_argument("central_ip"); parser.add_argument("central_port", type=int); parser.add_argument("kafka_broker"); parser.add_argument("sensor_port", type=int); parser.add_argument("taxi_id")
    args = parser.parse_args(); DigitalEngineClient(args.central_ip, args.central_port, args.kafka_broker, args.sensor_port, args.taxi_id).main_menu()