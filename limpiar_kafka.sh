#!/bin/bash

# Dirección de tu servidor Kafka
BOOTSTRAP_SERVER="localhost:9092"

# Lista de topics estáticos
TOPICS="service_requests taxi_updates system_errors"

echo "Borrando topics estáticos..."
for topic in $TOPICS; do
    # Usamos kafka-topics.sh (asegúrate de que esté en tu PATH o usa la ruta completa)
    kafka-topics.sh --bootstrap-server $BOOTSTRAP_SERVER --delete --topic $topic
done

# Borrando topics dinámicos (esto es más complejo, un ejemplo para 5 taxis y 5 clientes)
echo "Borrando topics dinámicos (taxis 1-5, clientes 101-105)..."
for i in {1..5}; do
    kafka-topics.sh --bootstrap-server $BOOTSTRAP_SERVER --delete --topic "taxi_orders_$i"
    kafka-topics.sh --bootstrap-server $BOOTSTRAP_SERVER --delete --topic "customer_notifications_10$i"
done

echo "Limpieza de topics de Kafka completada."
echo "NOTA: Es normal ver errores si un topic no existía. Los nuevos topics se crearán automáticamente al iniciar la app."