import socket
import threading
from battleship import Board, parse_coordinate, SHIPS, BOARD_SIZE, run_multiplayer_game

HOST = '127.0.0.1'
PORT = 5001

players = []
lock = threading.Lock()

def handle_client(conn, addr):
    global players
    rfile = conn.makefile('r')
    wfile = conn.makefile('w')

    with lock:
        if len(players) < 2:
            players.append((rfile, wfile, addr))
            try:
                wfile.write("Waiting for another player to join...\n")
                wfile.flush()
            except (socket.error, BrokenPipeError):
                print(f"[INFO] Client {addr} disconnected before pairing.")
                if (rfile, wfile, addr) in players:
                    players.remove((rfile, wfile, addr))
                try:
                    if rfile and not rfile.closed: rfile.close()
                    if wfile and not wfile.closed: wfile.close()
                    conn.close()
                except:
                    pass
                return

        if len(players) == 2: # Should be exactly 2 to start a game
            players_to_start = players[:]
            players = [] # Reset for new connections, so lock can be released sooner

            # At this point, players_to_start holds the pair.
            # Release lock before blocking I/O if possible, though makefile should be quick.
            # For this structure, lock is released after this block anyway.

            try:
                # Using players_to_start[0][1] for wfile of player 1, etc.
                players_to_start[0][1].write("Player 1, you are about to place your ships.\n")
                players_to_start[0][1].flush()
                players_to_start[1][1].write("Player 2, you are about to place your ships.\n")
                players_to_start[1][1].flush()
            except (socket.error, BrokenPipeError) as e:
                print(f"[INFO] A player disconnected just before game could start (during initial messages): {e}. Aborting this pair.")
                for pr_init, pw_init, ad_init in players_to_start:
                    print(f"[INFO] Closing connection for {ad_init} from aborted pair.")
                    try:
                        if pr_init and not pr_init.closed: pr_init.close()
                    except: pass
                    try:
                        if pw_init and not pw_init.closed: pw_init.close()
                    except: pass
                return # Exit this handle_client thread

            print(f"[INFO] Starting game for {players_to_start[0][2]} and {players_to_start[1][2]}")
            # Start the game in a new thread
            threading.Thread(
                target=run_multiplayer_game,
                args=(players_to_start[0][0], players_to_start[0][1], players_to_start[1][0], players_to_start[1][1]),
                daemon=True
            ).start()
            # The handle_client thread for these two connections has now handed off responsibility
            # to run_multiplayer_game, which will manage and close the rfile/wfile objects.

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print("[INFO] Server is ready to accept connections.")
        while True:
            try:
                conn, addr = s.accept()
                print(f"[INFO] Connection established with {addr}")
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"[ERROR] Error accepting connection: {e}")
                # Consider a small delay or more specific error handling if s.accept() fails repeatedly.

if __name__ == "__main__":
    main()