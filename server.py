import socket
import threading
from battleship import Board, parse_coordinate, SHIPS, BOARD_SIZE

HOST = '127.0.0.1'
PORT = 5000

players = []
lock = threading.Lock()

def send(wfile, msg):
    wfile.write(msg + '\n')
    wfile.flush()

def send_board(wfile, board):
    send(wfile, "GRID")
    wfile.write("  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)) + '\n')
    for r in range(board.size):
        row_label = chr(ord('A') + r)
        row_str = " ".join(board.display_grid[r][c] for c in range(board.size))
        wfile.write(f"{row_label:2} {row_str}\n")
    wfile.write('\n')
    wfile.flush()

def handle_game():
    p1, p2 = players
    (r1, w1, addr1) = p1
    (r2, w2, addr2) = p2

    board1 = Board(BOARD_SIZE)
    board2 = Board(BOARD_SIZE)
    board1.place_ships_randomly(SHIPS)
    board2.place_ships_randomly(SHIPS)

    send(w1, "Welcome Player 1! Game starting.")
    send(w2, "Welcome Player 2! Game starting.")

    turn = 0
    while True:
        attacker = (r1, w1, board2, "Player 1") if turn % 2 == 0 else (r2, w2, board1, "Player 2")
        defender_wfile = w2 if turn % 2 == 0 else w1

        rfile, wfile, opponent_board, attacker_name = attacker

        send(wfile, f"Your turn, {attacker_name}.")
        send_board(wfile, opponent_board)
        send(wfile, "Enter coordinate to fire at (e.g. B5):")
        guess = rfile.readline().strip()
        if not guess:
            break
        if guess.lower() == "quit":
            send(wfile, "You quit. Game over.")
            send(defender_wfile, f"{attacker_name} quit. You win!")
            break

        try:
            row, col = parse_coordinate(guess)
            result, sunk = opponent_board.fire_at(row, col)

            if result == "hit":
                send(wfile, "HIT!" + (f" You sank the {sunk}!" if sunk else ""))
                send(defender_wfile, f"{attacker_name} hit your ship at {guess}!")
            elif result == "miss":
                send(wfile, "MISS!")
                send(defender_wfile, f"{attacker_name} missed at {guess}.")
            elif result == "already_shot":
                send(wfile, "You already fired at that location. Try again.")
                continue

            if opponent_board.all_ships_sunk():
                send(wfile, "All ships sunk. You win!")
                send(defender_wfile, "All your ships have been sunk. You lose!")
                break

            turn += 1

        except Exception as e:
            send(wfile, f"Invalid input: {e}")
            continue

    w1.close()
    w2.close()

def handle_client(conn, addr):
    global players
    rfile = conn.makefile('r')
    wfile = conn.makefile('w')

    with lock:
        if len(players) < 2:
            players.append((rfile, wfile, addr))
            send(wfile, "Waiting for another player to join...")
        if len(players) == 2:
            game_thread = threading.Thread(target=handle_game, daemon=True)
            game_thread.start()

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
