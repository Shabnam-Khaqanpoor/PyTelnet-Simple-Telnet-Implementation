# Import necessary system and networking libraries
import socket
import sys
import select
import signal
import termios
import tty
import os
import time

# Basic network configuration for the client
HOST = 'localhost'  # Server address
PORT = 2323         # Server port
BUFFER_SIZE = 1024  # Size of data chunks for transmission

# Telnet protocol control characters and options
IAC = 255           # Interpret As Command
DONT = 254          # Don't use option
DO = 253           # Do use option
WONT = 252         # Won't use option
WILL = 251         # Will use option
SB = 250           # Subnegotiation Begin
SE = 240           # Subnegotiation End
ECHO = 1           # Echo option
SUPPRESS_GO_AHEAD = 3  # Suppress Go Ahead option
TERMINAL_TYPE = 24     # Terminal type option
NAWS = 31             # Negotiate About Window Size
BINARY = 0            # Binary transmission option
CR = 13              # Carriage Return
LF = 10              # Line Feed
NUL = 0              # Null character

# Global variables to track client state
local_echo = True    # Controls whether client echoes input
original_terminal_settings = None  # Stores original terminal configuration
last_window_size = (0, 0)  # Tracks the last sent window dimensions

def send_option(client_socket, command, option):
    """Send a Telnet option command to the server."""
    try:
        client_socket.send(bytes([IAC, command, option]))
    except socket.error as e:
        print(f"\rError sending option: {e}")

def send_suboption(client_socket, option, data):
    """Send a Telnet suboption with specific data."""
    try:
        client_socket.send(bytes([IAC, SB, option]) + data + bytes([IAC, SE]))
    except socket.error as e:
        print(f"\rError sending suboption: {e}")

def process_telnet_command(client_socket, data):
    """Process incoming Telnet commands and handle protocol negotiations."""
    global local_echo
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
                # Handle various Telnet options
                if data[i + 1] == DO:
                    if option == ECHO:
                        local_echo = False
                        send_option(client_socket, WILL, ECHO)
                    elif option == SUPPRESS_GO_AHEAD:
                        send_option(client_socket, WILL, SUPPRESS_GO_AHEAD)
                    elif option == TERMINAL_TYPE:
                        send_option(client_socket, WILL, TERMINAL_TYPE)
                    elif option == NAWS:
                        send_option(client_socket, WILL, NAWS)
                        send_suboption(client_socket, NAWS, bytes([0, 80, 0, 24]))
                    elif option == BINARY:
                        send_option(client_socket, WILL, BINARY)
                elif data[i + 1] == DONT:
                    if option == ECHO:
                        local_echo = True
                        send_option(client_socket, WONT, ECHO)
                    elif option == BINARY:
                        send_option(client_socket, WONT, BINARY)
                elif data[i + 1] == WILL:
                    if option == BINARY:
                        send_option(client_socket, DO, BINARY)
                    elif option == ECHO:
                        send_option(client_socket, DO, ECHO)
                i += 3
            elif data[i + 1] == SB:
                j = i + 2
                while j < len(data) and not (data[j] == IAC and j + 1 < len(data) and data[j + 1] == SE):
                    j += 1
                if j + 1 < len(data):
                    suboption = data[i + 2:j]
                    if suboption[0] == TERMINAL_TYPE and suboption[1] == 1:
                        send_suboption(client_socket, TERMINAL_TYPE, b'\x00' + b'VT100')
                    i = j + 2
                else:
                    break
            else:
                i += 2
        else:
            result.append(data[i])
            i += 1
    return bytes(result)

def set_raw_mode():
    """Configure terminal for raw input mode."""
    global original_terminal_settings
    if not sys.stdin.isatty():
        return
    original_terminal_settings = termios.tcgetattr(sys.stdin)
    tty.setraw(sys.stdin.fileno(), termios.TCSANOW)

def restore_terminal():
    """Restore terminal to its original settings."""
    global original_terminal_settings
    if original_terminal_settings and sys.stdin.isatty():
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_terminal_settings)
        print("\rTerminal restored")

def get_terminal_size():
    """Get current terminal dimensions."""
    try:
        columns, lines = os.get_terminal_size(0)
        return columns, lines
    except OSError:
        return 80, 24  # Default terminal size

def handle_interrupt(signum, frame):
    """Handle interrupt signals (like Ctrl+C)."""
    restore_terminal()
    print("\rInterrupted by user")
    sys.exit(0)

def handle_window_change(signum, frame):
    """Handle terminal window size changes."""
    global last_window_size
    if 'client_socket' in globals():
        width, height = get_terminal_size()
        if (width, height) != last_window_size:
            try:
                send_suboption(client_socket, NAWS, bytes([width >> 8, width & 0xFF, height >> 8, height & 0xFF]))
                last_window_size = (width, height)
            except:
                pass

def main():
    """Main client function handling connection and communication."""
    global client_socket, last_window_size
    # Set up signal handlers for graceful termination
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)
    if hasattr(signal, 'SIGWINCH'):
        signal.signal(signal.SIGWINCH, handle_window_change)

    # Initialize client socket
    client_socket = None
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((HOST, PORT))
        client_socket.setblocking(False)
        print(f"Connected to {HOST}:{PORT}")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    try:
        # Set up terminal and window size
        set_raw_mode()
        width, height = get_terminal_size()
        last_window_size = (width, height)

        # Send initial window size to server
        try:
            send_suboption(client_socket, NAWS, bytes([width >> 8, width & 0xFF, height >> 8, height & 0xFF]))
        except:
            pass

        # Set up input monitoring
        inputs = [client_socket, sys.stdin]
        buffer = bytearray()

        # Main communication loop
        while True:
            readable, _, _ = select.select(inputs, [], [], 0.1)

            for s in readable:
                if s == client_socket:
                    try:
                        data = client_socket.recv(BUFFER_SIZE)
                        if not data:
                            print("\r\nConnection closed by server")
                            return

                        processed_data = process_telnet_command(client_socket, data)
                        if processed_data:
                            sys.stdout.buffer.write(processed_data)
                            sys.stdout.buffer.flush()
                    except socket.error as e:
                        print(f"\r\nSocket error: {e}")
                        return

                elif s == sys.stdin:
                    try:
                        char = sys.stdin.buffer.read(1)
                        if not char:  # EOF
                            return

                        # Process special input characters
                        if char == b'\x04':  # Ctrl+D (EOT)
                            return
                        elif char == b'\x7f' or char == b'\x08':  # Backspace or Delete
                            if buffer:  # Only if buffer has content
                                buffer.pop()  # Remove last character
                                if local_echo:
                                    sys.stdout.buffer.write(b'\b \b')
                                    sys.stdout.buffer.flush()
                        elif char == b'\r':  # Enter key
                            if buffer:
                                cmd = bytes(buffer)
                                client_socket.send(cmd + bytes([CR, LF]))
                            else:
                                client_socket.send(bytes([CR, LF]))

                            if local_echo:
                                sys.stdout.buffer.write(b'\r\n')
                                sys.stdout.buffer.flush()
                            buffer.clear()
                        else:
                            buffer.append(ord(char))
                            if local_echo:
                                sys.stdout.buffer.write(char)
                                sys.stdout.buffer.flush()
                    except Exception as e:
                        print(f"\r\nInput error: {e}")
                        continue

    except Exception as e:
        print(f"\r\nError: {e}")
    finally:
        # Cleanup and close connection
        restore_terminal()
        if client_socket:
            try:
                client_socket.close()
            except:
                pass
        print("\r\nConnection closed")

if __name__ == "__main__":
    main()
