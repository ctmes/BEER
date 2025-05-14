"""
battleship.py

Contains core data structures and logic for Battleship, including:
 - Board class for storing ship positions, hits, misses
 - Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)
 - A test harness run_single_player_game() to demonstrate the logic in a local, single-player mode
 - run_multiplayer_game() for networked play, now with disconnection handling.
"""

import random
import threading
import socket # For socket.error and network operations

BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2)
]


class PlayerDisconnectedException(Exception):
    """Custom exception for handling player disconnections during the game."""
    pass


class Board:
    """
    Represents a single Battleship board with hidden ships.
    """

    def __init__(self, size=BOARD_SIZE):
        self.size = size
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.placed_ships = [] # List of dicts: {'name': str, 'positions': set_of_tuples}

    def place_ships_randomly(self, ships=SHIPS):
        for ship_name, ship_size in ships:
            placed = False
            while not placed:
                orientation = random.randint(0, 1) # 0: H, 1: V
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({'name': ship_name, 'positions': occupied_positions.copy()})
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

                orientation = 0 if orientation_str == 'H' else 1 if orientation_str == 'V' else -1
                if orientation == -1:
                    print("  [!] Invalid orientation. Please enter 'H' or 'V'.")
                    continue

                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({'name': ship_name, 'positions': occupied_positions.copy()})
                    break
                else:
                    print(f"  [!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again.")


    def can_place_ship(self, row, col, ship_size, orientation):
        if orientation == 0:  # Horizontal
            if not (0 <= row < self.size and 0 <= col < self.size and col + ship_size <= self.size): return False
            for c in range(col, col + ship_size):
                if self.hidden_grid[row][c] != '.': return False
        else:  # Vertical
            if not (0 <= row < self.size and 0 <= col < self.size and row + ship_size <= self.size): return False
            for r in range(row, row + ship_size):
                if self.hidden_grid[r][col] != '.': return False
        return True

    def do_place_ship(self, row, col, ship_size, orientation):
        occupied = set()
        if orientation == 0:  # Horizontal
            for c in range(col, col + ship_size):
                self.hidden_grid[row][c] = 'S'
                occupied.add((row, c))
        else:  # Vertical
            for r in range(row, row + ship_size):
                self.hidden_grid[r][col] = 'S'
                occupied.add((r, col))
        return occupied

    def fire_at(self, row, col):
        if not (0 <= row < self.size and 0 <= col < self.size):
            # This should ideally be validated before calling, e.g., by parse_coordinate
            raise ValueError("Coordinate out of bounds")

        cell = self.hidden_grid[row][col]
        if cell == 'S':
            self.hidden_grid[row][col] = 'X'
            self.display_grid[row][col] = 'X'
            sunk_ship_name = self._mark_hit_and_check_sunk(row, col)
            return ('hit', sunk_ship_name)
        elif cell == '.':
            self.hidden_grid[row][col] = 'o'
            self.display_grid[row][col] = 'o'
            return ('miss', None)
        elif cell in ('X', 'o'):
            return ('already_shot', None)
        return ('error', "Unknown cell state") # Should not happen

    def _mark_hit_and_check_sunk(self, row, col):
        for ship in self.placed_ships:
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if not ship['positions']:
                    return ship['name']
                break
        return None

    def all_ships_sunk(self):
        if not self.placed_ships: return False # No ships placed means none can be sunk.
        return all(not ship['positions'] for ship in self.placed_ships)

    def print_display_grid(self, show_hidden_board=False):
        grid_to_print = self.hidden_grid if show_hidden_board else self.display_grid
        print("  " + "".join(str(i + 1).rjust(2) for i in range(self.size)))
        for r_idx in range(self.size):
            row_label = chr(ord('A') + r_idx)
            row_str = " ".join(grid_to_print[r_idx][c_idx] for c_idx in range(self.size))
            print(f"{row_label:2} {row_str}")


