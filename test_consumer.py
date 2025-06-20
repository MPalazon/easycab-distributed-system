from kafka import KafkaConsumer
import security
import byte_protocol as bp

KAFKA_BROKER = 'localhost:9092'
TAXI_ID = '1'
TOPIC_NAME = f'taxi_orders_{TAXI_ID}'
# ¡Usa la misma clave que en el productor!
SESSION_KEY = "Y0FlTTZBaWFBeGFCbF9TaFNKOHprZ09PUDVzNUtfUUNoZz0="

print("--- INICIANDO TEST CONSUMER ---")
print(f"Escuchando en el topic '{TOPIC_NAME}'...")
try:
    consumer = KafkaConsumer(TOPIC_NAME, bootstrap_servers=KAFKA_BROKER, auto_offset_reset='latest', consumer_timeout_ms=20000)
    message_received = False
    for msg in consumer:
        message_received = True
        print("\n¡Mensaje recibido!")
        decrypted_payload = security.decrypt(msg.value, SESSION_KEY)
        if not decrypted_payload:
            print(">>> RESULTADO: FALLO. El mensaje se recibió, pero NO SE PUDO DESCIFRAR.")
        elif decrypted_payload[0] == bp.MSG_TYPE_TAXI_ORDER:
            cmd, dest = decrypted_payload[1], (decrypted_payload[2], decrypted_payload[3])
            print(">>> RESULTADO: ¡ÉXITO! Mensaje descifrado correctamente.")
            print(f"    -> Comando: {cmd}, Destino: {dest}")
        else:
            print(">>> RESULTADO: FALLO. El mensaje se descifró, pero no es una orden válida.")
        break
    if not message_received:
        print("\n>>> RESULTADO: FALLO. No se recibió ningún mensaje después de esperar 20 segundos.")
except Exception as e:
    print(f"\nERROR: El consumidor falló: {e}")
finally:
    print("--- TEST CONSUMER FINALIZADO ---")