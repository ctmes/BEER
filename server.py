import socket
import threading
from battleship import Board, parse_coordinate, SHIPS, BOARD_SIZE, run_multiplayer_game

HOST = '127.0.0.1'
PORT = 5001

players = []
spectators = []
lock = threading.Lock()


def handle_client(conn, addr):
    global players, spectators
    rfile = conn.makefile('r')
    wfile = conn.makefile('w')

    with lock:
        if len(players) < 2:
            # Add player to the list if there are less than 2 players
            players.append((rfile, wfile, addr))
            try:
                wfile.write("Waiting for another player to join...\n")
                wfile.flush()
            except (socket.error, BrokenPipeError):
                print(f"[INFO] Client {addr} disconnected before pairing.")
                if (rfile, wfile, addr) in players:
                    players.remove((rfile, wfile, addr))
                try:
                    rfile.close()
                    wfile.close()
                    conn.close()
                except:
                    pass
                return

            # If two players are now connected, start the game
            if len(players) == 2:
                # Notify both players that the game is starting
                (r1, w1, addr1), (r2, w2, addr2) = players[0], players[1]
                players_to_start = players[:]
                

                try:
                    w1.write("Player 1, you are about to place your ships.\n")
                    w1.flush()
                    w2.write("Player 2, you are about to place your ships.\n")
                    w2.flush()
                except (socket.error, BrokenPipeError):
                    print(f"[INFO] A player disconnected before the game could start fully. Aborting this pair.")
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
                    args=(players_to_start[0][0], players_to_start[0][1], players_to_start[1][0], players_to_start[1][1], spectators),
                    daemon=True
                ).start()

        else:
            # After the first two players, the client becomes a spectator
            spectators.append({"r": rfile, "w": wfile, "addr": addr})
            try:
                # Send a welcome message to the spectator
                wfile.write("You are a spectator. You will receive real-time updates about the game.\n")
                wfile.flush()

                

            except (socket.error, BrokenPipeError):
                print(f"[INFO] Spectator {addr} disconnected before receiving any updates.")
                if {"r": rfile, "w": wfile, "addr": addr} in spectators:
                    spectators.remove({"r": rfile, "w": wfile, "addr": addr})
                try:
                    rfile.close()
                    wfile.close()
                    conn.close()
                except:
                    pass
                return


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
