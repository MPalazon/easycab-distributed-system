#!/bin/bash

echo "--- Iniciando Servicios Centrales con xterm ---"
xterm -T "Registry" -e "python3 EC_Registry.py" &
xterm -T "CTC" -e "python3 EC_CTC.py" &
xterm -T "Central" -e "python3 EC_Central.py 1234 localhost:9092" &

echo "Esperando 5 segundos..."
sleep 5


xterm -T "Taxi 1 DE" -e "python3 EC_DE.py localhost 1234 localhost:9092 8001 1" &
xterm -T "Taxi 2 DE" -e "python3 EC_DE.py localhost 1234 localhost:9092 8002 2" &
xterm -T "Taxi 3 DE" -e "python3 EC_DE.py localhost 1234 localhost:9092 8003 3" &

sleep 10 

xterm -T "Taxi 1 S" -e "python3 EC_S.py localhost 8001" &
xterm -T "Taxi 2 S" -e "python3 EC_S.py localhost 8002" &
xterm -T "Taxi 3 S" -e "python3 EC_S.py localhost 8003" &   

sleep 10

xterm -T "Customer 1" -e "python3 EC_Customer.py localhost:9092 1" &
xterm -T "Customer 2" -e "python3 EC_Customer.py localhost:9092 2" &


echo "--- Simulación iniciada ---"