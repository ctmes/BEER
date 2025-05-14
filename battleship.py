"""
battleship.py

Contains core data structures and logic for Battleship, including:
 - Board class for storing ship positions, hits, misses
 - Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)
 - A test harness run_single_player_game() to demonstrate the logic in a local, single-player mode
"""

import random
import threading
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2)
]

class Board:
    """
    Represents a single Battleship board with hidden ships.
    We store:
      - self.hidden_grid: tracks real positions of ships ('S'), hits ('X'), misses ('o')
      - self.display_grid: the version we show to the player ('.' for unknown, 'X' for hits, 'o' for misses)
      - self.placed_ships: a list of dicts, each dict with:
          {
             'name': <ship_name>,
             'positions': set of (r, c),
          }
        used to determine when a specific ship has been fully sunk.
    """
    def __init__(self, size=BOARD_SIZE):
        self.size = size
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.placed_ships = []

    def place_ships_randomly(self, ships=SHIPS):
        for ship_name, ship_size in ships:
            placed = False
            while not placed:
                orientation = random.randint(0, 1)
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    placed = True

    def place_ships_manually(self, ships=SHIPS):
        print("\nPlease place your ships manually on the board.")
        for ship_name, ship_size in ships:
            while True:
                self.print_display_grid(show_hidden_board=True)
                print(f"\nPlacing your {ship_name} (size {ship_size}).")
                coord_str = input("  Enter starting coordinate (e.g. A1): ").strip()
                orientation_str = input("  Orientation? Enter 'H' (horizontal) or 'V' (vertical): ").strip().upper()
                try:
                    row, col = parse_coordinate(coord_str)
                except ValueError as e:
                    print(f"  [!] Invalid coordinate: {e}")
                    continue
                if orientation_str == 'H':
                    orientation = 0
                elif orientation_str == 'V':
                    orientation = 1
                else:
                    print("  [!] Invalid orientation. Please enter 'H' or 'V'.")
                    continue
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    break
                else:
                    print(f"  [!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again.")

    def can_place_ship(self, row, col, ship_size, orientation):
        if orientation == 0:
            if col + ship_size > self.size:
                return False
            for c in range(col, col + ship_size):
                if self.hidden_grid[row][c] != '.':
                    return False
        else:
            if row + ship_size > self.size:
                return False
            for r in range(row, row + ship_size):
                if self.hidden_grid[r][col] != '.':
                    return False
        return True

    def do_place_ship(self, row, col, ship_size, orientation):
        occupied = set()
        if orientation == 0:
            for c in range(col, col + ship_size):
                self.hidden_grid[row][c] = 'S'
                occupied.add((row, c))
        else:
            for r in range(row, row + ship_size):
                self.hidden_grid[r][col] = 'S'
                occupied.add((r, c))
        return occupied

    def fire_at(self, row, col):
        cell = self.hidden_grid[row][col]
        if cell == 'S':
            self.hidden_grid[row][col] = 'X'
            self.display_grid[row][col] = 'X'
            sunk_ship_name = self._mark_hit_and_check_sunk(row, col)
            if sunk_ship_name:
                return ('hit', sunk_ship_name)
            else:
                return ('hit', None)
        elif cell == '.':
            self.hidden_grid[row][col] = 'o'
            self.display_grid[row][col] = 'o'
            return ('miss', None)
        elif cell == 'X' or cell == 'o':
            return ('already_shot', None)
        else:
            return ('already_shot', None)

    def _mark_hit_and_check_sunk(self, row, col):
        for ship in self.placed_ships:
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if len(ship['positions']) == 0:
                    return ship['name']
                break
        return None

    def all_ships_sunk(self):
        for ship in self.placed_ships:
            if len(ship['positions']) > 0:
                return False
        return True

    def print_display_grid(self, show_hidden_board=False):
        grid_to_print = self.hidden_grid if show_hidden_board else self.display_grid
        print("  " + "".join(str(i + 1).rjust(2) for i in range(self.size)))
        for r in range(self.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(grid_to_print[r][c] for c in range(self.size))
            print(f"{row_label:2} {row_str}")

def parse_coordinate(coord_str):
    coord_str = coord_str.strip().upper()
    row_letter = coord_str[0]
    col_digits = coord_str[1:]
    row = ord(row_letter) - ord('A')
    col = int(col_digits) - 1
    return (row, col)

def run_single_player_game_locally():
    board = Board(BOARD_SIZE)
    choice = input("Place ships manually (M) or randomly (R)? [M/R]: ").strip().upper()
    if choice == 'M':
        board.place_ships_manually(SHIPS)
    else:
        board.place_ships_randomly(SHIPS)
    print("\nNow try to sink all the ships!")
    moves = 0
    while True:
        board.print_display_grid()
        guess = input("\nEnter coordinate to fire at (or 'quit'): ").strip()
        if guess.lower() == 'quit':
            print("Thanks for playing. Exiting...")
            return
        try:
            row, col = parse_coordinate(guess)
            result, sunk_name = board.fire_at(row, col)
            moves += 1
            if result == 'hit':
                if sunk_name:
                    print(f"  >> HIT! You sank the {sunk_name}!")
                else:
                    print("  >> HIT!")
                if board.all_ships_sunk():
                    board.print_display_grid()
                    print(f"\nCongratulations! You sank all ships in {moves} moves.")
                    break
            elif result == 'miss':
                print("  >> MISS!")
            elif result == 'already_shot':
                print("  >> You've already fired at that location. Try again.")
        except ValueError as e:
            print("  >> Invalid input:", e)

def run_multiplayer_game(rfile1, wfile1, rfile2, wfile2, conn1, conn2):
    """
    A multiplayer Battleship game for two players where players place ships simultaneously
    and then alternate turns. Handles client disconnections by notifying the other player
    and resetting the game state.
    """
    from server import players, lock, clients
    logging.debug("Starting run_multiplayer_game for players with connections %s, %s", conn1, conn2)

    def network_place_ships(board, ships, rfile, wfile, player_name, conn):
        logging.debug("Starting ship placement for Player %s", player_name)
        for ship_name, ship_size in ships:
            while True:
                try:
                    send_board(board, wfile)
                    send(f"Placing your {ship_name} (size {ship_size})", wfile)
                    send("Enter starting coordinate (e.g. A1):", wfile)
                    coord_str = recv(rfile)
                    logging.debug("Player %s sent coordinate: %s", player_name, coord_str)
                    send("Orientation? Enter 'H' (horizontal) or 'V' (vertical):", wfile)
                    orientation_str = recv(rfile)
                    logging.debug("Player %s sent orientation: %s", player_name, orientation_str)
                    orientation_str = orientation_str.upper()
                    try:
                        row, col = parse_coordinate(coord_str)
                    except ValueError as e:
                        send(f"[!] Invalid coordinate: {e}", wfile)
                        continue
                    if orientation_str == 'H':
                        orientation = 0
                    elif orientation_str == 'V':
                        orientation = 1
                    else:
                        send("[!] Invalid orientation. Please enter 'H' or 'V'.", wfile)
                        continue
                    if board.can_place_ship(row, col, ship_size, orientation):
                        occupied_positions = board.do_place_ship(row, col, ship_size, orientation)
                        board.placed_ships.append({
                            'name': ship_name,
                            'positions': occupied_positions
                        })
                        break
                    else:
                        send(f"[!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again.")
                except (ConnectionError, BrokenPipeError, OSError) as e:
                    logging.error("Connection error for Player %s: %s", player_name, e)
                    handle_disconnect(player_name, conn)
                    raise
        send(f"Player {player_name}, you have finished placing all your ships.", wfile)
        logging.debug("Player %s completed ship placement", player_name)

    def send(msg, wfile):
        try:
            wfile.write(msg + '\n')
            wfile.flush()
        except (BrokenPipeError, OSError):
            raise ConnectionError("Client disconnected")

    def send_board(board, wfile):
        try:
            wfile.write("GRID\n")
            wfile.write("  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)) + '\n')
            for r in range(board.size):
                row_label = chr(ord('A') + r)
                row_str = " ".join(board.display_grid[r][c] for c in range(board.size))
                wfile.write(f"{row_label:2} {row_str}\n")
            wfile.write('\n')
            wfile.flush()
        except (BrokenPipeError, OSError):
            raise ConnectionError("Client disconnected")

    def recv(rfile):
        line = rfile.readline().strip()
        if not line:
            raise ConnectionError("Client disconnected")
        return line

    def handle_disconnect(player_name, conn):
        """Notify the other player and reset game state."""
        logging.debug("Handling disconnection for Player %s", player_name)
        opponent_conn = conn2 if conn == conn1 else conn1
        opponent_wfile = wfile2 if conn == conn1 else wfile1
        try:
            send(f"[INFO] Player {player_name} disconnected. Game aborted.", opponent_wfile)
            send("Waiting for another player to join...", opponent_wfile)
        except:
            logging.warning("Failed to notify opponent of Player %s disconnection", player_name)
        with lock:
            players[:] = [(r, w, a, c) for r, w, a, c in players if c != conn]
            if opponent_conn in clients:
                players.append((opponent_rfile, opponent_wfile, opponent_addr, opponent_conn))
        try:
            conn.close()
        except:
            pass
        logging.debug("Player %s disconnection handled", player_name)

    # Initialize boards and player info
    try:
        board1 = Board(BOARD_SIZE)
        board2 = Board(BOARD_SIZE)
        opponent_rfile = rfile2
        opponent_wfile = wfile2
        opponent_conn = conn2
        opponent_addr = players[1][2] if conn1 == players[0][3] else players[0][2]
        logging.debug("Initialized boards and opponent info")
    except Exception as e:
        logging.error("Error initializing game: %s", e)
        handle_disconnect('1', conn1)
        handle_disconnect('2', conn2)
        return

    # Place ships with disconnection handling
    try:
        thread1 = threading.Thread(target=network_place_ships, args=(board1, SHIPS, rfile1, wfile1, '1', conn1))
        thread2 = threading.Thread(target=network_place_ships, args=(board2, SHIPS, rfile2, wfile2, '2', conn2))
        logging.debug("Starting ship placement threads")
        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()
        logging.debug("Ship placement completed")
    except (ConnectionError, BrokenPipeError, OSError):
        logging.debug("Game aborted due to disconnection during ship placement")
        return

    # Confirm both players are ready
    try:
        send("Both players have finished placing ships. The game is starting!", wfile1)
        send("Both players have finished placing ships. The game is starting!", wfile2)
        logging.debug("Sent game start confirmation to both players")
    except (ConnectionError, BrokenPipeError, OSError):
        logging.debug("Game aborted due to disconnection at game start")
        handle_disconnect('1' if conn1 else '2', conn1 if conn1 else conn2)
        return

    # Game loop
    turn = 0
    while True:
        current_player = (turn % 2) + 1
        opponent_player = 2 if current_player == 1 else 1
        current_board = board1 if current_player == 1 else board2
        opponent_board = board2 if current_player == 1 else board1
        current_rfile = rfile1 if current_player == 1 else rfile2
        current_wfile = wfile1 if current_player == 1 else wfile2
        current_conn = conn1 if current_player == 1 else conn2

        try:
            send_board(current_board, current_wfile)
            send_board(opponent_board, opponent_wfile)
            send(f"Player {current_player}, enter coordinate to fire at (e.g. B5):", current_wfile)
            guess = recv(current_rfile)
            logging.debug("Player %s sent guess: %s", current_player, guess)
            if guess.lower() == 'quit':
                send("Thanks for playing. Goodbye.", current_wfile)
                handle_disconnect(str(current_player), current_conn)
                return
            row, col = parse_coordinate(guess)
            result, sunk_name = opponent_board.fire_at(row, col)
            if result == 'hit':
                if sunk_name:
                    send(f"Player {current_player}, HIT! You sank the {sunk_name}!", current_wfile)
                else:
                    send(f"Player {current_player}, HIT!", current_wfile)
            elif result == 'miss':
                send(f"Player {current_player}, MISS!", current_wfile)
            elif result == 'already_shot':
                send("You've already fired at that location. Try again.", current_wfile)
            if opponent_board.all_ships_sunk():
                send_board(current_board, current_wfile)
                send_board(opponent_board, opponent_wfile)
                send(f"Player {current_player} wins! Congratulations! You sank all the opponent's ships.", current_wfile)
                send(f"Player {current_player} wins! Congratulations! You sank all the opponent's ships.", opponent_wfile)
                logging.debug("Player %s won the game", current_player)
                return
            turn += 1
        except (ConnectionError, BrokenPipeError, OSError, ValueError) as e:
            logging.error("Error in game loop for Player %s: %s", current_player, e)
            if isinstance(e, ValueError):
                send(f"Invalid input: {e}", current_wfile)
            else:
                handle_disconnect(str(current_player), current_conn)
            return

def run_single_player_game_online(rfile, wfile):
    def send(msg):
        wfile.write(msg + '\n')
        wfile.flush()
    def send_board(board):
        wfile.write("GRID\n")
        wfile.write("  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)) + '\n')
        for r in range(board.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(board.display_grid[r][c] for c in range(board.size))
            wfile.write(f"{row_label:2} {row_str}\n")
        wfile.write('\n')
        wfile.flush()
    def recv():
        return rfile.readline().strip()
    board = Board(BOARD_SIZE)
    board.place_ships_randomly(SHIPS)
    send("Welcome to Online Single-Player Battleship! Try to sink all the ships. Type 'quit' to exit.")
    moves = 0
    while True:
        send_board(board)
        send("Enter coordinate to fire at (e.g. B5):")
        guess = recv()
        if guess.lower() == 'quit':
            send("Thanks for playing. Goodbye.")
            return
        try:
            row, col = parse_coordinate(guess)
            result, sunk_name = board.fire_at(row, col)
            moves += 1
            if result == 'hit':
                if sunk_name:
                    send(f"HIT! You sank the {sunk_name}!")
                else:
                    send("HIT!")
                if board.all_ships_sunk():
                    send_board(board)
                    send(f"Congratulations! You sank all ships in {moves} moves.")
                    return
            elif result == 'miss':
                send("MISS!")
            elif result == 'already_shot':
                send("You've already fired at that location.")
        except ValueError as e:
            send(f"Invalid input: {e}")

if __name__ == "__main__":
    run_single_player_game_locally()