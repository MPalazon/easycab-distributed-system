import socket, argparse, threading, logging, time, requests, json, os, sqlite3
from flask import Flask, jsonify, send_from_directory
from kafka import KafkaProducer, KafkaConsumer
import security, protocol, byte_protocol as bp
import collections

# --- SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', filename='audit.log', filemode='a')
audit_log = logging.getLogger('audit')
CODE_TO_STATUS = {
    bp.STATUS_IDLE: 'IDLE', bp.STATUS_GOING_TO_PICKUP: 'GOING_TO_PICKUP',
    bp.STATUS_GOING_TO_DROPOFF: 'GOING_TO_DROPOFF', bp.STATUS_ARRIVED_PICKUP: 'ARRIVED_PICKUP',
    bp.STOPPED_SENSOR: 'STOPPED_SENSOR', bp.STOPPED_BY_CENTRAL: 'STOPPED_BY_CENTRAL',
    bp.STATUS_UNAVAILABLE: 'UNAVAILABLE', bp.STATUS_SENSOR_FAIL: 'SENSOR_FAIL',
    bp.STATUS_TAXI_LOST: 'TAXI_LOST'
}

class CentralServer:
    def __init__(self, port, kafka_broker):
        self.port, self.kafka_broker, self.lock = port, kafka_broker, threading.Lock()
        self.map_locations, self.traffic_status = {}, "OK"
        self.producer = KafkaProducer(bootstrap_servers=self.kafka_broker)
        self.db_path = "easycab_state.db"
        self.system_errors = collections.deque(maxlen=20)
        self._setup_database()

    def _get_db_conn(self): return sqlite3.connect(self.db_path, timeout=10)
    def _setup_database(self):
        with self.lock:
            with self._get_db_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''CREATE TABLE IF NOT EXISTS registered_taxis (id TEXT PRIMARY KEY)''')
                cursor.execute('''CREATE TABLE IF NOT EXISTS taxis (id TEXT PRIMARY KEY, status TEXT, pos_x INTEGER, pos_y INTEGER, customer_id TEXT, pickup_loc TEXT, final_dest TEXT, last_heartbeat REAL, FOREIGN KEY(id) REFERENCES registered_taxis(id))''')
                cursor.execute('''CREATE TABLE IF NOT EXISTS active_tokens (token TEXT PRIMARY KEY, taxi_id TEXT, session_key TEXT, FOREIGN KEY(taxi_id) REFERENCES registered_taxis(id))''')
                cursor.execute('''CREATE TABLE IF NOT EXISTS clients (id TEXT PRIMARY KEY, pos_x INTEGER, pos_y INTEGER)''')
                conn.commit()

    def log_audit(self, et, det, sip="127.0.0.1"): audit_log.info(f"EVENTO:{et}|ORIGEN:{sip}|DETALLES:{det}")
    def load_config(self, loc_json="EC_Locations.json"):
        try:
            p=os.path.join(os.path.dirname(os.path.abspath(__file__)),loc_json)
            with open(p,'r') as f:
                for loc in json.load(f).get('locations',[]): self.map_locations[loc['Id']]=tuple(map(int,loc['POS'].split(',')))
            print(f"INFO: Cargadas {len(self.map_locations)} localizaciones.")
        except Exception as e: self.log_audit("CONFIG_ERROR",f"Error al cargar {loc_json}:{e}")

    def _watchdog_thread(self):
        while True:
            time.sleep(10)
            with self.lock:
                with self._get_db_conn() as conn:
                    c=conn.cursor(); to=time.time()-20
                    st=('GOING_TO_PICKUP','ARRIVED_PICKUP','GOING_TO_DROPOFF','STOPPED_SENSOR')
                    q=f"SELECT id,customer_id FROM taxis WHERE status IN({','.join('?'for _ in st)})AND last_heartbeat<?"; c.execute(q,st+(to,))
                    for tid,cid in c.fetchall():
                        print(f"ALERTA WATCHDOG: Taxi {tid} perdido."); self.log_audit("TAXI_LOST",f"Taxi {tid} no responde.")
                        c.execute("UPDATE taxis SET status=? WHERE id=?",('TAXI_LOST',tid))
                        if cid: self.producer.send(f'customer_notifications_{cid}',bp.encode_customer_notification(bp.STATUS_KO)); self.producer.flush()
                    conn.commit()
    
    def _reconcile_state_on_startup(self):
        with self.lock:
            with self._get_db_conn() as conn:
                c=conn.cursor(); c.execute("SELECT T.id, T.final_dest, A.session_key FROM taxis T JOIN active_tokens A ON T.id = A.taxi_id WHERE T.status = 'ARRIVED_PICKUP'")
                for tid,dest_str,key in c.fetchall():
                    if dest_str:
                        dest=tuple(map(int,dest_str.strip("() ").split(',')))
                        order=bp.encode_taxi_order(bp.CMD_GOTO,dest)
                        self.producer.send(f'taxi_orders_{tid}',security.encrypt(order,key)); self.producer.flush()
                        c.execute("UPDATE taxis SET status=? WHERE id=?",('GOING_TO_DROPOFF',tid))
                conn.commit()

    def _error_consumer_thread(self):
        cons=KafkaConsumer('system_errors',bootstrap_servers=self.kafka_broker,auto_offset_reset='latest')
        for msg in cons:
            try:
                err=f"{time.strftime('%H:%M:%S')} - {msg.value.decode('utf-8')}"
                with self.lock: self.system_errors.append(err)
                print(f"ERROR RECIBIDO: {err}")
            except Exception: pass
            
    def handle_taxi_auth(self, conn, addr):
        try:
            if conn.recv(1024)!=protocol.ENQ: return
            conn.sendall(protocol.ACK)
            msg,valid=protocol.unwrap_message(conn.recv(1024))
            if not valid or not msg.startswith("AUTH#"): return
            tid=msg.split('#')[1]
            with self.lock:
                with self._get_db_conn() as db:
                    c=db.cursor(); c.execute("SELECT id FROM registered_taxis WHERE id=?",(tid,));
                    if not c.fetchone(): conn.sendall(b"KO:TAXI_NO_REGISTRADO"); return
                    tok,key=security.generate_token(),security.generate_session_key()
                    c.execute("DELETE FROM active_tokens WHERE taxi_id=?",(tid,))
                    c.execute("INSERT OR REPLACE INTO taxis(id,status,pos_x,pos_y,last_heartbeat,customer_id,pickup_loc,final_dest)VALUES(?,?,?,?,?,?,?,?)",(tid,'IDLE',1,1,time.time(),None,None,None))
                    c.execute("INSERT INTO active_tokens(token,taxi_id,session_key)VALUES(?,?,?)",(tok,tid,key))
                    db.commit()
            self.log_audit("AUTH_SUCCESS",f"Taxi {tid} autenticado"); conn.sendall(f"OK:{tok}:{key}".encode())
        except Exception as e: self.log_audit("AUTH_ERROR",f"Error en auth: {e}")
        finally: conn.close()
    
    def listen_for_taxis_auth(self):
        ss=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        ss.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ss.bind(('',self.port))
        ss.listen()
        print(f"Servidor de autenticación escuchando en puerto {self.port}")
        while True: conn,addr=ss.accept(); threading.Thread(target=self.handle_taxi_auth,args=(conn,addr),daemon=True).start()

    ### INICIO DE LA SECCIÓN CORREGIDA ###
    def _handle_taxi_update(self, msg):
        try:
            with self._get_db_conn() as conn:
                c = conn.cursor()
                tok = msg.value[:security.TOKEN_HEX_LENGTH].decode()
                c.execute("SELECT taxi_id, session_key FROM active_tokens WHERE token=?", (tok,))
                res = c.fetchone()
                if not res: return

                tid, key = res
                payload = security.decrypt(msg.value[security.TOKEN_HEX_LENGTH:], key)
                if not payload: return

                _, pos, status_code = bp.decode_taxi_payload(payload)
                new_status = CODE_TO_STATUS.get(status_code)
                if not new_status: return

                # Paso 1: Actualizar siempre el estado físico del taxi (posición y latido).
                c.execute("UPDATE taxis SET last_heartbeat=?, pos_x=?, pos_y=? WHERE id=?", (time.time(), pos[0], pos[1], tid))

                # Paso 2: Obtener el estado lógico autoritativo de la base de datos.
                c.execute("SELECT status, customer_id, final_dest FROM taxis WHERE id=?", (tid,))
                db_status, cust_id, final_dest_str = c.fetchone()

                # --- MÁQUINA DE ESTADOS REVISADA Y EXPLÍCITA ---

                # Transición 1: El taxi estaba yendo a recoger y notifica que ha llegado.
                if db_status == "GOING_TO_PICKUP" and new_status == "ARRIVED_PICKUP":
                    print(f"CENTRAL_LOG: Taxi {tid} llegó a recoger. DB: {db_status}, Taxi: {new_status}")
                    
                    # 1.1: Se actualiza el estado a ARRIVED_PICKUP para que sea visible.
                    c.execute("UPDATE taxis SET status=? WHERE id=?", ('ARRIVED_PICKUP', tid))
                    
                    # 1.2: Se le envía inmediatamente la orden de ir al destino final.
                    if final_dest_str:
                        dest = tuple(map(int, final_dest_str.strip("() ").split(',')))
                        order = bp.encode_taxi_order(bp.CMD_GOTO, dest)
                        self.producer.send(f'taxi_orders_{tid}', security.encrypt(order, key))
                        self.producer.flush()
                        
                        # 1.3: El servidor actualiza autoritativamente el estado a GOING_TO_DROPOFF.
                        #      Esto soluciona el problema del "estado saltado".
                        c.execute("UPDATE taxis SET status=? WHERE id=?", ('GOING_TO_DROPOFF', tid))
                        print(f"CENTRAL_LOG: Taxi {tid} enviado a destino. DB actualizada a GOING_TO_DROPOFF.")

                    # 1.4: Se elimina al cliente del mapa (ya está "dentro" del taxi).
                    if cust_id:
                        c.execute("DELETE FROM clients WHERE id=?", (cust_id,))

                # Transición 2: El taxi estaba yendo al destino y notifica que ha terminado (IDLE).
                elif db_status == "GOING_TO_DROPOFF" and new_status == "IDLE":
                    print(f"CENTRAL_LOG: Taxi {tid} llegó a destino. DB: {db_status}, Taxi: {new_status}")
                    
                    # 2.1: Se resetea el estado del taxi a IDLE, limpiando los datos de la misión.
                    #      Esto soluciona el bug principal de que el taxi no quedaba libre.
                    c.execute("UPDATE taxis SET status='IDLE', customer_id=NULL, pickup_loc=NULL, final_dest=NULL WHERE id=?", (tid,))
                    print(f"CENTRAL_LOG: Taxi {tid} ahora está IDLE en la DB.")

                    # 2.2: Se notifica al cliente y se le "deja" en su nueva posición en el mapa.
                    if cust_id:
                        c.execute("INSERT OR REPLACE INTO clients(id, pos_x, pos_y) VALUES (?, ?, ?)", (cust_id, pos[0], pos[1]))
                        notif = bp.encode_customer_notification(bp.STATUS_FINALIZADO, p=pos)
                        self.producer.send(f'customer_notifications_{cust_id}', notif)
                        self.producer.flush()
                
                # Transición de fallback: Para otros estados (ej. fallos de sensor) que no sean los de la lógica de viaje.
                elif new_status != db_status:
                    c.execute("UPDATE taxis SET status=? WHERE id=?", (new_status, tid))
                
                conn.commit()
        except Exception as e:
            # Se añade un print para ver el error directamente en consola, además de en el log.
            error_msg = f"Error procesando la actualización del taxi: {e}"
            print(f"CENTRAL_ERROR: {error_msg}")
            self.log_audit("UPDATE_ERROR", error_msg)
    ### FIN DE LA SECCIÓN CORREGIDA ###

    def _handle_service_request(self, msg):
        try:
            with self._get_db_conn() as conn:
                c=conn.cursor(); data=msg.value; cust_id,p_coords,dest_id=str(data[1]),(data[2],data[3]),chr(data[4])
                c.execute("INSERT OR REPLACE INTO clients(id,pos_x,pos_y)VALUES(?,?,?)",(cust_id,p_coords[0],p_coords[1]))
                taxi=None
                if self.traffic_status=="OK":
                    c.execute("SELECT id FROM taxis WHERE status='IDLE' LIMIT 1"); res=c.fetchone()
                    if res: taxi=res[0]
                if taxi and dest_id in self.map_locations:
                    f_coords=self.map_locations[dest_id]
                    c.execute("UPDATE taxis SET status=?,customer_id=?,pickup_loc=?,final_dest=?,last_heartbeat=? WHERE id=?",('GOING_TO_PICKUP',cust_id,str(p_coords),str(f_coords),time.time(),taxi))
                    c.execute("SELECT session_key FROM active_tokens WHERE taxi_id=?",(taxi,)); key_res=c.fetchone()
                    if key_res:
                        key=key_res[0]; order=bp.encode_taxi_order(bp.CMD_GOTO,p_coords)
                        notif=bp.encode_customer_notification(bp.STATUS_OK,int(taxi))
                        self.producer.send(f'customer_notifications_{cust_id}',notif)
                        self.producer.send(f'taxi_orders_{taxi}',security.encrypt(order,key))
                        self.producer.flush()
                else:
                    print(f"INFO: No hay taxis libres para el cliente {cust_id}.")
                    notif=bp.encode_customer_notification(bp.STATUS_KO); self.producer.send(f'customer_notifications_{cust_id}',notif); self.producer.flush()
                conn.commit()
        except Exception as e: self.log_audit("REQUEST_ERROR",f"Error en petición: {e}")

    def main_event_processor(self):
        topics = ['taxi_updates', 'service_requests']
        cons = KafkaConsumer(*topics, bootstrap_servers=self.kafka_broker, auto_offset_reset='latest')
        print("INFO: Procesador de Eventos Principal iniciado.")
        for msg in cons:
            with self.lock:
                if msg.topic == 'taxi_updates':
                    self._handle_taxi_update(msg)
                elif msg.topic == 'service_requests':
                    self._handle_service_request(msg)
                elif msg.topic == 'system_errors':
                    pass
    
    def check_traffic_status(self):
        while True:
            time.sleep(10)
            try:
                data = requests.get("http://localhost:5002/traffic_status", timeout=5).json()
                if data["status"] != self.traffic_status:
                    with self.lock: self.traffic_status = data["status"]
                    if self.traffic_status == "KO":
                        with self.lock:
                            with self._get_db_conn() as conn:
                                c=conn.cursor(); c.execute("SELECT T.id,A.session_key FROM taxis T JOIN active_tokens A ON T.id=A.taxi_id WHERE T.status IN('GOING_TO_PICKUP','ARRIVED_PICKUP','GOING_TO_DROPOFF')")
                                for tid,key in c.fetchall():
                                    order=bp.encode_taxi_order(bp.CMD_VOLVERABASE,(1,1))
                                    self.producer.send(f'taxi_orders_{tid}',security.encrypt(order,key))
                            self.producer.flush()
            except Exception as e: self.log_audit("CTC_ERROR",f"No se pudo conectar con EC_CTC: {e}")

    def create_api_app(self):
        api = Flask(__name__,static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)),'static'))
        @api.route('/status')
        def get_status():
            try:
                with self.lock:
                    with self._get_db_conn() as conn:
                        conn.row_factory = sqlite3.Row
                        taxis={r['id']:dict(r) for r in conn.execute("SELECT id,status,pos_x,pos_y,customer_id FROM taxis")}
                        clients={r['id']:dict(r) for r in conn.execute("SELECT id,pos_x,pos_y FROM clients")}
                    errors=list(self.system_errors)
                return jsonify({"taxis":taxis,"traffic_status":self.traffic_status,"map_locations":self.map_locations,"clients":clients,"system_errors":errors})
            except Exception as e: return jsonify({"error":f"Error en BD: {e}"}),500
        @api.route('/')
        def serve_index(): return api.send_static_file('index.html')
        return api

    def run_operator_commands(self):
        cmds={"parar":bp.CMD_PARAR,"reanudar":bp.CMD_REANUDAR,"destino":bp.CMD_DESTINO,"volverabase":bp.CMD_VOLVERABASE}
        while True:
            cmd = input("Operador> "); parts=cmd.split();
            if len(parts)<2: print("Uso: <cmd> <id> [args]"); continue
            cmd_str, tid = parts[0].lower(), parts[1]
            if cmd_str not in cmds: print("Comando no válido."); continue
            with self.lock:
                try:
                    with self._get_db_conn() as conn:
                        c=conn.cursor(); c.execute("SELECT session_key FROM active_tokens WHERE taxi_id=?",(tid,)); res=c.fetchone()
                        if not res: print(f"Error: Taxi {tid} sin sesión activa."); continue
                        key=res[0]; coords=(0,0)
                        if cmd_str == "destino":
                            if len(parts)<3: print("Error: Falta ID de destino."); continue
                            dest_id = parts[2].upper()
                            if dest_id in self.map_locations: coords=self.map_locations[dest_id]
                            else: print(f"Error: Destino '{dest_id}' no encontrado."); continue
                        order = bp.encode_taxi_order(cmds[cmd],coords)
                        self.producer.send(f'taxi_orders_{tid}',security.encrypt(order,key)); self.producer.flush()
                        if cmd_str == "volverabase":
                            c.execute("DELETE FROM active_tokens WHERE taxi_id=?",(tid,))
                            c.execute("UPDATE taxis SET status='IDLE',customer_id=NULL,pickup_loc=NULL,final_dest=NULL WHERE id=?",(tid,)); conn.commit()
                            self.log_audit("TOKEN_EXPIRED",f"Token para taxi {tid} invalidado.")
                except sqlite3.Error as e: print(f"Error de BD: {e}")

    def run(self):
        self.load_config(); self._reconcile_state_on_startup()
        threads=[threading.Thread(target=self.listen_for_taxis_auth,daemon=True),threading.Thread(target=self.main_event_processor,daemon=True),
                 threading.Thread(target=self.check_traffic_status,daemon=True),threading.Thread(target=self._watchdog_thread,daemon=True),
                 # Añadido el hilo para consumir errores, que no estaba siendo iniciado
                 threading.Thread(target=self._error_consumer_thread, daemon=True)]
        for t in threads: t.start()
        api=self.create_api_app(); threading.Thread(target=lambda:api.run(host='0.0.0.0',port=5000),daemon=True).start()
        self.log_audit("SYSTEM_START","EC_Central iniciado."); print("Servidor API en http://0.0.0.0:5000"); print("EC_Central operativo.")
        self.run_operator_commands()

if __name__ == "__main__":
    p=argparse.ArgumentParser(description="EC_Central(R2)"); p.add_argument("port",type=int); p.add_argument("kafka_broker")
    a=p.parse_args(); CentralServer(a.port,a.kafka_broker).run()