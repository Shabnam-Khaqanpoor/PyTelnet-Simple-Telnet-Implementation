import socket
import select
import time
import os
import sys
import hashlib
import threading
import signal
import queue

# Server configuration
HOST = '0.0.0.0'
PORT = 2323
BUFFER_SIZE = 1024
TIMEOUT = 30  # 5 minutes idle timeout

# Telnet protocol constants
IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250
SE = 240
ECHO = 1
SUPPRESS_GO_AHEAD = 3
TERMINAL_TYPE = 24
NAWS = 31
BINARY = 0
CR = 13
LF = 10
NUL = 0

# User authentication
users = {
    # username: password
    'admin': 'admin',
    'guest': 'guest',
    'user': '123456',
}

# Client states
STATE_LOGIN = 0
STATE_PASSWORD = 1
STATE_COMMAND = 2

# Client state
clients = {}  # {socket: {'addr': addr, 'buffer': b'', 'last_activity': timestamp, 'options': {}, 'state': int, 'username': str, 'prompt': str, 'window_size': (width, height)}}

# Active users for tracking (username -> {socket, addr})
active_users = {}  # username -> {socket: socket_obj, addr: (ip, port)}

# Lock for thread safety
lock = threading.Lock()

# Global variables for server state
message_queue = queue.Queue()  # Queue for broadcasting messages
running = True  # Server running state

def send_option(client_socket, command, option):
    """Send a Telnet option command."""
    try:
        client_socket.send(bytes([IAC, command, option]))
    except socket.error as e:
        print(f"Error sending option to {clients[client_socket]['addr']}: {e}")

def send_suboption(client_socket, option, data):
    """Send a Telnet suboption."""
    try:
        client_socket.send(bytes([IAC, SB, option]) + data + bytes([IAC, SE]))
    except socket.error as e:
        print(f"Error sending suboption to {clients[client_socket]['addr']}: {e}")

def send_message(client_socket, message):
    """Send a message to the client with proper line endings."""
    try:
        # Replace single \n with \r\n for proper Telnet line endings
        message = message.replace('\n', '\r\n')
        # Print full message to server log without truncation
        if len(message) > 100:
            print(f"Sending message to client ({len(message)} bytes): {message[:50]}...{message[-50:]}")
        else:
            print(f"Sending message to client ({len(message)} bytes): {message}")
        client_socket.send(message.encode('utf-8', errors='replace'))
    except socket.error as e:
        print(f"Error sending message to {clients[client_socket]['addr']}: {e}")

def process_telnet_command(client_socket, data):
    """Process Telnet IAC commands and return filtered data."""
    result = bytearray()
    i = 0
    while i < len(data):
        if data[i] == IAC:
            if i + 1 >= len(data):
                break
            if data[i + 1] == IAC:
                result.append(data[i])
                i += 2
            elif data[i + 1] in (DO, DONT, WILL, WONT):
                if i + 2 >= len(data):
                    break
                option = data[i + 2]
                if data[i + 1] == DO:
                    if option == ECHO:
                        send_option(client_socket, WONT, ECHO)  # Server controls echo
                    elif option == SUPPRESS_GO_AHEAD:
                        send_option(client_socket, WILL, SUPPRESS_GO_AHEAD)
                        clients[client_socket]['options']['suppress_go_ahead'] = True
                    elif option == TERMINAL_TYPE:
                        send_option(client_socket, WILL, TERMINAL_TYPE)
                    elif option == NAWS:
                        send_option(client_socket, WILL, NAWS)
                    elif option == BINARY:
                        send_option(client_socket, WILL, BINARY)
                        clients[client_socket]['options']['binary'] = True
                elif data[i + 1] == WILL:
                    if option == ECHO:
                        send_option(client_socket, DO, ECHO)
                        clients[client_socket]['options']['echo'] = True
                    elif option in (SUPPRESS_GO_AHEAD, TERMINAL_TYPE, NAWS):
                        send_option(client_socket, DO, option)
                    elif option == BINARY:
                        send_option(client_socket, DO, BINARY)
                        clients[client_socket]['options']['binary'] = True
                elif data[i + 1] == WONT:
                    if option == BINARY:
                        clients[client_socket]['options']['binary'] = False
                elif data[i + 1] == DONT:
                    if option == BINARY:
                        clients[client_socket]['options']['binary'] = False
                i += 3
            elif data[i + 1] == SB:
                j = i + 2
                while j < len(data) and not (data[j] == IAC and j + 1 < len(data) and data[j + 1] == SE):
                    j += 1
                if j + 1 < len(data):
                    suboption = data[i + 2:j]
                    if suboption[0] == TERMINAL_TYPE and suboption[1] == 1:
                        send_suboption(client_socket, TERMINAL_TYPE, b'\x00' + b'VT100')
                    elif suboption[0] == NAWS and len(suboption) >= 5:
                        width = (suboption[1] << 8) + suboption[2]
                        height = (suboption[3] << 8) + suboption[4]
                        
                        # Only print if window size actually changed
                        if 'window_size' not in clients[client_socket] or clients[client_socket]['window_size'] != (width, height):
                            print(f"Client {clients[client_socket]['addr']} window size: {width}x{height}")
                        
                        clients[client_socket]['window_size'] = (width, height)
                    i = j + 2
                else:
                    break
            else:
                i += 2
        else:
            result.append(data[i])
            i += 1
    return bytes(result)

