import socket
import threading
import re
import os
import signal
import sys
from packet import pack_packet, receive_packet, SYSTEM_MESSAGE, USER_INPUT


HOST = '127.0.0.1'
PORT = 5001
running = True  # Global flag to control client loops

# Colors for different message types (ANSI escape codes)
COLORS = {
    'RESET': '\033[0m',
    'SYSTEM': '\033[1;33m',  # Yellow bold
    'CHAT': '\033[1;36m',    # Cyan bold
    'ERROR': '\033[1;31m',   # Red bold
    'GAME': '\033[1;32m',    # Green bold
}


def colorize_message(message):
    """Add color to different message types."""
    if not sys.stdout.isatty():
        return message
    if message.startswith("[SYSTEM]"):
        return f"{COLORS['SYSTEM']}{message}{COLORS['RESET']}"
    elif message.startswith("[CHAT]"):
        return f"{COLORS['CHAT']}{message}{COLORS['RESET']}"
    elif message.startswith("[ERROR]"):
        return f"{COLORS['ERROR']}{message}{COLORS['RESET']}"
    elif message.startswith("[GAME]"):
        return f"{COLORS['GAME']}{message}{COLORS['RESET']}"
    return message


def receive_messages(sock):
    global running
    try:
        while running:
            result = receive_packet(sock)
            if not result:
                if running:
                    print("\n[INFO] Server connection closed or game ended.")
                running = False
                break
            seq, pkt_type, payload = result
            message = payload.decode().strip()
            if message:
                print(colorize_message(message))
    except (socket.error, BrokenPipeError, ConnectionResetError) as e:
        if running:
            print(f"\n[INFO] Network error receiving messages: {e}. Disconnecting.")
        running = False
    except Exception as e:
        if running:
            print(f"\n[INFO] Unexpected error receiving messages: {e}. Disconnecting.")
        running = False
    finally:
        if running:
            running = False
        print("[INFO] Message receiver thread has stopped.")


def main():
    global running
    sock = None

    try:
        print(f"[INFO] Attempting to connect to server at {HOST}:{PORT}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((HOST, PORT))
        sock.settimeout(None)
        print("[INFO] Connected to server.")

        # --- Packet-based username handshake ---
        result = receive_packet(sock)
        if result:
            seq, pkt_type, payload = result
            if pkt_type == SYSTEM_MESSAGE:
                print(payload.decode())
                username = input("Enter username: ").strip()
                packet = pack_packet(1, USER_INPUT, username.encode())
                sock.sendall(packet)
            else:
                print("[ERROR] Did not receive SYSTEM_MESSAGE for username prompt.")
                return
        else:
            print("[ERROR] No packet received for username prompt.")
            return
        # ---------------------------------------

        # Start the message receiver thread
        receiver = threading.Thread(target=receive_messages, args=(sock,), daemon=True)
        receiver.start()

        print("[INFO] Waiting for welcome message and instructions from server...")

        # Main input loop
        while running:
            try:
                user_input = input("")
            except EOFError:
                print("\n[INFO] EOF detected on input (e.g., Ctrl+D). Exiting.")
                running = False
                break
            except KeyboardInterrupt:
                print("\n[INFO] Ctrl+C detected. Type '/quit' to exit gracefully or press Ctrl+C again to force quit.")
                continue

            if not running:
                break

            try:
                packet = pack_packet(2, USER_INPUT, user_input.encode())
                sock.sendall(packet)
            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                if running:
                    print(f"\n[ERROR] Failed to send message: {e}.")
                running = False
                break
            except Exception as e:
                if running:
                    print(f"\n[ERROR] An unexpected error occurred while sending: {e}")
                running = False
                break

            if user_input.lower() == "/quit":
                print("[INFO] Sent '/quit' to server. Waiting for server confirmation...")
                break

        if receiver.is_alive():
            print("[INFO] Waiting for receiver thread to finish...")
            receiver.join(timeout=2)

    except ConnectionRefusedError:
        print(f"[ERROR] Connection refused. Ensure the server is running at {HOST}:{PORT}.")
    except socket.timeout:
        print(f"[ERROR] Connection timed out after {sock.gettimeout()} seconds.")
    except KeyboardInterrupt:
        print("\n[INFO] Ctrl+C detected during startup. Exiting client...")
    except Exception as e:
        print(f"\n[ERROR] An unexpected client error occurred: {e}")
    finally:
        if running:
            running = False
        print("\n[INFO] Client is shutting down.")
        if sock:
            try:
                sock.close()
            except:
                pass
        print("[INFO] Client has exited.")


if __name__ == "__main__":
    main()