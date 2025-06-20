# EasyCab - Simulación de Sistema Distribuido

Simulación de una flota de taxis (`EasyCab`) como proyecto para la asignatura de Sistemas Distribuidos. El sistema está diseñado con una arquitectura modular, asíncrona y resiliente, capaz de gestionar múltiples taxis y clientes de forma concurrente.

## Características Principales

* **Arquitectura Modular:** El sistema se descompone en microservicios independientes (Central, Registry, CTC, Taxi, Cliente), cada uno con una responsabilidad única.
* **Comunicación Asíncrona:** Uso de **Apache Kafka** como bus de mensajes para desacoplar los componentes, permitiendo una comunicación robusta y escalable.
* **Seguridad por Capas:**
    * **Canal Seguro:** Comunicación con el servicio de registro (`EC_Registry`) mediante **HTTPS**.
    * **Cifrado de Datos:** Cifrado simétrico (AES) con claves de sesión únicas para toda la comunicación operacional a través de Kafka.
    * **Autenticación y Autorización:** Sistema de tokens de sesión para validar las peticiones de los taxis.
    * **Auditoría:** Registro estructurado de todos los eventos significativos del sistema en `audit.log`.
* **Visualización en Tiempo Real:** Interfaz web (`index.html`) que consume una **API REST (Flask)** para mostrar el estado de todos los taxis, clientes y destinos en un mapa interactivo.
* **Resiliencia Avanzada:** El sistema está diseñado para recuperarse de fallos en cualquiera de sus componentes sin intervención manual y sin pérdida de datos o servicios en curso.

## Arquitectura y Módulos

* `EC_Central.py`: El cerebro del sistema. Orquesta la asignación de servicios, monitoriza los taxis y sirve la API REST para el frontend.
* `EC_DE.py`: El motor digital de un taxi. Gestiona el estado, movimiento y comunicación de una unidad de taxi.
* `EC_Customer.py`: Simula un cliente que solicita servicios de taxi de una lista predefinida.
* `EC_Registry.py`: Servicio con API REST sobre HTTPS para el registro seguro de nuevos taxis.
* `EC_CTC.py`: Servicio de control de tráfico que consulta una API externa (OpenWeather) para determinar la viabilidad de la circulación.
* `EC_S.py`: Simula el sensor de un taxi que reporta incidencias.

## Tecnologías Utilizadas

* **Lenguaje:** Python 3
* **Broker de Mensajes:** Apache Kafka
* **API REST y Web:** Flask
* **Base de Datos:** SQLite 3
* **Librerías Clave:** `kafka-python`, `requests`, `pynput`

## Ejecución del Proyecto

### Requisitos Previos

1.  Tener una instancia de **Apache Kafka** corriendo. Por defecto, se espera que esté en `localhost:9092`.
2.  Tener **Python 3** y **pip** instalados.

### Instalación de Dependencias

Se recomienda crear un entorno virtual. Para instalar todas las librerías de Python necesarias, ejecuta:
```bash
pip install -r requirements.txt
```
*(Nota: Para crear el fichero `requirements.txt`, ejecuta `pip freeze > requirements.txt` en tu terminal una vez tengas todo instalado).*

### Secuencia de Arranque

Para un funcionamiento correcto, los módulos deben ser lanzados en el siguiente orden. Abre una terminal para cada uno.

1.  **EC_Registry (Servicio de Registro):**
    ```bash
    python3 EC_Registry.py
    ```
2.  **EC_CTC (Control de Tráfico):**
    ```bash
    python3 EC_CTC.py
    ```
3.  **Taxis y Sensores (Lanzar un par por cada taxi):**
    ```bash
    # Terminal para el motor del Taxi 1
    python3 EC_DE.py localhost 1234 localhost:9092 8001 1
    # Terminal para el sensor del Taxi 1
    python3 EC_S.py localhost 8001
    ```
    *(No olvides registrar (opción 1) e iniciar (opción 2) cada taxi desde su menú)*

4.  **EC_Central (El Orquestador):**
    ```bash
    python3 EC_Central.py 1234 localhost:9092
    ```
5.  **Clientes (Lanzar tantos como se desee):**
    ```bash
    python3 EC_Customer.py localhost:9092 101
    ```

Una vez que todo esté en marcha, puedes acceder a la interfaz de visualización en `http://localhost:5000`.

## Diseño de Resiliencia

El sistema implementa una estrategia de resiliencia multicapa para asegurar la continuidad del servicio ante fallos:

1.  **Persistencia de Estado:** La Central utiliza una base de datos SQLite para persistir el estado de los viajes. Los Taxis y Clientes guardan su estado actual en ficheros `.json` locales.
2.  **Recuperación de la Central:** Al reiniciarse, `EC_Central` lee su base de datos y reenvía las órdenes a los taxis que se encontraban en mitad de un servicio, recuperando así los viajes en curso.
3.  **Recuperación de Taxis/Clientes:** Si un taxi o cliente se reinicia, lee su fichero de estado local y reanuda su tarea automáticamente, sin necesidad de intervención manual.
4.  **Fiabilidad de la Comunicación:** El uso de `auto_offset_reset='earliest'` y `group_id` fijos en los consumidores de Kafka garantiza que no se pierdan mensajes durante una caída y que no se procesen peticiones "fantasma" de ejecuciones anteriores, asegurando la consistencia del sistema.