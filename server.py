import socket
import threading
from battleship import Board, parse_coordinate, SHIPS, BOARD_SIZE, run_multiplayer_game

HOST = '127.0.0.1'
PORT = 5000

players = []
lock = threading.Lock()

def handle_client(conn, addr):
    global players
    rfile = conn.makefile('r')
    wfile = conn.makefile('w')

    with lock:
        if len(players) < 2:
            players.append((rfile, wfile, addr))
            wfile.write("Waiting for another player to join...\n")
            wfile.flush()

        if len(players) == 2:
            # Notify both players that the game is starting
            (r1, w1, addr1), (r2, w2, addr2) = players
            w1.write("Player 1, place your ships manually.\n")
            w1.flush()
            w2.write("Player 2, place your ships manually.\n")
            w2.flush()

            # Clear the players list to allow new games
            players = []

            # Start the game in a new thread
            threading.Thread(
                target=run_multiplayer_game,
                args=(r1, w1, r2, w2),
                daemon=True
            ).start()

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        while True:
            conn, addr = s.accept()
            print(f"[INFO] Connection established with {addr}")
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
