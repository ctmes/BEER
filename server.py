import socket
import threading
import json
from battleship import Board, parse_coordinate, SHIPS, BOARD_SIZE

HOST = '127.0.0.1'
PORT = 5000

players = []
lock = threading.Lock()

def send_json(wfile, obj):
    wfile.write(json.dumps(obj) + '\n')
    wfile.flush()

def recv_json(rfile):
    try:
        return json.loads(rfile.readline())
    except:
        return None

def send_board(wfile, board):
    send_json(wfile, {
        "type": "board",
        "grid": board.display_grid
    })

def handle_placement(rfile, wfile):
    board = Board(BOARD_SIZE)
    for ship_name, ship_size in SHIPS:
        placed = False
        while not placed:
            send_json(wfile, {
                "type": "prompt",
                "action": "place",
                "ship": ship_name,
                "size": ship_size
            })
            request = recv_json(rfile)
            if not request or request.get("action") != "place":
                send_json(wfile, {"type": "error", "message": "Expected a ship placement."})
                continue

            if request.get("ship") != ship_name:
                send_json(wfile, {"type": "error", "message": f"Expected to place {ship_name}."})
                continue

            try:
                row, col = parse_coordinate(request.get("start"))
                orientation = request.get("orientation").upper()
                orient_code = 0 if orientation == 'H' else 1 if orientation == 'V' else -1
                if orient_code not in (0, 1):
                    raise ValueError("Invalid orientation.")

                if not board.can_place_ship(row, col, ship_size, orient_code):
                    send_json(wfile, {"type": "error", "message": "Invalid position or overlap. Try again."})
                    continue

                occupied = board.do_place_ship(row, col, ship_size, orient_code)
                board.placed_ships.append({
                    'name': ship_name,
                    'positions': occupied
                })
                send_json(wfile, {"type": "status", "message": f"{ship_name} placed."})
                placed = True

            except Exception as e:
                send_json(wfile, {"type": "error", "message": str(e)})
    return board

def handle_game():
    p1, p2 = players
    (r1, w1, addr1) = p1
    (r2, w2, addr2) = p2

    send_json(w1, {"type": "status", "message": "Welcome Player 1. Place your ships."})
    board1 = handle_placement(r1, w1)

    send_json(w2, {"type": "status", "message": "Welcome Player 2. Place your ships."})
    board2 = handle_placement(r2, w2)

    send_json(w1, {"type": "status", "message": "All ships placed. Game starts now."})
    send_json(w2, {"type": "status", "message": "All ships placed. Game starts now."})

    turn = 0
    while True:
        attacker = (r1, w1, board2, "Player 1") if turn % 2 == 0 else (r2, w2, board1, "Player 2")
        defender_wfile = w2 if turn % 2 == 0 else w1

        rfile, wfile, opponent_board, attacker_name = attacker

        send_json(wfile, {"type": "status", "message": f"Your turn, {attacker_name}."})
        send_board(wfile, opponent_board)
        send_json(wfile, {"type": "prompt", "action": "fire"})

        request = recv_json(rfile)
        if not request or request.get("action") == "quit":
            send_json(wfile, {"type": "status", "message": "You quit. Game over."})
            send_json(defender_wfile, {"type": "status", "message": f"{attacker_name} quit. You win!"})
            break

        if request.get("action") == "fire":
            try:
                row, col = parse_coordinate(request.get("coordinate"))
                result, sunk = opponent_board.fire_at(row, col)

                if result == "hit":
                    send_json(wfile, {"type": "result", "result": "hit", "sunk": sunk})
                    send_json(defender_wfile, {
                        "type": "status",
                        "message": f"{attacker_name} hit your ship at {request.get('coordinate')}."
                    })
                elif result == "miss":
                    send_json(wfile, {"type": "result", "result": "miss"})
                    send_json(defender_wfile, {
                        "type": "status",
                        "message": f"{attacker_name} missed at {request.get('coordinate')}."
                    })
                elif result == "already_shot":
                    send_json(wfile, {"type": "error", "message": "Already fired at that location."})
                    continue

                if opponent_board.all_ships_sunk():
                    send_json(wfile, {"type": "status", "message": "All ships sunk. You win!"})
                    send_json(defender_wfile, {"type": "status", "message": "All your ships have been sunk. You lose!"})
                    break

                turn += 1
            except Exception as e:
                send_json(wfile, {"type": "error", "message": f"Invalid coordinate: {e}"})
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
            send_json(wfile, {"type": "status", "message": "Waiting for another player to join..."})
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
