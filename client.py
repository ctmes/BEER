import socket
import threading
import re
import os
import signal
import sys
from packet import pack_packet, receive_packet, SYSTEM_MESSAGE, USER_INPUT

# Should probably make these command line params
SERVER_ADDR = '127.0.0.1'  # localhost for testing
SERVER_PORT = 5001
client_active = True  # Flag to control our loops

# Terminal colors - makes output prettier
# copied from my other project, might need fixing for Windows
MSG_COLORS = {
    'RESET': '\033[0m',
    'SYSTEM': '\033[1;33m',  # Yellow bold
    'CHAT': '\033[1;36m',  # Cyan bold
    'ERROR': '\033[1;31m',  # Red bold
    'GAME': '\033[1;32m',  # Green bold
}


def pretty_print(msg):
    """Make messages look nicer with colors based on type"""
    # skip colors if not in a proper terminal
    if not sys.stdout.isatty():
        return msg

    # lazy way to handle different message types
    if "[SYSTEM]" in msg:
        return f"{MSG_COLORS['SYSTEM']}{msg}{MSG_COLORS['RESET']}"
    elif "[CHAT]" in msg:
        return f"{MSG_COLORS['CHAT']}{msg}{MSG_COLORS['RESET']}"
    elif "[ERROR]" in msg:
        return f"{MSG_COLORS['ERROR']}{msg}{MSG_COLORS['RESET']}"
    elif "[GAME]" in msg:
        return f"{MSG_COLORS['GAME']}{msg}{MSG_COLORS['RESET']}"
    return msg


def msg_receiver(connection):
    """Thread that listens for server messages"""
    global client_active
    try:
        while client_active:
            data = receive_packet(connection)
            if not data:
                if client_active:
                    print("\n[INFO] Lost connection to server.")
                client_active = False
                break

            # extract the message
            seq_num, msg_type, raw_data = data
            text = raw_data.decode().strip()

            # print if not empty
            if text:
                print(pretty_print(text))
    except (socket.error, BrokenPipeError, ConnectionResetError) as e:
        # network broke
        if client_active:
            print(f"\n[INFO] Connection error: {e}. Disconnecting.")
        client_active = False
    except Exception as e:
        # some other errror
        if client_active:
            print(f"\n[INFO] Weird error in message thread: {e}")
        client_active = False
    finally:
        if client_active:
            client_active = False
        print("[INFO] Message thread stopped.")


def main():
    global client_active
    sock = None

    try:
        # Connect to game server
        print(f"[INFO] Connecting to {SERVER_ADDR}:{SERVER_PORT}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)  # Don't hang forever
        sock.connect((SERVER_ADDR, SERVER_PORT))
        sock.settimeout(None)  # Back to normal mode
        print("[INFO] Connected!")

        # Login process
        got_packet = receive_packet(sock)
        if got_packet:
            seq, pkt_type, payload = got_packet
            if pkt_type == SYSTEM_MESSAGE:
                # Show login prompt and send username
                print(payload.decode())
                name = input("Enter username: ").strip()
                login_packet = pack_packet(1, USER_INPUT, name.encode())
                sock.sendall(login_packet)
            else:
                print("[ERROR] Server didn't send login prompt. Weird.")
                return
        else:
            print("[ERROR] No response from server for login.")
            return

        # Start listening thread
        msg_thread = threading.Thread(target=msg_receiver, args=(sock,), daemon=True)
        msg_thread.start()

        print("[INFO] Waiting for server welcome message...")

        # Main input loop
        while client_active:
            try:
                text = input("")  # Get user input
            except EOFError:
                print("\n[INFO] Input stream closed (Ctrl+D). Quitting.")
                client_active = False
                break
            except KeyboardInterrupt:
                print("\n[INFO] Interrupted! Type '/quit' to exit properly or press Ctrl+C again to force quit.")
                continue

            # Check if we should still be runnig
            if not client_active:
                break

            # Send messege to server
            try:
                # always use seq 2 for now
                pkt = pack_packet(2, USER_INPUT, text.encode())
                sock.sendall(pkt)
            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                if client_active:
                    print(f"\n[ERROR] Can't send message: {e}")
                client_active = False
                break
            except Exception as e:
                if client_active:
                    print(f"\n[ERROR] Something broke while sending: {e}")
                client_active = False
                break

            # Handle quit command
            if text.lower() == "/quit":
                print("[INFO] Quitting game. Waiting for server to acknowledge...")
                break

        # Clean up the message thread
        if msg_thread.is_alive():
            print("[INFO] Waiting for message thread...")
            msg_thread.join(timeout=2)  # wait up to 2 sec

    except ConnectionRefusedError:
        print(f"[ERROR] Server refused connection. Is it running at {SERVER_ADDR}:{SERVER_PORT}?")
    except socket.timeout:
        print(f"[ERROR] Connection attempt timed out after {sock.gettimeout()} seconds.")
    except KeyboardInterrupt:
        print("\n[INFO] Startup interrupted. Exiting...")
    except Exception as e:
        print(f"\n[ERROR] Something unexpected happened: {e}")
    finally:
        # Final cleanup
        if client_active:
            client_active = False
        print("\n[INFO] Shutting down client...")
        if sock:
            try:
                sock.close()
            except:
                pass  # we're quitting anyway
        print("[INFO] Goodbye!")


# Run the main function
if __name__ == "__main__":
    # Could add arg parsing here later
    main()