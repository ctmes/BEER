import socket
import threading

HOST = '127.0.0.1'
PORT = 5001
running = True


def receive_messages(rfile):
    global running
    try:
        while running:
            line = rfile.readline()
            if not line:
                if running:
                    print("[INFO] Server connection closed or game ended.")
                running = False
                break

            line = line.strip()
            if line == "GRID":
                while True:
                    board_line = rfile.readline()
                    if not board_line:
                        if running: print("[INFO] Connection lost while receiving grid.")
                        running = False
                        return
                    if board_line.strip() == "":
                        print()
                        break
                    print(board_line.strip())
            else:
                print(line)
    except (socket.error, BrokenPipeError, ConnectionResetError) as e:
        if running:
            print(f"[INFO] Network error receiving messages: {e}. Disconnecting.")
        running = False
    except Exception as e:
        if running:
            print(f"[INFO] Error receiving messages: {e}. Disconnecting.")
        running = False
    finally:
        if running:  # Should already be false if loop/try exited normally due to error/EOF
            running = False
        print("[INFO] Message receiver thread stopped.")


def main():
    global running
    rfile, wfile = None, None
    sock = None  # Define socket for finally block

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))
        rfile = sock.makefile('r')
        wfile = sock.makefile('w')

        receiver = threading.Thread(target=receive_messages, args=(rfile,), daemon=True)
        receiver.start()

        while running:
            try:
                user_input = input(">> ")
            except EOFError:  # Can happen if stdin is redirected and ends
                print("[INFO] EOF received on input. Exiting.")
                running = False
                break

            if not running:
                break

            try:
                wfile.write(user_input + '\n')
                wfile.flush()
            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                print(f"[ERROR] Failed to send message: {e}. Server may be down.")
                running = False
                break

            if user_input.lower() == "quit":
                print("[INFO] You typed 'quit'. Exiting.")
                running = False
                break
    except ConnectionRefusedError:
        print("[ERROR] Connection refused. Is the server running?")
        running = False
    except KeyboardInterrupt:
        print("\n[INFO] Ctrl+C detected. Exiting client...")
        running = False
    except Exception as e:
        print(f"[ERROR] An unexpected client error occurred: {e}")
        running = False
    finally:
        running = False
        print("\n[INFO] Client exiting.")

        # Close file objects first
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
        # Then close the socket
        if sock:
            try:
                sock.close()
            except:
                pass


if __name__ == "__main__":
    main()