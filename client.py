import socket
import threading
import re
import os
import signal
import sys # Import sys for stdin/stdout check
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
    # Check if stdout is a terminal and not being redirected
    if not sys.stdout.isatty():
        return message

    # Add colors based on message type prefixes
    if message.startswith("[SYSTEM]"):
        return f"{COLORS['SYSTEM']}{message}{COLORS['RESET']}"
    elif message.startswith("[CHAT]"):
        return f"{COLORS['CHAT']}{message}{COLORS['RESET']}"
    elif message.startswith("[ERROR]"):
        return f"{COLORS['ERROR']}{message}{COLORS['RESET']}"
    # Game messages from the server might not always have a specific prefix
    # For simplicity, we'll color messages that seem like game updates
    # based on context, or rely on the server to add a [GAME] prefix if needed.
    # Let's add a [GAME] prefix check as well.
    elif message.startswith("[GAME]"):
        return f"{COLORS['GAME']}{message}{COLORS['RESET']}"
    return message # Default color for other messages


def receive_messages(rfile):
    global running
    try:
        while running:
            # Use select or non-blocking read if necessary for more complex scenarios,
            # but simple readline works with the server sending line by line.
            line = rfile.readline()
            if not line:
                # Server closed the connection
                if running:
                    print("\n[INFO] Server connection closed or game ended.")
                running = False
                break

            line = line.strip()

            # Handle special grid updates
            if line == "GRID":
                # Read lines until an empty line is encountered
                grid_lines = []
                while running: # Ensure we stop if client is shutting down
                    board_line = rfile.readline()
                    if not board_line:
                        if running: print("\n[INFO] Connection lost while receiving grid data.")
                        running = False
                        break # Exit the inner and outer loops
                    if board_line.strip() == "":
                        break # End of grid data
                    grid_lines.append(board_line.rstrip()) # rstrip to keep potential trailing spaces in grid but remove newline
                if running: # Only print if we finished reading the grid
                    print("\n" + "\n".join(grid_lines)) # Print the grid with a preceding newline
                else:
                     break # Exit the main loop if running is false
            else:
                # Process and colorize message before printing
                if line: # Avoid printing empty lines received outside of GRID
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
        # Ensure running is set to False if it wasn't already
        if running:
            running = False
        print("[INFO] Message receiver thread has stopped.")


def main():
    global running
    rfile, wfile = None, None
    sock = None

    try:
        print(f"[INFO] Attempting to connect to server at {HOST}:{PORT}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Set a timeout for the connection attempt itself
        sock.settimeout(10) # 10 seconds timeout for connection
        sock.connect((HOST, PORT))
        sock.settimeout(None) # Remove timeout after successful connection

        print("[INFO] Connected to server.")
        rfile = sock.makefile('r')
        wfile = sock.makefile('w')

         # --- Prompt for username and send it to the server ---
        username = input("Enter your username: ")
        wfile.write(username + '\n')
        wfile.flush()
        # -----------------------------------------------------

        # Start the message receiver thread
        receiver = threading.Thread(target=receive_messages, args=(rfile,), daemon=True)
        receiver.start()

        # Initial message might contain welcome and instructions, receiver will print it.
        print("[INFO] Waiting for welcome message and instructions from server...")

        # Main input loop
        while running:
            try:
                # Prompt user for input. This blocks, but the receiver thread
                # allows displaying incoming messages concurrently.
                user_input = input("") # Empty prompt for cleaner chat interface

            except EOFError:
                print("\n[INFO] EOF detected on input (e.g., Ctrl+D). Exiting.")
                running = False
                break
            except KeyboardInterrupt:
                # Handle Ctrl+C gracefully in the input loop
                print("\n[INFO] Ctrl+C detected. Type '/quit' to exit gracefully or press Ctrl+C again to force quit.")
                # Optionally send a quit command immediately, but letting the user type /quit is cleaner.
                continue # Go back to waiting for input

            if not running:
                break # Exit if receiver thread set running to False

            # Send the input to the server
            try:
                # Add a newline to signal the end of the input line
                wfile.write(user_input + '\n')
                wfile.flush()
            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                if running:
                    print(f"\n[ERROR] Failed to send message: {e}.")
                running = False
                break # Exit the loop on send error
            except Exception as e:
                 if running:
                     print(f"\n[ERROR] An unexpected error occurred while sending: {e}")
                 running = False
                 break # Exit the loop on other send errors


            # If the user typed /quit, break the loop to start shutdown
            if user_input.lower() == "/quit":
                print("[INFO] Sent '/quit' to server. Waiting for server confirmation...")
                # The server should handle the /quit and close the connection,
                # which will cause the receiver thread to exit and set running=False.
                # We can add a short delay or wait for the receiver to finish here
                # to ensure all messages are received, but the current logic
                # of letting the receiver set 'running' is generally sufficient.
                break # Exit the sender loop

        # After the loop, wait for the receiver thread to finish cleanly
        if receiver.is_alive():
             print("[INFO] Waiting for receiver thread to finish...")
             receiver.join(timeout=2) # Wait a bit for the receiver to pick up final messages

    except ConnectionRefusedError:
        print(f"[ERROR] Connection refused. Ensure the server is running at {HOST}:{PORT}.")
    except socket.timeout:
        print(f"[ERROR] Connection timed out after {sock.gettimeout()} seconds.")
    except KeyboardInterrupt:
        # Handle Ctrl+C if it occurs before the input loop starts or while waiting for connection
        print("\n[INFO] Ctrl+C detected during startup. Exiting client...")
    except Exception as e:
        print(f"\n[ERROR] An unexpected client error occurred: {e}")
    finally:
        # Cleanup resources
        if running:
            running = False # Ensure the flag is False during shutdown

        print("\n[INFO] Client is shutting down...")

        if wfile:
            try:
                wfile.close()
            except:
                pass # Ignore errors during close
        if rfile:
            try:
                rfile.close()
            except:
                pass # Ignore errors during close
        if sock:
            try:
                sock.close()
            except:
                pass # Ignore errors during close

        print("[INFO] Client has exited.")


if __name__ == "__main__":
    main()