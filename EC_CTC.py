from flask import Flask, jsonify
import requests, os, threading, time
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
city = "Murcia"
traffic_status = "OK"

def check_weather():
    global traffic_status
    if not OPENWEATHER_API_KEY or OPENWEATHER_API_KEY == "TU_API_KEY_DE_OPENWEATHER":
        print("ERROR: API Key de OpenWeather no configurada en .env"); traffic_status = "KO"; return
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        data = requests.get(url, timeout=5).json()
        temp = data['main']['temp']
        traffic_status = "OK" if temp >= 0 else "KO"
        print(f"INFO: Clima en {city} actualizado. Temp: {temp}°C. Tráfico: {traffic_status}")
    except Exception as e: print(f"ERROR al contactar OpenWeather: {e}"); traffic_status = "KO"

@app.route('/traffic_status', methods=['GET'])
def get_traffic_status(): return jsonify({"city": city, "status": traffic_status})
def console_menu():
    global city
    while True:
        new_city = input(f"\nCiudad actual: {city}. Introduce nueva ciudad y pulsa Enter: ")
        if new_city.strip(): city = new_city.strip(); check_weather()
def periodic_weather_check():
    while True: check_weather(); time.sleep(600)
if __name__ == '__main__':
    threading.Thread(target=periodic_weather_check, daemon=True).start()
    threading.Thread(target=console_menu, daemon=True).start()
    print("Servicio EC_CTC iniciado en http://0.0.0.0:5002")
    app.run(host='0.0.0.0', port=5002)