import argparse, time, json, random
from kafka import KafkaProducer, KafkaConsumer
import byte_protocol as bp
import os

class CustomerApp:
    def __init__(self, kafka_broker, customer_id):
        self.kafka_broker, self.customer_id = kafka_broker, int(customer_id)
        self.services_file = "EC_Requests.json"
        self.current_position = (random.randint(1, 20), random.randint(1, 20))
        self.producer = KafkaProducer(bootstrap_servers=self.kafka_broker)
        self.consumer = KafkaConsumer(f'customer_notifications_{self.customer_id}', bootstrap_servers=self.kafka_broker, auto_offset_reset='latest')
        self.state_file = f"customer_{self.customer_id}_state.json"
        self.waiting_for_destination = self._load_state()
        print(f"Cliente {self.customer_id} iniciado en la posición aleatoria: {self.current_position}")
    
    def _save_state(self, destination_id):
        state = {"waiting_for_destination": destination_id, "current_position": self.current_position}
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            print(f"ERROR (Cliente {self.customer_id}): No se pudo guardar el estado. {e}")
    
    def _load_state(self):
        if not os.path.exists(self.state_file):
            return None
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                self.current_position = tuple(state.get("current_position", self.current_position))
                destination = state.get("waiting_for_destination")
                if destination:
                    print(f"INFO (Cliente {self.customer_id}): Estado recuperado. Esperando finalización del viaje a {destination}.")
                    return destination
            return None
        except Exception as e:
            print(f"ERROR (Cliente {self.customer_id}): No se pudo cargar el estado. {e}")
            return None

    def _clear_state(self):
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
            print(f"DEBUG (Cliente {self.customer_id}): Estado local limpiado.")
    
    def read_services_from_json(self):
        try:
            with open(self.services_file, 'r') as f: return [req['Id'] for req in json.load(f).get('Requests', [])]
        except Exception as e: print(f"ERROR al leer '{self.services_file}': {e}"); return []
        
    def run(self):
        if self.waiting_for_destination:
            # Si estamos recuperando, la lista de servicios es solo el que estábamos esperando
            services_to_request = [self.waiting_for_destination]
        else:
            # Si no, leemos la lista completa del fichero
            services_to_request = self.read_services_from_json()
        if not services_to_request: print("No hay servicios que solicitar."); return
        for destination in services_to_request:
            print(f"\n--- Cliente {self.customer_id} desde {self.current_position} solicitando servicio a {destination} ---")
            request_bytes = bp.encode_service_request(self.customer_id, self.current_position, destination)
            self.producer.send('service_requests', request_bytes); self.producer.flush()
            print("Petición enviada. Esperando finalización del servicio...")
            for message in self.consumer:
                data = message.value
                if not data or data[0] != bp.MSG_TYPE_CUSTOMER_NOTIFICATION: continue
                status_code = data[1]
                if status_code == bp.STATUS_KO: print("Notificación: Servicio denegado."); break
                elif status_code == bp.STATUS_OK: print(f"Notificación: Servicio aceptado. Taxi asignado: {data[2]}.")
                elif status_code == bp.STATUS_FINALIZADO:
                    print("Notificación: Servicio concluido con éxito.")
                    self.current_position = (data[2], data[3])
                    print(f"El cliente {self.customer_id} se ha movido a su nuevo destino: {self.current_position}")
                    break
            print("Esperando 4 segundos para el siguiente servicio...")
            time.sleep(4)
        print("\nTodos los servicios del cliente han sido procesados.")
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="App de Cliente EasyCab"); parser.add_argument("kafka_broker"); parser.add_argument("customer_id")
    args = parser.parse_args(); CustomerApp(args.kafka_broker, args.customer_id).run()