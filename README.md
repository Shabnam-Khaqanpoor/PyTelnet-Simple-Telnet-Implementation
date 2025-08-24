# **PyTelnet: A Simple Telnet Implementation in Python**

A lightweight and simple Telnet server and client implementation in Python. This project provides core Telnet protocol support (RFC 854), user authentication, and a basic command-line interface for interaction. It is designed for educational purposes to demonstrate the fundamentals of network socket programming and the Telnet protocol negotiation process.

## **Key Features**

* **Telnet Protocol Support:** Implements standard Telnet protocol commands (IAC, DO, DONT, WILL, WONT).  
* **Option Negotiation:** Supports key Telnet options like ECHO, SUPPRESS-GO-AHEAD, TERMINAL-TYPE, and NAWS (Negotiate About Window Size).  
* **Multi-threaded Server:** The server uses threading to handle multiple client connections simultaneously.  
* **User Authentication:** A basic authentication system with pre-defined usernames and passwords.  
* **Interactive Client:** The client runs in raw terminal mode, allowing for character-by-character input and proper handling of server-side echo.  
* **Cross-Platform:** Runs on any Unix-like system (Linux, macOS) with Python 3.6 or higher.

## **How It Works**

The project consists of two main components:

1. **server.py**: This script creates a TCP socket server that listens for incoming connections on a specified port. When a client connects, the server spawns a new thread to handle it. The server and client then negotiate Telnet options to determine how communication will proceed. After successful authentication, the server processes commands sent by the client.  
2. **client.py**: This script establishes a connection to the Telnet server. It sets the local terminal to "raw" mode to send individual keystrokes to the server immediately. It also responds to the server's Telnet option negotiations and displays data received from the server.

## **Requirements**

* Python 3.6 or higher  
* A Linux or other Unix-like operating system (for the termios and tty modules used by the client).

## **Getting Started**

No special installation is required as the project only uses standard Python libraries.

### **1\. Start the Server**

Open a terminal and run the following command to start the server. It will bind to 0.0.0.0 on port 2323\.

python3 server.py

You should see the output: Server listening on 0.0.0.0:2323

### **2\. Connect with the Client**

Open a second terminal and run the client script to connect to the server.

python3 client.py

By default, the client will attempt to connect to localhost:2323.

### **3\. Log In**

Once connected, the server will prompt you for a username and password. You can use one of the default credentials:

* **Username:** admin, **Password:** admin  
* **Username:** guest, **Password:** guest  
* **Username:** user, **Password:** 123456

## **Available Commands**

Once you are authenticated, you can use the following commands:

| Command | Description |
| :---- | :---- |
| help | Shows the list of available commands. |
| whoami | Displays your username and connection info. |
| users | Lists all currently connected users. |
| uptime | Shows the system uptime of the server. |
| date | Displays the current date and time on the server. |
| hostname | Shows the server's system hostname. |
| echo \[msg\] | Echoes back the message you provide. |
| exit / logout | Disconnects you from the server. |

