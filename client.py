# client.py

import socket
import threading
import re
import os
import signal
import sys

HOST = '127.0.0.1'
PORT = 5001
running = True

COLORS = {
    'RESET': '\033[0m',
    'SYSTEM': '\033[1;33m',
    'CHAT': '\033[1;36m',
    'ERROR': '\033[1;31m',
    'GAME': '\033[1;32m',
}


def colorize_message(message):
    """
    TIER 4.2 INSTANT MESSAGING (IM) CHANNEL - Add color to different message types based on prefixes.

    Args:
        message (str): The incoming message string.

    Returns:
        str: The message string with added ANSI color codes if applicable and
             stdout is a terminal.
    """
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


def receive_messages(rfile):
    """
    TIER 1.1 CONCURRENCY ISSUES, TIER 1.4 SIMPLE CLIENT/SERVER MESSAGE EXCHANGE,
    TIER 1.5 NO DISCONNECTION HANDLING / TIER 2.4 DISCONNECTION HANDLING,
    TIER 3.1 MULTIPLE CONCURRENT CONNECTIONS / TIER 3.2 SPECTATOR EXPERIENCE -
    Continuously reads messages from the server and prints them to the console.
    Handles special "GRID" messages for displaying the board and detects disconnections.

    Args:
        rfile: The file-like object for reading from the socket.
    """
    global running
    try:
        while running:
            line = rfile.readline()
            if not line:
                if running:
                    print("\n[INFO] Server connection closed or game ended.")
                running = False
                break

            line = line.strip()

            if line == "GRID":
                grid_lines = []
                while running:
                    board_line = rfile.readline()
                    if not board_line:
                        if running: print("\n[INFO] Connection lost while receiving grid data.")
                        running = False
                        break
                    if board_line.strip() == "":
                        break
                    grid_lines.append(board_line.rstrip())
                if running:
                    print("\n" + "\n".join(grid_lines))
                else:
                     break
            else:
                if line:
                    print(colorize_message(line))

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
    """
    TIER 1.1 CONCURRENCY ISSUES, TIER 1.4 SIMPLE CLIENT/SERVER MESSAGE EXCHANGE,
    TIER 1.5 NO DISCONNECTION HANDLING / TIER 2.4 DISCONNECTION HANDLING -
    Main function to establish connection, start receiver thread, handle user input,
    send messages to the server, and manage the connection lifecycle.
    """
    global running
    rfile, wfile = None, None
    sock = None

    try:
        print(f"[INFO] Attempting to connect to server at {HOST}:{PORT}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((HOST, PORT))
        sock.settimeout(None)

        print("[INFO] Connected to server.")
        rfile = sock.makefile('r')
        wfile = sock.makefile('w')

        receiver = threading.Thread(target=receive_messages, args=(rfile,), daemon=True)
        receiver.start()

        print("[INFO] Waiting for welcome message and instructions from server...")

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
                wfile.write(user_input + '\n')
                wfile.flush()
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

        print("\n[INFO] Client is shutting down...")

        if wfile:
            try:
                wfile.close()
            except:
                pass
        if rfile:
            try:
                rfile.close()
            except:
                pass
        if sock:
            try:
                sock.close()
            except:
                pass

        print("[INFO] Client has exited.")


if __name__ == "__main__":
    main()