def parse_coordinate(coord_str):
    coord_str = coord_str.strip().upper()
    if not (2 <= len(coord_str) <= 3): raise ValueError(f"Invalid coordinate format '{coord_str}'. Expected e.g., A1 or J10.")
    row_letter = coord_str[0]
    col_digits = coord_str[1:]
    if not ('A' <= row_letter < chr(ord('A') + BOARD_SIZE)):
        raise ValueError(f"Invalid row letter '{row_letter}'. Must be A-{chr(ord('A') + BOARD_SIZE - 1)}.")
    if not col_digits.isdigit(): raise ValueError("Column part must be a number.")

    col = int(col_digits) - 1
    row = ord(row_letter) - ord('A')

    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
        raise ValueError(f"Coordinate ({row_letter}{col_digits}) out of board range (A1-{chr(ord('A') + BOARD_SIZE - 1)}{BOARD_SIZE}).")
    return (row, col)


def run_multiplayer_game(rfile1, wfile1, rfile2, wfile2):
    player_files = {
        "Player 1": {"r": rfile1, "w": wfile1, "addr": "Unknown"}, # Addr could be passed if needed for logs
        "Player 2": {"r": rfile2, "w": wfile2, "addr": "Unknown"}
    }
    player_boards = {"Player 1": Board(BOARD_SIZE), "Player 2": Board(BOARD_SIZE)}

    def send_msg_to_player(player_tag, message):
        wfile = player_files[player_tag]["w"]
        try:
            wfile.write(message + '\n')
            wfile.flush()
        except (socket.error, BrokenPipeError, ConnectionResetError) as e:
            raise PlayerDisconnectedException(f"{player_tag} disconnected (send error: {e})")

    def recv_msg_from_player(player_tag):
        rfile = player_files[player_tag]["r"]
        try:
            line = rfile.readline()
            if not line:
                raise PlayerDisconnectedException(f"{player_tag} disconnected (EOF on read)")
            return line.strip()
        except UnicodeDecodeError as e: # Catch garbled input before socket error
             raise PlayerDisconnectedException(f"{player_tag} sent invalid data (decode error: {e}), assuming disconnect.")
        except (socket.error, ConnectionResetError) as e:
            raise PlayerDisconnectedException(f"{player_tag} disconnected (read error: {e})")

    def send_board_to_player(player_tag, board_to_send, show_hidden=False):
        wfile = player_files[player_tag]["w"]
        try:
            wfile.write("GRID\n")
            grid_data = board_to_send.hidden_grid if show_hidden else board_to_send.display_grid
            header = "  " + "".join(str(i + 1).rjust(2) for i in range(board_to_send.size)) + '\n'
            wfile.write(header)
            for r_idx in range(board_to_send.size):
                row_label = chr(ord('A') + r_idx)
                row_str = " ".join(grid_data[r_idx][c_idx] for c_idx in range(board_to_send.size))
                wfile.write(f"{row_label:2} {row_str}\n")
            wfile.write('\n')
            wfile.flush()
        except (socket.error, BrokenPipeError, ConnectionResetError) as e:
            raise PlayerDisconnectedException(f"{player_tag} disconnected (send_board error: {e})")

    def place_ships_for_player(player_tag):
        board = player_boards[player_tag]
        send_msg_to_player(player_tag, f"Welcome, {player_tag}. It's time to place your ships.")
        for ship_name, ship_size in SHIPS:
            while True:
                send_msg_to_player(player_tag, f"\n{player_tag}, your current board setup:")
                send_board_to_player(player_tag, board, show_hidden=True)
                send_msg_to_player(player_tag, f"Place your {ship_name} (size {ship_size}).")

                send_msg_to_player(player_tag, "Enter start coordinate (e.g., A1) or type 'quit' to exit:")
                coord_str = recv_msg_from_player(player_tag)
                if coord_str.lower() == 'quit':
                    raise PlayerDisconnectedException(f"{player_tag} quit during ship placement.")

                send_msg_to_player(player_tag, "Enter orientation ('H' or 'V') or type 'quit' to exit:")
                orient_str = recv_msg_from_player(player_tag).upper()
                if orient_str.lower() == 'quit':
                    raise PlayerDisconnectedException(f"{player_tag} quit during ship placement.")

                try:
                    row, col = parse_coordinate(coord_str)
                    orientation = 0 if orient_str == 'H' else 1 if orient_str == 'V' else -1
                    if orientation == -1:
                        send_msg_to_player(player_tag, "[!] Invalid orientation. Use 'H' for horizontal or 'V' for vertical.")
                        continue
                    if board.can_place_ship(row, col, ship_size, orientation):
                        positions = board.do_place_ship(row, col, ship_size, orientation)
                        board.placed_ships.append({'name': ship_name, 'positions': positions.copy()})
                        send_msg_to_player(player_tag, f"{ship_name} placed successfully at {coord_str}{orient_str}.")
                        break
                    else:
                        send_msg_to_player(player_tag, f"[!] Cannot place {ship_name} at {coord_str}{orient_str}. It overlaps or is out of bounds.")
                except ValueError as e: # From parse_coordinate
                    send_msg_to_player(player_tag, f"[!] Invalid input for {ship_name}: {e}")

        send_msg_to_player(player_tag, f"\n{player_tag}, all your ships have been placed:")
        send_board_to_player(player_tag, board, show_hidden=True)
        send_msg_to_player(player_tag, "Waiting for the other player to finish placing ships...")

    game_active = True
    try:
        placement_threads = []
        placement_status = {}

        def placement_worker(p_tag):
            try:
                place_ships_for_player(p_tag)
                placement_status[p_tag] = "success"
            except PlayerDisconnectedException as e_disconnect:
                placement_status[p_tag] = e_disconnect
            except Exception as e_other:
                print(f"[ERROR] Unexpected critical error in {p_tag} placement thread: {e_other}")
                placement_status[p_tag] = PlayerDisconnectedException(f"{p_tag} had a critical error during placement: {e_other}")

        for p_tag_worker in ["Player 1", "Player 2"]:
            thread = threading.Thread(target=placement_worker, args=(p_tag_worker,))
            placement_threads.append(thread)
            thread.start()
        for thread in placement_threads:
            thread.join()

        for p_tag_check in ["Player 1", "Player 2"]:
            status = placement_status.get(p_tag_check)
            if isinstance(status, PlayerDisconnectedException):
                raise status
            if status != "success":
                 raise PlayerDisconnectedException(f"{p_tag_check} failed ship placement unexpectedly (status: {status}).")

        send_msg_to_player("Player 1", "\nBoth players have placed ships. The battle begins!")
        send_msg_to_player("Player 2", "\nBoth players have placed ships. The battle begins!")

        turn = 0
        while game_active:
            current_player_tag = "Player 1" if turn % 2 == 0 else "Player 2"
            opponent_player_tag = "Player 2" if turn % 2 == 0 else "Player 1"

            opponent_board = player_boards[opponent_player_tag]

            send_msg_to_player(current_player_tag, f"\n--- {current_player_tag}, it's your turn! ---")
            send_msg_to_player(current_player_tag, f"Your view of {opponent_player_tag}'s board:")
            send_board_to_player(current_player_tag, opponent_board, show_hidden=False)
            send_msg_to_player(opponent_player_tag, f"\nWaiting for {current_player_tag} to make a move...")

            send_msg_to_player(current_player_tag, "Enter coordinate to fire (e.g., A1) or type 'quit' to exit:")
            guess = recv_msg_from_player(current_player_tag)

            if guess.lower() == 'quit':
                game_active = False
                send_msg_to_player(current_player_tag, "You have quit the game. Game over.")
                send_msg_to_player(opponent_player_tag, f"{current_player_tag} has quit the game. Game over.")
                continue

            try:
                row, col = parse_coordinate(guess)
                result, sunk_ship = opponent_board.fire_at(row, col)

                msg_active = f"You fired at {guess.upper()}: "
                msg_opponent = f"{current_player_tag} fired at {guess.upper()}: "

                if result == 'hit':
                    if sunk_ship:
                        msg_active += f"HIT! You sank their {sunk_ship}!"
                        msg_opponent += f"HIT! Your {sunk_ship} has been SUNK!"
                    else:
                        msg_active += "HIT!"
                        msg_opponent += "HIT on one of your ships!"
                elif result == 'miss':
                    msg_active += "MISS."
                    msg_opponent += "MISS."
                elif result == 'already_shot':
                    msg_active += "ALREADY SHOT there. Your turn is wasted."
                    msg_opponent += "They fired at an already targeted location."

                send_msg_to_player(current_player_tag, msg_active)
                send_msg_to_player(opponent_player_tag, msg_opponent)

                send_msg_to_player(opponent_player_tag, f"\n{opponent_player_tag}'s board after {current_player_tag}'s shot:")
                send_board_to_player(opponent_player_tag, opponent_board, show_hidden=True)

                if opponent_board.all_ships_sunk():
                    game_active = False
                    final_win_msg = f"GAME OVER! {current_player_tag} WINS! All {opponent_player_tag}'s ships are sunk."
                    send_msg_to_player(current_player_tag, final_win_msg)
                    send_msg_to_player(current_player_tag, f"\nFinal state of {opponent_player_tag}'s board (what you saw):")
                    send_board_to_player(current_player_tag, opponent_board, show_hidden=False)

                    send_msg_to_player(opponent_player_tag, final_win_msg)
                    send_msg_to_player(opponent_player_tag, f"\nYour final board state (all ships shown):")
                    send_board_to_player(opponent_player_tag, opponent_board, show_hidden=True)
                    continue

                turn += 1
            except ValueError as e:
                send_msg_to_player(current_player_tag, f"[!] Invalid move input ('{guess}'): {e}. Please try again this turn.")

    except PlayerDisconnectedException as e:
        game_active = False
        disconnected_message = str(e)
        print(f"[GAME INFO] A player disconnected: {disconnected_message}. Game ending.")

        remaining_player_tag = None
        if "Player 1" in disconnected_message: remaining_player_tag = "Player 2"
        elif "Player 2" in disconnected_message: remaining_player_tag = "Player 1"

        if remaining_player_tag:
            try: send_msg_to_player(remaining_player_tag, f"Your opponent ({disconnected_message.split(' (')[0]}) has disconnected or quit. Game over.")
            except PlayerDisconnectedException:
                print(f"[GAME INFO] {remaining_player_tag} also disconnected or unreachable while notifying of opponent's disconnect.")
        else: # Should not happen if PlayerDisconnectedException is tagged.
             print(f"[GAME INFO] Could not determine remaining player to notify from message: {disconnected_message}")


    except Exception as e_critical:
        game_active = False
        print(f"[CRITICAL ERROR in run_multiplayer_game] Type: {type(e_critical)}, Error: {e_critical}")
        error_msg_to_send = "A critical server error occurred in the game. Game over."
        for p_tag_crit in ["Player 1", "Player 2"]:
            try: send_msg_to_player(p_tag_crit, error_msg_to_send)
            except: pass

    finally:
        print(f"[INFO] run_multiplayer_game ({player_files['Player 1'].get('addr','P1')} vs {player_files['Player 2'].get('addr','P2')}) is concluding.")
        final_msg = "The game session has ended. Goodbye."
        if not game_active and not isinstance(e_critical if 'e_critical' in locals() else None, Exception) \
           and not isinstance(e if 'e' in locals() and isinstance(e, PlayerDisconnectedException) else None, PlayerDisconnectedException) :
             # This means game ended somewhat normally (win or quit command)
             pass # Specific messages already sent
        else: # Disconnection or critical error
            final_msg = "The game session has ended due to an issue or disconnection. Goodbye."


        for p_tag_final in ["Player 1", "Player 2"]:
            wfile = player_files[p_tag_final]["w"]
            rfile = player_files[p_tag_final]["r"]
            if wfile and not wfile.closed:
                try:
                    wfile.write(final_msg + '\n')
                    wfile.flush()
                except: pass
                finally:
                    try: wfile.close()
                    except: pass
            if rfile and not rfile.closed:
                try: rfile.close()
                except: pass


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
                print(f"  >> HIT! You sank the {sunk_name}!" if sunk_name else "  >> HIT!")
                if board.all_ships_sunk():
                    board.print_display_grid()
                    print(f"\nCongratulations! You sank all ships in {moves} moves.")
                    break
            elif result == 'miss': print("  >> MISS!")
            elif result == 'already_shot': print("  >> You've already fired there. Try again.")
        except ValueError as e: print(f"  >> Invalid input: {e}")


if __name__ == "__main__":
    run_single_player_game_locally()