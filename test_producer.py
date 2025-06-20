# test_producer.py
from kafka import KafkaProducer
import security
import byte_protocol as bp

KAFKA_BROKER = 'localhost:9092'
TAXI_ID = '1'
TOPIC_NAME = f'taxi_orders_{TAXI_ID}'
# Clave de sesión simple para la prueba. El consumidor debe usar la misma.
SESSION_KEY = "Y0FlTTZBaWFBeGFCbF9TaFNKOHprZ09PUDVzNUtfUUNoZz0="

print("--- INICIANDO TEST PRODUCER ---")
try:
    producer = KafkaProducer(bootstrap_servers=KAFKA_BROKER, request_timeout_ms=5000)
    print(f"1. Productor de Kafka conectado a {KAFKA_BROKER}.")
    orden_payload = bp.encode_taxi_order(bp.CMD_GOTO, (10, 15))
    print(f"2. Orden en claro creada: {orden_payload.hex()}")
    encrypted_order = security.encrypt(orden_payload, SESSION_KEY)
    print(f"3. Orden cifrada con la clave de prueba.")
    print(f"4. Enviando mensaje al topic '{TOPIC_NAME}'...")
    future = producer.send(TOPIC_NAME, encrypted_order)
    future.get(timeout=10)
    producer.flush()
    print("5. ¡Mensaje enviado y confirmado por el broker!")
except Exception as e:
    print(f"\nERROR: No se pudo enviar el mensaje: {e}")
finally:
    print("--- TEST PRODUCER FINALIZADO ---")