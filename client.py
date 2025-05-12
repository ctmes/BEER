import socket
import threading
import json

HOST = '127.0.0.1'
PORT = 5000
running = True

player_grid = [['.' for _ in range(10)] for _ in range(10)]

def send_json(wfile, obj):
    try:
        wfile.write(json.dumps(obj) + '\n')
        wfile.flush()
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        return False
    return True

def print_board(grid, title="[Board]"):
    print(f"\n{title}")
    print("  " + " ".join(str(i + 1).rjust(2) for i in range(len(grid[0]))))
    for r in range(len(grid)):
        row_label = chr(ord('A') + r)
        row_str = " ".join(grid[r])
        print(f"{row_label:2} {row_str}")
    print()

def simulate_placement(row, col, size, orient):
    if orient == 'H':
        if col + size > 10:
            return False
        for c in range(col, col + size):
            if player_grid[row][c] != '.':
                return False
        for c in range(col, col + size):
            player_grid[row][c] = 'S'
    else:
        if row + size > 10:
            return False
        for r in range(row, row + size):
            if player_grid[r][col] != '.':
                return False
        for r in range(row, row + size):
            player_grid[r][col] = 'S'
    return True

def receive_messages(rfile, wfile):
    global running

    while running:
        line = rfile.readline()
        if not line:
            print("\n[INFO] Server disconnected.")
            running = False
            break

        try:
            msg = json.loads(line)
        except:
            print("[ERROR] Malformed server message.")
            continue

        msg_type = msg.get("type")

        if msg_type == "status":
            print(f"\n[SERVER] {msg.get('message')}")
        elif msg_type == "prompt" and msg.get("action") == "place":
            ship = msg["ship"]
            size = msg["size"]
            while True:
                print_board(player_grid, f"[Your Board - Placing {ship} (size {size})]")
                print("  Start coordinate (e.g. A1): ", end="")
                coord = input().strip()
                print("  Orientation (H or V): ", end="")
                orient = input().strip().upper()

                try:
                    row = ord(coord[0].upper()) - ord('A')
                    col = int(coord[1:]) - 1
                    if not (0 <= row < 10 and 0 <= col < 10):
                        raise ValueError("Coordinate out of bounds.")
                    if orient not in ('H', 'V'):
                        raise ValueError("Orientation must be 'H' or 'V'.")

                    if not simulate_placement(row, col, size, orient):
                        print("[!] Invalid placement (out of bounds or overlapping). Try again.")
                        continue

                    send_json(wfile, {
                        "action": "place",
                        "ship": ship,
                        "start": coord.upper(),
                        "orientation": orient
                    })
                    break
                except Exception as e:
                    print(f"[!] Invalid input: {e}")
                    continue

        elif msg_type == "prompt" and msg.get("action") == "fire":
            print("\nEnter coordinate to fire at (e.g. B5): ", end="")
            coord = input().strip()
            send_json(wfile, {"action": "fire", "coordinate": coord})
        elif msg_type == "result":
            if msg["result"] == "hit":
                print(">> HIT!", f"You sank the {msg['sunk']}!" if msg.get("sunk") else "")
            elif msg["result"] == "miss":
                print(">> MISS!")
        elif msg_type == "board":
            print_board(msg["grid"], "[Opponent's Board]")
        elif msg_type == "error":
            print("[ERROR]", msg.get("message"))

def main():
    global running
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            rfile = s.makefile('r')
            wfile = s.makefile('w')

            print("Type 'quit' to exit any time.")
            threading.Thread(target=receive_messages, args=(rfile, wfile), daemon=True).start()

            while running:
                cmd = input().strip()
                if cmd.lower() == "quit":
                    send_json(wfile, {"action": "quit"})
                    running = False
                    break
    except Exception as e:
        print(f"[FATAL] Connection error: {e}")

if __name__ == "__main__":
    main()
