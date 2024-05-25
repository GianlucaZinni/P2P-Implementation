import socket
import threading
import json
import time
import random
from tkinter import Tk, Label, Button, Entry, Text, END, messagebox

# Función para obtener la IP local de la máquina
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()
    return local_ip

# Clase que representa un nodo en la red P2P
class Node:
    def __init__(self, host, port, discovery_server):
        self.host = host
        self.port = port
        self.peers = []  # Lista de pares conocidos
        self.inventory = {f"Recurso-{i}": None for i in range(1, 5)}  # Inventario de recursos
        self.updates = []  # Lista de actualizaciones de inventario
        self.lock_responses = []  # Respuestas a solicitudes de bloqueo de recursos
        self.discovery_server = discovery_server
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.host, self.port))

    # Método para iniciar el servidor en un hilo separado
    def start_server(self):
        server = threading.Thread(target=self.run_server)
        server.daemon = True
        server.start()
        self.register_with_discovery_server()  # Registrarse en el servidor de descubrimiento

    # Método principal del servidor que escucha mensajes de otros nodos
    def run_server(self):
        print(f"Servidor iniciado en {self.host}:{self.port}")

        while True:
            data, addr = self.socket.recvfrom(1024)  # Recibir datos de otros nodos
            message = json.loads(data.decode())
            print(f"Mensaje recibido de {addr}: {message}")
            self.handle_message(message, addr)  # Manejar el mensaje recibido

    # Manejar diferentes tipos de mensajes recibidos
    def handle_message(self, message, addr):
        print(f"Manejando mensaje de {addr}: {message}")
        if message["type"] == "inventory_update":
            self.merge_inventory(message["inventory"], message["updates"])
            self.update_inventory_display()
        elif message["type"] == "lock_request":
            self.handle_lock_request(message, addr)
        elif message["type"] == "lock_response":
            self.lock_responses.append(message["approved"])
        elif message["type"] == "reservation":
            self.inventory[message["book_id"]] = (time.time(), f"{addr[0]}:{addr[1]}")
            self.update_inventory_display()
        elif message["type"] == "unreserve":
            self.inventory[message["book_id"]] = None
            self.update_inventory_display()
        elif message["type"] == "node_list":
            self.peers = [tuple(peer) for peer in message["nodes"]]
            if (self.host, self.port) in self.peers:
                self.peers.remove((self.host, self.port))
            print(f"Lista de nodos actualizada: {self.peers}")

    # Manejar solicitud de bloqueo de un recurso
    def handle_lock_request(self, message, addr):
        book_id = message["book_id"]
        if book_id in self.inventory:
            response = {
                "type": "lock_response",
                "book_id": book_id,
                "approved": self.inventory[book_id] is None
            }
        else:
            response = {
                "type": "lock_response",
                "book_id": book_id,
                "approved": False,
                "error": "Book ID not found"
            }
        self.send_message(response, addr)

    # Enviar un mensaje a un par específico
    def send_message(self, message, peer):
        self.socket.sendto(json.dumps(message).encode(), peer)
        print(f"Mensaje enviado a {peer}: {message}")

    # Método de gossiping para compartir el estado del inventario con otros nodos
    def gossip(self):
        while True:
            time.sleep(random.randint(1, 15))
            if self.peers:
                peer = random.choice(self.peers)
                message = {
                    "type": "inventory_update",
                    "inventory": self.inventory,
                    "updates": self.updates
                }
                self.send_message(message, peer)
                print(f"Gossip enviado a {peer}")

    # Sincronizar el inventario con otro nodo
    def merge_inventory(self, remote_inventory, remote_updates):
        print("Iniciando la sincronización del inventario...")
        for book_id, data in remote_inventory.items():
            if book_id not in self.inventory or self.inventory[book_id] is None or (self.inventory[book_id] is not None and data is not None and self.inventory[book_id][0] < data[0]):
                print(f"Actualizando {book_id} con timestamp {data}")
                self.inventory[book_id] = data

        print("Actualizando lista de actualizaciones...")
        self.updates.extend(remote_updates)
        self.updates = list(set(self.updates))
        print("Inventario sincronizado")

    # Método para reservar un libro
    def reserve_book(self, book_id):
        if book_id not in self.inventory:
            self.show_error_message(f"El libro {book_id} no existe en el inventario.")
            return

        print(f"Intentando reservar libro {book_id}")
        lock_request = {"type": "lock_request", "book_id": book_id}
        self.lock_responses = []
        for peer in self.peers:
            self.send_message(lock_request, peer)

        start_time = time.time()
        while len(self.lock_responses) < len(self.peers) and time.time() - start_time < 5:
            time.sleep(0.1)

        if all(self.lock_responses):
            print(f"Reserva confirmada para el libro {book_id}")
            self.inventory[book_id] = (time.time(), f"{self.host}:{self.port}")
            self.updates.append(f"Reserva de {book_id}")
            self.notify_peers(book_id, "reservation")
        else:
            print(f"Reserva fallida para el libro {book_id}: no se recibió confirmación de todos los peers")
            self.show_error_message(f"No se pudo reservar el libro {book_id}: no se recibió confirmación de todos los peers")

    # Método para devolver una reserva de libro
    def unreserve_book(self, book_id):
        if book_id not in self.inventory:
            self.show_error_message(f"El libro {book_id} no existe en el inventario.")
            return

        if self.inventory.get(book_id) and self.inventory[book_id][1] == f"{self.host}:{self.port}":
            print(f"Devolviendo reserva del libro {book_id}")
            self.inventory[book_id] = None
            self.updates.append(f"Devolución de {book_id}")
            self.notify_peers(book_id, "unreserve")
        else:
            self.show_error_message(f"No se puede devolver el libro {book_id} porque no está reservado por este nodo.")

    # Notificar a todos los pares sobre una reserva o devolución
    def notify_peers(self, book_id, msg_type):
        print(f"Notificando a los peers sobre {msg_type} del libro {book_id}")
        notification = {"type": msg_type, "book_id": book_id}
        for peer in self.peers:
            self.send_message(notification, peer)

    # Registrar el nodo con el servidor de descubrimiento
    def register_with_discovery_server(self):
        print(f"Registrando nodo con el servidor de descubrimiento {self.discovery_server}")
        message = {"type": "join"}
        self.send_message(message, self.discovery_server)
        self.get_node_list()

    # Solicitar la lista de nodos del servidor de descubrimiento
    def get_node_list(self):
        print("Solicitando lista de nodos del servidor de descubrimiento")
        message = {"type": "get_nodes"}
        self.send_message(message, self.discovery_server)

    # Actualizar la visualización del inventario en la interfaz gráfica
    def update_inventory_display(self):
        if hasattr(self, 'app'):
            self.app.update_inventory_display()

    # Mostrar un mensaje de error en la interfaz gráfica
    def show_error_message(self, message):
        if hasattr(self, 'app'):
            self.app.show_error_message(message)

