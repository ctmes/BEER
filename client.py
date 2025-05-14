import socket
import threading
import os  # For os.kill if desperate, but not used here.
import signal  # For os.kill if desperate.

HOST = '127.0.0.1'
PORT = 5001
running = True  # Global flag to control client loops


def receive_messages(rfile):
    global running
    try:
        while running:  # Check flag at the start of each iteration
            line = rfile.readline()
            if not line:  # Server closed connection (EOF)
                if running:  # Only print if we weren't already stopping
                    print("\n[INFO] Server connection closed or game ended.")
                running = False  # Signal main loop to stop
                break  # Exit receiver loop

            line = line.strip()
            if line == "GRID":
                # Server will send a descriptive line before "GRID" like "Your view of X's board:"
                # print("\n[Game Board Update]") # Generic header, can be removed if server messages are good.
                while True:
                    board_line = rfile.readline()
                    if not board_line:
                        if running: print("\n[INFO] Connection lost while receiving grid data.")
                        running = False
                        return  # Exit receiver function
                    if board_line.strip() == "":  # Empty line signifies end of this grid transmission
                        print()  # Add a newline for better readability after grid
                        break
                    print(board_line.strip())
            else:
                print(line)  # Print general messages from server
    except (socket.error, BrokenPipeError, ConnectionResetError) as e:
        if running:  # Avoid double messages if already stopping
            print(f"\n[INFO] Network error receiving messages: {e}. Disconnecting.")
        running = False
    except Exception as e:  # Catch any other unexpected error during receive
        if running:
            print(f"\n[INFO] Unexpected error receiving messages: {e}. Disconnecting.")
        running = False
    finally:
        # This block executes when the try block is exited (normally or via exception)
        if running:  # If loop exited for reasons other than setting running=False
            running = False  # Ensure main loop is signalled
        print("[INFO] Message receiver thread has stopped.")


def main():
    global running
    rfile, wfile = None, None
    sock = None

    try:
        print(f"[INFO] Attempting to connect to server at {HOST}:{PORT}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))
        print("[INFO] Connected to server.")
        rfile = sock.makefile('r')
        wfile = sock.makefile('w')

        # Start the message receiver thread
        receiver = threading.Thread(target=receive_messages, args=(rfile,), daemon=True)
        receiver.start()

        # Main input loop
        while running:  # Check flag before attempting input
            try:
                user_input = input(">> ")
            except EOFError:  # Handles case where stdin is closed (e.g. piping input)
                print("\n[INFO] EOF detected on input. Exiting.")
                running = False  # Signal to exit
                break  # Exit input loop
            except KeyboardInterrupt:  # User pressed Ctrl+C during input()
                print("\n[INFO] Ctrl+C detected during input. Exiting client...")
                running = False  # Signal to exit
                # No need to send "quit", server will detect disconnect
                break  # Exit input loop

            if not running:  # Check if receiver thread set running to False (e.g. server disconnect)
                # This check is after input() returns.
                break

            try:
                wfile.write(user_input + '\n')
                wfile.flush()
            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                # This error means server is likely gone or connection broke
                if running:  # Avoid printing if already exiting for other reasons
                    print(f"\n[ERROR] Failed to send message (server connection may be lost): {e}.")
                running = False  # Signal to exit
                break  # Exit input loop

            if user_input.lower() == "quit":
                print("[INFO] You typed 'quit'. Client will now exit.")
                # The server will receive this "quit" message and handle it.
                # Or, if this client closes connection first, server detects disconnect.
                running = False  # Signal to exit
                break  # Exit input loop

    except ConnectionRefusedError:
        print(f"[ERROR] Connection refused. Ensure the server is running at {HOST}:{PORT}.")
        running = False
    except KeyboardInterrupt:  # Ctrl+C pressed during connect or other main thread ops
        print("\n[INFO] Ctrl+C detected. Exiting client...")
        running = False
    except Exception as e:  # Catch-all for other unexpected errors in main client logic
        print(f"\n[ERROR] An unexpected client error occurred: {e}")
        running = False
    finally:
        # This finally block ensures cleanup happens
        if running:  # If exited finally for a reason that didn't set running to false
            running = False  # Explicitly set, though daemon receiver might keep running until main exits

        print("\n[INFO] Client is shutting down...")

        # Attempt to close file objects and socket
        # These operations should be idempotent or handle errors if already closed
        if wfile:
            try:
                wfile.close()
            except:
                pass  # Ignore errors on close
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