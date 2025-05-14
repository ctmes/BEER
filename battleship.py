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
            for c_offset in range(ship_size):
                if self.hidden_grid[row][col + c_offset] != '.': return False
        else:  # Vertical
            if not (0 <= row < self.size and 0 <= col < self.size and row + ship_size <= self.size): return False
            for r_offset in range(ship_size):
                if self.hidden_grid[row + r_offset][col] != '.': return False
        return True

    def do_place_ship(self, row, col, ship_size, orientation):
        occupied = set()
        if orientation == 0:  # Horizontal
            for c_offset in range(ship_size):
                self.hidden_grid[row][col + c_offset] = 'S'
                occupied.add((row, col + c_offset))
        else:  # Vertical
            for r_offset in range(ship_size):
                self.hidden_grid[row + r_offset][col] = 'S'
                occupied.add((row + r_offset, col))
        return occupied

    def fire_at(self, row, col):
        # parse_coordinate should ensure row/col are valid before this is called.
        # if not (0 <= row < self.size and 0 <= col < self.size):
        #     raise ValueError("Coordinate out of bounds")

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
        return ('error', "Unknown cell state")

    def _mark_hit_and_check_sunk(self, row, col):
        for ship in self.placed_ships:
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if not ship['positions']:
                    return ship['name']
                break
        return None

    def all_ships_sunk(self):
        if not self.placed_ships: return False
        return all(not ship['positions'] for ship in self.placed_ships)

    def print_display_grid(self, show_hidden_board=False): # For local test
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
    if not col_digits.isdigit(): raise ValueError(f"Column part '{col_digits}' must be a number.")

    col = int(col_digits) - 1
    row = ord(row_letter) - ord('A')

    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE): # Check if parsed row/col are in board range
        raise ValueError(f"Coordinate {row_letter}{int(col_digits)} is out of board range (A1-{chr(ord('A') + BOARD_SIZE - 1)}{BOARD_SIZE}).")
    return (row, col)


