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
                # Attempt to remove the player if they were added.
                # This needs careful handling if the player list could be modified by another thread.
                # For simplicity, if makefile ops fail, the player might not be fully registered or cleaned up
                # immediately from this list if append happened first, but game won't start.
                # A more robust cleanup would involve checking if (rfile, wfile, addr) is in players and removing it.
                # However, if wfile.write fails, the connection is likely already dead.
                if (rfile, wfile, addr) in players:
                    players.remove((rfile, wfile, addr))
                try:
                    rfile.close()
                    wfile.close()
                    conn.close()
                except:
                    pass
                return

        if len(players) == 2:
            # Notify both players that the game is starting
            (r1, w1, addr1), (r2, w2, addr2) = players[0], players[1]

            players_to_start = players[:]
            players = []

            try:
                w1.write("Player 1, you are about to place your ships.\n")
                w1.flush()
                w2.write("Player 2, you are about to place your ships.\n")
                w2.flush()
            except (socket.error, BrokenPipeError):
                print(f"[INFO] A player disconnected before game could start fully. Aborting this pair.")
                # Close connections for both players in this pair
                for pr, pw, _ in players_to_start:
                    try:
                        pr.close()
                    except:
                        pass
                    try:
                        pw.close()
                    except:
                        pass
                return

            # Start the game in a new thread
            threading.Thread(
                target=run_multiplayer_game,
                args=(players_to_start[0][0], players_to_start[0][1], players_to_start[1][0], players_to_start[1][1]),
                daemon=True
            ).start()
            # The original conn objects for these clients are implicitly managed by rfile/wfile.
            # run_multiplayer_game is responsible for closing rfile/wfile.


def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        while True:
            try:
                conn, addr = s.accept()
                print(f"[INFO] Connection established with {addr}")
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"[ERROR] Error accepting connection: {e}")


if __name__ == "__main__":
    main()