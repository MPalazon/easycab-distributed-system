import socket, argparse, time, threading
from pynput import keyboard

class Sensor:
    def __init__(self, de_host, de_port):
        self.de_address, self.sock, self.contingency = (de_host,de_port), socket.socket(socket.AF_INET, socket.SOCK_STREAM), threading.Event()
    def connect_to_de(self):
        for _ in range(5):
            try: self.sock.connect(self.de_address); print(f"Sensor conectado a DE en {self.de_address}."); return True
            except ConnectionRefusedError: time.sleep(2)
        print("Fallo al conectar con EC_DE."); return False
    def keyboard_listener(self):
        def on_press(key):
            if not self.contingency.is_set(): print("\n¡Incidencia detectada!"); self.contingency.set()
        def on_release(key):
            if self.contingency.is_set(): print("\nIncidencia terminada."); self.contingency.clear()
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener: listener.join()
    def run(self):
        if not self.connect_to_de(): return
        threading.Thread(target=self.keyboard_listener, daemon=True).start()
        print("Listener de teclado iniciado. Mantén pulsada una tecla para simular incidencia.")
        while True:
            message = "KO" if self.contingency.is_set() else "OK"
            try: self.sock.sendall(message.encode('utf-8'))
            except (ConnectionResetError, BrokenPipeError): print("Conexión con DE perdida."); break
            time.sleep(1)
        self.sock.close()
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sensores de Taxi EasyCab"); parser.add_argument("de_ip"); parser.add_argument("de_port", type=int)
    args = parser.parse_args(); Sensor(args.de_ip, args.de_port).run()