def run_multiplayer_game(rfile1, wfile1, rfile2, wfile2):
    player_files = {
        "Player 1": {"r": rfile1, "w": wfile1},
        "Player 2": {"r": rfile2, "w": wfile2}
    }
    player_boards = {"Player 1": Board(BOARD_SIZE), "Player 2": Board(BOARD_SIZE)}

    # --- Network Helper Functions (defined inside to close over player_files) ---
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
        except UnicodeDecodeError as e:
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

    # --- Ship Placement Phase (defined inside to use helpers) ---
    def place_ships_for_player(player_tag):
        board = player_boards[player_tag]
        send_msg_to_player(player_tag, f"Welcome, {player_tag}. It's time to place your ships.")
        for ship_name, ship_size in SHIPS:
            while True: # Loop for current ship until placed
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
                    orientation_val = -1
                    if orient_str == 'H': orientation_val = 0
                    elif orient_str == 'V': orientation_val = 1

                    if orientation_val == -1:
                        send_msg_to_player(player_tag, "[!] Invalid orientation. Use 'H' for horizontal or 'V' for vertical. Try again.")
                        continue
                    if board.can_place_ship(row, col, ship_size, orientation_val):
                        positions = board.do_place_ship(row, col, ship_size, orientation_val)
                        board.placed_ships.append({'name': ship_name, 'positions': positions.copy()})
                        send_msg_to_player(player_tag, f"{ship_name} placed successfully at {coord_str}{orient_str}.")
                        break # Ship placed, exit inner while loop
                    else:
                        send_msg_to_player(player_tag, f"[!] Cannot place {ship_name} at {coord_str}{orient_str}. It overlaps existing ships or is out of bounds. Try again.")
                except ValueError as e: # From parse_coordinate
                    send_msg_to_player(player_tag, f"[!] Invalid input for {ship_name} placement: {e}. Try again.")

        send_msg_to_player(player_tag, f"\n{player_tag}, all your ships have been placed:")
        send_board_to_player(player_tag, board, show_hidden=True)
        send_msg_to_player(player_tag, "Waiting for the other player to finish placing ships...")

    # --- Main Game Logic ---
    game_active = True # Flag to control main game loop
    # Define e_main_handler and e_critical_main outside try for finally block access check
    e_main_handler = None
    e_critical_main = None

    try:
        # --- Threaded Ship Placement ---
        placement_threads = []
        placement_status = {} # Stores "success" or the exception object

        def placement_worker(p_tag_worker):
            nonlocal e_main_handler # To indicate if an error happened here
            try:
                place_ships_for_player(p_tag_worker)
                placement_status[p_tag_worker] = "success"
            except PlayerDisconnectedException as e_disconnect:
                placement_status[p_tag_worker] = e_disconnect
                e_main_handler = e_disconnect # Store first disconnect during placement
            except Exception as e_other:
                print(f"[ERROR] Unexpected critical error in {p_tag_worker} placement thread: {e_other}")
                custom_disconnect_exception = PlayerDisconnectedException(f"{p_tag_worker} had a critical error during placement: {e_other}")
                placement_status[p_tag_worker] = custom_disconnect_exception
                e_main_handler = custom_disconnect_exception

        for p_tag_for_thread in ["Player 1", "Player 2"]:
            thread = threading.Thread(target=placement_worker, args=(p_tag_for_thread,))
            placement_threads.append(thread)
            thread.start()
        for thread in placement_threads:
            thread.join() # Wait for both placement threads to complete

        # Check results of placement
        for p_tag_check in ["Player 1", "Player 2"]:
            status = placement_status.get(p_tag_check)
            if isinstance(status, PlayerDisconnectedException):
                raise status # Propagate the first PlayerDisconnectedException from placement
            if status != "success": # Should be an exception if not "success"
                 raise PlayerDisconnectedException(f"{p_tag_check} failed ship placement unexpectedly (status: {status}).")

        # If placement successful for both:
        send_msg_to_player("Player 1", "\nBoth players have placed ships. The battle begins!")
        send_msg_to_player("Player 2", "\nBoth players have placed ships. The battle begins!")

        # --- Main Game Loop (Turns) ---
        turn_count = 0
        while game_active:
            current_player_tag = "Player 1" if turn_count % 2 == 0 else "Player 2"
            opponent_player_tag = "Player 2" if turn_count % 2 == 0 else "Player 1"

            target_board = player_boards[opponent_player_tag] # The board being fired upon

            send_msg_to_player(current_player_tag, f"\n--- {current_player_tag}, it's your turn! ---")
            send_msg_to_player(current_player_tag, f"Your view of {opponent_player_tag}'s board:")
            send_board_to_player(current_player_tag, target_board, show_hidden=False) # Show display grid of opponent

            send_msg_to_player(opponent_player_tag, f"\nWaiting for {current_player_tag} to make a move...")

            send_msg_to_player(current_player_tag, "Enter coordinate to fire (e.g., A1) or type 'quit' to exit:")
            guess_input = recv_msg_from_player(current_player_tag)

            if guess_input.lower() == 'quit':
                game_active = False # Mark game as ended
                quitting_player = current_player_tag
                other_player = opponent_player_tag
                print(f"[GAME INFO] {quitting_player} has chosen to quit.")
                try:
                    send_msg_to_player(quitting_player, "You have quit the game. Game over.")
                except PlayerDisconnectedException: # Quitter already gone
                    print(f"[GAME INFO] {quitting_player} (who was quitting) already disconnected.")
                try:
                    send_msg_to_player(other_player, f"{quitting_player} has quit the game. Game over.")
                except PlayerDisconnectedException: # Opponent already gone
                    print(f"[GAME INFO] Opponent {other_player} was already disconnected when {quitting_player} quit.")
                break # Exit the 'while game_active:' loop immediately

            try:
                row, col = parse_coordinate(guess_input)
                result, sunk_ship = target_board.fire_at(row, col)

                msg_for_active_player = f"You fired at {guess_input.upper()}: "
                msg_for_opponent = f"{current_player_tag} fired at {guess_input.upper()}: "

                if result == 'hit':
                    if sunk_ship:
                        msg_for_active_player += f"HIT! You sank their {sunk_ship}!"
                        msg_for_opponent += f"HIT! Your {sunk_ship} has been SUNK!"
                    else:
                        msg_for_active_player += "HIT!"
                        msg_for_opponent += "HIT on one of your ships!"
                elif result == 'miss':
                    msg_for_active_player += "MISS."
                    msg_for_opponent += "MISS."
                elif result == 'already_shot':
                    msg_for_active_player += "ALREADY SHOT there. Your turn is wasted."
                    msg_for_opponent += "They fired at an already targeted location."

                send_msg_to_player(current_player_tag, msg_for_active_player)
                send_msg_to_player(opponent_player_tag, msg_for_opponent)

                # After a shot, show the opponent their updated board
                send_msg_to_player(opponent_player_tag, f"\n{opponent_player_tag}'s board after {current_player_tag}'s shot:")
                send_board_to_player(opponent_player_tag, target_board, show_hidden=True) # Show their own board (can see their ships)

                if target_board.all_ships_sunk():
                    game_active = False # Mark game as ended
                    final_win_msg = f"GAME OVER! {current_player_tag} WINS! All {opponent_player_tag}'s ships are sunk."
                    send_msg_to_player(current_player_tag, final_win_msg)
                    send_msg_to_player(current_player_tag, f"\nFinal state of {opponent_player_tag}'s board (what you saw):")
                    send_board_to_player(current_player_tag, target_board, show_hidden=False)

                    send_msg_to_player(opponent_player_tag, final_win_msg)
                    send_msg_to_player(opponent_player_tag, f"\nYour final board state (all ships shown):")
                    send_board_to_player(opponent_player_tag, target_board, show_hidden=True)
                    break # Exit the 'while game_active:' loop

                turn_count += 1 # Next player's turn
            except ValueError as e_parse_fire: # From parse_coordinate or fire_at (if it raises one)
                send_msg_to_player(current_player_tag, f"[!] Invalid move input ('{guess_input}'): {e_parse_fire}. Please try again this turn.")
                # Player does not lose turn for bad input formatting.

    except PlayerDisconnectedException as e_disconnect_main:
        e_main_handler = e_disconnect_main # Store the exception for finally block
        game_active = False
        disconnected_msg_detail = str(e_disconnect_main)
        print(f"[GAME INFO] A player disconnected: {disconnected_msg_detail}. Game ending.")

        # Determine which player is remaining to notify
        # The disconnected_msg_detail usually starts with "Player X disconnected..."
        remaining_player = None
        if "Player 1" in disconnected_msg_detail: remaining_player = "Player 2"
        elif "Player 2" in disconnected_msg_detail: remaining_player = "Player 1"

        if remaining_player:
            try:
                # Use a more generic message if one player disconnected during the other's action
                notification_msg = f"The game has ended because your opponent ({disconnected_msg_detail.split(' (')[0]}) disconnected or quit."
                send_msg_to_player(remaining_player, notification_msg)
            except PlayerDisconnectedException:
                print(f"[GAME INFO] {remaining_player} also disconnected or unreachable while notifying of opponent's disconnect.")
        else:
             print(f"[GAME INFO] Could not reliably determine remaining player to notify from message: {disconnected_msg_detail}")

    except Exception as e_critical:
        e_critical_main = e_critical # Store for finally
        game_active = False
        print(f"[CRITICAL ERROR in run_multiplayer_game] Type: {type(e_critical)}, Error: {e_critical}")
        # Attempt to notify both players if a very unexpected error occurs
        critical_error_msg = "A critical server error occurred in the game. The game has to end."
        for p_tag_crit_notify in ["Player 1", "Player 2"]:
            try: send_msg_to_player(p_tag_crit_notify, critical_error_msg)
            except: pass # Best effort notification

    finally:
        print(f"[INFO] run_multiplayer_game is concluding for players associated with this game instance.")

        # Determine the final message based on how the game ended
        final_goodbye_msg = "The game session has ended. Goodbye." # Default

        if e_critical_main: # A critical, unexpected error occurred
            final_goodbye_msg = "The game session has ended due to a server error. Goodbye."
        elif e_main_handler: # A player disconnected (PlayerDisconnectedException was caught)
            final_goodbye_msg = f"The game session has ended due to a disconnection ({str(e_main_handler).split(' (')[0]}). Goodbye."
        elif not game_active : # Game ended by win/loss or explicit "quit" command
            # Specific messages for win/loss/quit were already sent.
            # So, a simple "Goodbye" or no additional message might be best.
            # If we set final_goodbye_msg = None, no generic message is sent.
            final_goodbye_msg = None # Suppress generic goodbye if specific end already sent.


        for p_tag_final_cleanup in ["Player 1", "Player 2"]:
            wfile_cleanup = player_files[p_tag_final_cleanup]["w"]
            rfile_cleanup = player_files[p_tag_final_cleanup]["r"]

            if wfile_cleanup and not wfile_cleanup.closed:
                try:
                    if final_goodbye_msg: # Only send if a message is determined
                        wfile_cleanup.write(final_goodbye_msg + '\n')
                        wfile_cleanup.flush()
                except (socket.error, BrokenPipeError, ConnectionResetError):
                    pass # Ignore if connection is already broken
                finally: # Always attempt to close
                    try: wfile_cleanup.close()
                    except: pass

            if rfile_cleanup and not rfile_cleanup.closed:
                try: rfile_cleanup.close()
                except: pass
        print("[INFO] Game resources cleaned up for this instance.")


def run_single_player_game_locally(): # For local testing, unchanged
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