# Clase para la interfaz gráfica del nodo
class LibraryApp:
    def __init__(self, root, node):
        self.node = node
        self.node.app = self
        self.root = root
        self.root.title(f"P2P Nodo Reservas: {node.host}:{node.port}")

        self.label = Label(root, text="Reservar libro (ID):")
        self.label.pack()

        self.book_id_entry = Entry(root)
        self.book_id_entry.pack()

        self.reserve_button = Button(root, text="Reservar", command=self.reserve_book)
        self.reserve_button.pack()

        self.unreserve_button = Button(root, text="Devolver Reserva", command=self.unreserve_book)
        self.unreserve_button.pack()

        self.inventory_text = Text(root, height=30, width=65)
        self.inventory_text.pack()
        self.update_inventory_display()

    # Método para reservar un libro desde la interfaz
    def reserve_book(self):
        book_id = self.book_id_entry.get()
        if book_id:
            self.node.reserve_book(book_id)
            self.update_inventory_display()

    # Método para devolver una reserva desde la interfaz
    def unreserve_book(self):
        book_id = self.book_id_entry.get()
        if book_id:
            self.node.unreserve_book(book_id)
            self.update_inventory_display()

    # Actualizar la visualización del inventario en la interfaz
    def update_inventory_display(self):
        self.inventory_text.delete(1.0, END)
        for book_id, data in self.node.inventory.items():
            if data is None:
                status = "Disponible"
            else:
                timestamp, owner = data
                status = f"Reservado por {owner} (timestamp: {timestamp})"
            self.inventory_text.insert(END, f"{book_id}: {status}\n")

    # Mostrar un mensaje de error en la interfaz
    def show_error_message(self, message):
        messagebox.showerror("Error", message)

# Iniciar nodos con diferentes puertos
if __name__ == "__main__":
    
    IP_MAQUINA_2 = "192.168.0.15"  # IP del servidor de descubrimiento
    discovery_server_addr = (IP_MAQUINA_2, 4000)
    local_ip = get_local_ip()

    # Cambiar el puerto '8080' por otro distinto, para agregar más nodos.
    node = Node(local_ip, 8080, discovery_server_addr)
    node.start_server()

    gossip_thread = threading.Thread(target=node.gossip)
    gossip_thread.daemon = True
    gossip_thread.start()

    root = Tk()
    app = LibraryApp(root, node)
    root.mainloop()
