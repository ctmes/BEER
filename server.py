import socket
import threading
from battleship import Board, parse_coordinate, SHIPS, BOARD_SIZE, run_multiplayer_game

HOST = '127.0.0.1'
PORT = 5000

players = []
lock = threading.Lock()
clients = set()  # Track all client connections
shutdown_event = threading.Event()  # Signal for graceful shutdown

def handle_client(conn, addr):
    global players
    rfile = conn.makefile('r')
    wfile = conn.makefile('w')

    # Add client to tracking set
    with lock:
        clients.add(conn)

    game_thread = None
    try:
        with lock:
            if len(players) < 2 and not shutdown_event.is_set():
                players.append((rfile, wfile, addr, conn))
                wfile.write("Waiting for another player to join...\n")
                wfile.flush()

            if len(players) == 2:
                # Notify both players that the game is starting
                (r1, w1, addr1, conn1), (r2, w2, addr2, conn2) = players
                w1.write("Player 1, place your ships manually.\n")
                w1.flush()
                w2.write("Player 2, place your ships manually.\n")
                w2.flush()

                # Start the game in a new thread
                game_thread = threading.Thread(
                    target=run_multiplayer_game,
                    args=(r1, w1, r2, w2, conn1, conn2),
                    daemon=True
                )
                game_thread.start()

        # If a game was started, wait for it to finish
        if game_thread:
            game_thread.join()
            # Clear players list after the game thread completes
            with lock:
                players.clear()

    except Exception as e:
        print(f"[ERROR] Exception in handle_client for {addr}: {e}")
    finally:
        # Ensure client is removed from tracking and connection is closed
        with lock:
            clients.discard(conn)
            players[:] = [p for p in players if p[3] != conn]
        try:
            conn.close()
        except:
            pass

def shutdown_server():
    """Notify all clients and close connections."""
    with lock:
        for conn in clients.copy():
            try:
                wfile = conn.makefile('w')
                wfile.write("[INFO] Server is shutting down.\n")
                wfile.flush()
                conn.close()
            except:
                pass
            clients.discard(conn)
        players.clear()
    shutdown_event.set()

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        s.settimeout(1.0)
        try:
            while not shutdown_event.is_set():
                try:
                    conn, addr = s.accept()
                    print(f"[INFO] Connection established with {addr}")
                    threading.Thread(
                        target=handle_client,
                        args=(conn, addr),
                        daemon=True
                    ).start()
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            print("\n[INFO] Server shutting down...")
            shutdown_server()
        finally:
            s.close()
            print("[INFO] Server has shut down.")

if __name__ == "__main__":
    main()