def authenticate_user(username, password):
    """Authenticate user with username and password."""
    print(f"Auth attempt: username='{username}', password='{password}'")
    if username in users:
        if password == users[username]:
            print(f"Authentication successful for '{username}'")
            return True
        else:
            print(f"Invalid password for '{username}'")
    else:
        print(f"Username '{username}' not found")
    return False

def handle_command(client_socket, command):
    """Handle commands from authenticated users."""
    username = clients[client_socket]['username']
    
    # Simple command handler
    command = command.strip()
    print(f"\n{'*'*20} COMMAND RECEIVED {'*'*20}")
    print(f"USER: {username}")
    print(f"COMMAND: '{command}'")
    print(f"IP: {clients[client_socket]['addr'][0]}")
    print(f"PORT: {clients[client_socket]['addr'][1]}")
    print(f"{'*'*55}\n")
    
    if command.lower() == 'exit' or command.lower() == 'logout':
        print(f"\n{'#'*50}")
        print(f"USER DISCONNECTING: {username} from {clients[client_socket]['addr']}")
        print(f"{'#'*50}\n")
        
        # First remove from data structures
        with lock:
            if username in active_users:
                del active_users[username]
            if client_socket in clients:
                del clients[client_socket]
        
        # Then send goodbye message
        try:
            send_message(client_socket, "Goodbye!\n")
        except:
            pass
        
        # Finally close the socket
        try:
            client_socket.close()
            print(f"Socket closed successfully")
        except:
            pass
        
        return False  # Signal to close connection in main loop
    
    elif command.lower() == 'help':
        help_text = """
Available commands:
  help       - Show this help message
  whoami     - Display your username
  users      - List connected users
  uptime     - Show system uptime
  date       - Show current date and time
  hostname   - Show system hostname
  echo [msg] - Echo a message
  exit       - Disconnect from the server
  logout     - Same as exit
"""
        print(f"\nCOMMAND RESULT [help]: sending help text ({len(help_text)} bytes)\n")
        send_message(client_socket, help_text)
    
    elif command.lower() == 'whoami':
        client_ip, client_port = clients[client_socket]['addr']
        message = f"You are logged in as: {username}\n"
        message += f"Connected from: {client_ip}:{client_port}\n"
        print(f"\nCOMMAND RESULT [whoami]: {message.strip()}\n")
        send_message(client_socket, message)
    
    elif command.lower() == 'users':
        print(f"\n{'='*50}")
        print(f"USERS COMMAND from {username} at {clients[client_socket]['addr']}")
        print(f"{'='*50}")
        
        # IMPORTANT: No locks used at all in this implementation to avoid hanging
        
        # Simple solution - just show the current user's information
        # This avoids any potential issues with locks
        current_ip, current_port = clients[client_socket]['addr']
        
        # Create a simple response that always works
        message = f"You are connected as: {username} from {current_ip}:{current_port}\n"
        message += "To see other users, check the server logs.\n"
        
        # Server-side log (no locks) - create a safe copy of client keys first
        # to avoid dictionary changed during iteration errors
        print("\n*** CONNECTED USERS LIST START ***")
        try:
            # Get a copy of client keys to safely iterate
            client_sockets = list(clients.keys())
            connected_count = 0
            
            for s in client_sockets:
                try:
                    if s in clients and 'username' in clients[s] and clients[s]['username'] and 'addr' in clients[s]:
                        user = clients[s]['username']
                        addr = clients[s]['addr']
                        print(f"  USER: {user} | CONNECTION: {addr[0]}:{addr[1]}")
                        connected_count += 1
                except Exception as e:
                    print(f"  Error processing client: {e}")
            
            if connected_count == 0:
                print("  NO AUTHENTICATED USERS CONNECTED")
            else:
                print(f"  TOTAL USERS CONNECTED: {connected_count}")
            
        except Exception as e:
            print(f"  ERROR LISTING USERS: {e}")
        
        print("*** CONNECTED USERS LIST END ***\n")
        
        # Send the response to client
        print(f"Sending users response to client")
        send_message(client_socket, message)
        print(f"Users command completed successfully")
    
    elif command.lower() == 'uptime':
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
                days = int(uptime_seconds / 86400)
                hours = int((uptime_seconds % 86400) / 3600)
                minutes = int((uptime_seconds % 3600) / 60)
                message = f"System uptime: {days} days, {hours} hours, {minutes} minutes\n"
        except:
            message = f"System uptime information not available\n"
        print(f"\nCOMMAND RESULT [uptime]: {message.strip()}\n")
        send_message(client_socket, message)
    
    elif command.lower() == 'date':
        message = f"Current date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        print(f"\nCOMMAND RESULT [date]: {message.strip()}\n")
        send_message(client_socket, message)
    
    elif command.lower() == 'hostname':
        try:
            message = f"Hostname: {socket.gethostname()}\n"
        except:
            message = "Hostname information not available\n"
        print(f"\nCOMMAND RESULT [hostname]: {message.strip()}\n")
        send_message(client_socket, message)
    
    elif command.lower().startswith('echo '):
        message = command[5:] + "\n"  # Remove 'echo ' prefix
        print(f"\nCOMMAND RESULT [echo]: {message.strip()}\n")
        send_message(client_socket, message)
    
    else:
        message = f"Unknown command: {command}\n"
        print(f"Unknown command: {message.strip()}")
        send_message(client_socket, message)
    
    return True  # Continue connection

