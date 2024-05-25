import socket
import threading
import json
import time

# Función para obtener la IP local de la máquina
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Conectar a una dirección IP pública para determinar la IP local
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()
    return local_ip

# Clase que representa el servidor de descubrimiento
class DiscoveryServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.nodes = []  # Lista para almacenar nodos conectados

    # Método para iniciar el servidor en un hilo separado
    def start_server(self):
        server = threading.Thread(target=self.run_server)
        server.daemon = True
        server.start()

    # Método principal del servidor que escucha mensajes de nodos
    def run_server(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((self.host, self.port))
        print(f"Servidor de descubrimiento iniciado en {self.host}:{self.port}")

        while True:
            data, addr = s.recvfrom(1024)  # Recibir datos de los nodos
            message = json.loads(data.decode())
            print(f"Mensaje recibido de {addr}: {message}")
            if message["type"] == "join":
                self.nodes.append(addr)  # Añadir nodo a la lista
                print(f"Nuevo nodo unido: {addr}")
                self.send_node_list()  # Enviar lista actualizada de nodos
            elif message["type"] == "get_nodes":
                self.send_node_list()  # Enviar lista de nodos cuando se solicita

    # Método para enviar la lista de nodos a todos los nodos conectados
    def send_node_list(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        message = {"type": "node_list", "nodes": self.nodes}
        for node in self.nodes:
            s.sendto(json.dumps(message).encode(), node)
            print(f"Enviando lista de nodos a {node}: {message}")

# Iniciar el servidor de descubrimiento
local_ip = get_local_ip()
discovery_server = DiscoveryServer(local_ip, 4000)
discovery_server.start_server()

# Mantener el servidor corriendo indefinidamente
while True:
    time.sleep(1)