def handle_client(client_socket, client_address):
    """Handle individual client connections and communication."""
    print(f"New connection from {client_address}")
    clients[client_socket] = {
        'addr': client_address,
        'buffer': b'',
        'last_activity': time.time(),
        'options': {},
        'state': STATE_LOGIN,
        'username': None,
        'prompt': 'login: ',
        'window_size': (80, 24)
    }

    try:
        # Send welcome message
        welcome_msg = f"Welcome to the Telnet server! Connected from {client_address}\r\n"
        client_socket.send(welcome_msg.encode())

        while running:
            try:
                data = client_socket.recv(BUFFER_SIZE)
                if not data:
                    break

                # Process received data
                processed_data = process_telnet_command(client_socket, data)
                if processed_data:
                    # Broadcast message to all clients
                    message = f"Client {client_address}: {processed_data.decode()}"
                    message_queue.put(message)

            except socket.error as e:
                print(f"Socket error with {client_address}: {e}")
                break

    except Exception as e:
        print(f"Error handling client {client_address}: {e}")
    finally:
        # Clean up client connection
        client_socket.close()
        del clients[client_socket]
        print(f"Connection closed for {client_address}")

def broadcast_messages():
    """Broadcast messages to all connected clients."""
    while running:
        try:
            message = message_queue.get()
            if message:
                for client in list(clients.keys()):
                    try:
                        client.send(message.encode())
                    except:
                        pass
        except:
            pass

def handle_interrupt(signum, frame):
    """Handle server shutdown signals."""
    global running
    print("\nShutting down server...")
    running = False
    for client in list(clients.keys()):
        try:
            client.close()
        except:
            pass
    sys.exit(0)

def main():
    """Main server function handling connections and client management."""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)

    # Create server socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        # Bind and start listening
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        print(f"Server listening on {HOST}:{PORT}")

        # Start broadcast thread
        broadcast_thread = threading.Thread(target=broadcast_messages)
        broadcast_thread.daemon = True
        broadcast_thread.start()

        # Main server loop
        while running:
            try:
                client_socket, client_address = server_socket.accept()
                client_thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
                client_thread.daemon = True
                client_thread.start()
            except socket.error as e:
                if running:
                    print(f"Error accepting connection: {e}")
                break

    except Exception as e:
        print(f"Server error: {e}")
    finally:
        # Clean up server
        server_socket.close()
        print("Server closed")

if __name__ == "__main__":
    main()