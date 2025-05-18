"""
battleship.py

Contains core data structures and logic for Battleship, including:
 - Board class for storing ship positions, hits, misses
 - Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)
 - A test harness run_single_player_game() to demonstrate the logic in a local, single-player mode
 - run_multiplayer_game() for networked play, now with disconnection handling and timeout detection.
"""

import random
import threading
import socket  # For socket.error and network operations
import time    # For timeout handling


BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2)
]

# Timeout configuration
INACTIVITY_TIMEOUT = 30  # Seconds before a player's turn is skipped due to inactivity


class PlayerDisconnectedException(Exception):
    """Custom exception for handling player disconnections during the game."""
    pass


class PlayerTimeoutException(Exception):
    """Custom exception for handling player timeouts during the game."""
    pass


class Board:
    """
    Represents a single Battleship board with hidden ships.
    """

    def __init__(self, size=BOARD_SIZE):
        self.size = size
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.placed_ships = []  # List of dicts: {'name': str, 'positions': set_of_tuples}

    def place_ships_randomly(self, ships=SHIPS):
        for ship_name, ship_size in ships:
            placed = False
            while not placed:
                orientation = random.randint(0, 1)  # 0: H, 1: V
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

    def print_display_grid(self, show_hidden_board=False):  # For local test
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

    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):  # Check if parsed row/col are in board range
        raise ValueError(f"Coordinate {row_letter}{int(col_digits)} is out of board range (A1-{chr(ord('A') + BOARD_SIZE - 1)}{BOARD_SIZE}).")
    return (row, col)


def run_multiplayer_game(username1, rfile1, wfile1, username2, rfile2, wfile2, spectators, mark_player_disconnected, active_games):
    player_files = {
        username1: {"r": rfile1, "w": wfile1},
        username2: {"r": rfile2, "w": wfile2}
    }

    player_boards = {username1: Board(BOARD_SIZE), username2: Board(BOARD_SIZE)}

    # Track the last activity time for each player
    player_last_activity = {
        username1: time.time(),
        username2: time.time()
    }

    # --- Network Helper Functions (defined inside to close over player_files) ---
    def send_msg_to_player(player_tag, message):
        wfile = player_files[player_tag]["w"]
        try:
            wfile.write(message + '\n')
            wfile.flush()
        except (socket.error, BrokenPipeError, ConnectionResetError) as e:
            print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: Detected disconnect on send for {player_tag}")
            raise PlayerDisconnectedException(f"{player_tag} disconnected (send error: {e})")

    def recv_msg_from_player(player_tag, timeout=INACTIVITY_TIMEOUT):
        rfile = player_files[player_tag]["r"]
        result = {"data": None, "exception": None}

        def read_input():
            try:
                line = rfile.readline()
                if not line:
                    print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: Detected disconnect on recv for {player_tag}")
                    result["exception"] = PlayerDisconnectedException(f"{player_tag} disconnected (EOF on read)")
                    return
                result["data"] = line.strip()
                player_last_activity[player_tag] = time.time()
            except Exception as e:
                result["exception"] = e

        thread = threading.Thread(target=read_input)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            raise PlayerTimeoutException(f"{player_tag} timed out")
        if result["exception"]:
            raise result["exception"]
        return result["data"]

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
            while True:  # Loop for current ship until placed
                send_msg_to_player(player_tag, f"\n{player_tag}, your current board setup:")
                send_board_to_player(player_tag, board, show_hidden=True)
                send_msg_to_player(player_tag, f"Place your {ship_name} (size {ship_size}).")
                send_msg_to_player(player_tag, "Enter start coordinate (e.g., A1) or type 'quit' to exit:")

                try:
                    coord_str = recv_msg_from_player(player_tag, INACTIVITY_TIMEOUT * 2)  # Double timeout for ship placement
                    if coord_str.lower() == 'quit':
                        raise PlayerDisconnectedException(f"{player_tag} quit during ship placement.")

                    send_msg_to_player(player_tag, "Enter orientation ('H' or 'V') or type 'quit' to exit:")
                    orient_str = recv_msg_from_player(player_tag, INACTIVITY_TIMEOUT * 2).upper()  # Double timeout for ship placement
                    if orient_str.lower() == 'quit':
                        raise PlayerDisconnectedException(f"{player_tag} quit during ship placement.")

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
                        break  # Ship placed, exit inner while loop
                    else:
                        send_msg_to_player(player_tag, f"[!] Cannot place {ship_name} at {coord_str}{orient_str}. It overlaps existing ships or is out of bounds. Try again.")
                except PlayerTimeoutException:
                    # For ship placement, we'll be more lenient - just notify and let them try again
                    send_msg_to_player(player_tag, f"[!] You were inactive for too long. Please respond within {INACTIVITY_TIMEOUT * 2} seconds.")
                    # We don't break the loop here, giving them another chance
                except ValueError as e:  # From parse_coordinate
                    send_msg_to_player(player_tag, f"[!] Invalid input for {ship_name} placement: {e}. Try again.")

        send_msg_to_player(player_tag, f"\n{player_tag}, all your ships have been placed:")
        send_board_to_player(player_tag, board, show_hidden=True)
        send_msg_to_player(player_tag, "Waiting for the other player to finish placing ships...")


    def broadcast_to_spectators(spectators, message):
        for spec in spectators[:]:  # Use a copy of the list in case it changes during iteration
            wfile = spec.get("w")
            if wfile:
                send_msg_to_spectator(wfile, message)

    def send_msg_to_spectator(spectator_wfile, message):
        try:
            spectator_wfile.write(message + '\n')
            spectator_wfile.flush()
        except (socket.error, BrokenPipeError, ConnectionResetError) as e:
            print(f"[ERROR] Spectator disconnected (send error: {e})")
            # Handle spectator disconnection if needed (cleanup)
        pass

    def send_both_boards_to_spectators(spectators):
        # Get both player boards
        board_p1 = player_boards[username1]
        board_p2 = player_boards[username2]

        # Prepare the board display strings
        p1_grid = board_p1.display_grid
        p2_grid = board_p2.display_grid

        # Format the boards side-by-side
        board_message = "PLAYER 1                  PLAYER 2\n"
        board_message += "-" * (len(board_message) - 1) + "\n" # create a separator line of the right length
        for r_idx in range(board_p1.size):
            # Row label for P1 (Player 1) and P2 (Player 2)
            row_label = chr(ord('A') + r_idx)
            
            # Build row for Player 1's board (left)
            row_p1 = " ".join(p1_grid[r_idx][c_idx] for c_idx in range(board_p1.size))
            
            # Build row for Player 2's board (right)
            row_p2 = " ".join(p2_grid[r_idx][c_idx] for c_idx in range(board_p2.size))

            # Combine them into one row
            board_message += f"{row_label:2} {row_p1}    |    {row_label:2} {row_p2}\n"
        for spectator in spectators:
            send_msg_to_spectator(spectator["w"], board_message)


    # --- Main Game Logic ---
    game_active = True  # Flag to control main game loop
    # Define e_main_handler and e_critical_main outside try for finally block access check
    e_main_handler = None
    e_critical_main = None

    # Reset player activity times at game start
    for player in player_last_activity:
        player_last_activity[player] = time.time()

    try:
        # --- Threaded Ship Placement ---
        placement_threads = []
        placement_status = {}  # Stores "success" or the exception object

        def placement_worker(p_tag_worker):
            nonlocal e_main_handler  # To indicate if an error happened here
            try:
                place_ships_for_player(p_tag_worker)
                placement_status[p_tag_worker] = "success"
            except PlayerDisconnectedException as e_disconnect:
                print(f"[DEBUG] placement_worker: PlayerDisconnectedException caught in placement_worker for {p_tag_worker}: {e_disconnect}")
                placement_status[p_tag_worker] = e_disconnect
                e_main_handler = e_disconnect  # Store first disconnect during placement
            except PlayerTimeoutException as e_timeout:
                print(f"[DEBUG] placement_worker: PlayerTimeoutException caught in placement_worker for {p_tag_worker}: {e_timeout}")
                # If a player times out during placement, we'll treat it as a disconnect
                custom_disconnect_exception = PlayerDisconnectedException(
                    f"{p_tag_worker} timed out during ship placement and forfeited")
                placement_status[p_tag_worker] = custom_disconnect_exception
                e_main_handler = custom_disconnect_exception
            except Exception as e_other:
                print(f"[ERROR] placement_worker: Unexpected critical error in {p_tag_worker} placement thread: {e_other}")
                custom_disconnect_exception = PlayerDisconnectedException(
                    f"{p_tag_worker} had a critical error during placement: {e_other}")
                placement_status[p_tag_worker] = custom_disconnect_exception
                e_main_handler = custom_disconnect_exception

        for p_tag_for_thread in [username1, username2]:
            thread = threading.Thread(target=placement_worker, args=(p_tag_for_thread,))
            placement_threads.append(thread)
            thread.start()
        for thread in placement_threads:
            thread.join()  # Wait for both placement threads to complete

        # Check results of placement
        for p_tag_check in [username1, username2]:
            status = placement_status.get(p_tag_check)
            if isinstance(status, PlayerDisconnectedException):
                raise status  # Propagate the first PlayerDisconnectedException from placement
            if status != "success":  # Should be an exception if not "success"
                raise PlayerDisconnectedException(f"{p_tag_check} failed ship placement unexpectedly (status: {status}).")

        # If placement successful for both:
        send_msg_to_player(username1, "\nBoth players have placed ships. The battle begins!")
        send_msg_to_player(username2, "\nBoth players have placed ships. The battle begins!")
        send_both_boards_to_spectators(spectators)
        broadcast_to_spectators(spectators, "Game has started!")

        # --- Main Game Loop (Turns) ---
        turn_count = 0
        timeout_count = {username1: 0, username2: 0}  # Track consecutive timeouts
        MAX_TIMEOUTS = 2  # Maximum number of consecutive timeouts before forfeit

        while game_active:
            try:
                print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: Entered main game loop try block for turn {turn_count}")
                current_player_tag = username1 if turn_count % 2 == 0 else username2
                opponent_player_tag = username2 if turn_count % 2 == 0 else username1
                target_board = player_boards[opponent_player_tag]

                # --- Ping both players to detect disconnects early ---
                try:
                    send_msg_to_player(current_player_tag, "[PING]")  # Detect if current player disconnected
                except PlayerDisconnectedException as e:
                    print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: Detected disconnect on ping for {current_player_tag}")
                    raise

                try:
                    send_msg_to_player(opponent_player_tag, "[PING]")  # Detect if waiting player disconnected
                except PlayerDisconnectedException as e:
                    print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: Detected disconnect on ping for {opponent_player_tag}")
                    raise

                # --- All network and game logic for the turn is inside this try! ---
                send_msg_to_player(current_player_tag, f"\n--- {current_player_tag}, it's your turn! ---")
                send_msg_to_player(current_player_tag, f"Your view of {opponent_player_tag}'s board:")
                send_board_to_player(current_player_tag, target_board, show_hidden=False)
                send_msg_to_player(current_player_tag, f"You have {INACTIVITY_TIMEOUT} seconds to make your move.")
                send_msg_to_player(opponent_player_tag, f"\nWaiting for {current_player_tag} to make a move...")

                send_msg_to_player(current_player_tag, "Enter coordinate to fire (e.g., A1) or type 'quit' to exit:")
                guess_input = recv_msg_from_player(current_player_tag)

                timeout_count[current_player_tag] = 0

                if guess_input.lower() == 'quit':
                    game_active = False
                    quitting_player = current_player_tag
                    other_player = opponent_player_tag
                    print(f"[GAME INFO] {quitting_player} has chosen to quit.")

                    try:
                        send_msg_to_player(quitting_player, f"You have chosen to quit the game. Game over.")
                    except PlayerDisconnectedException:
                        print(f"[GAME INFO] {quitting_player} (who was quitting) already disconnected.")

                    try:
                        send_msg_to_player(other_player, f"\n{quitting_player} has chosen to quit the game. Game over.")
                    except PlayerDisconnectedException:
                        print(f"[GAME INFO] Opponent {other_player} was already disconnected when {quitting_player} quit.")

                    break

                row, col = parse_coordinate(guess_input)
                result, sunk_ship = target_board.fire_at(row, col)

                msg_for_active_player = f"You fired at {guess_input.upper()}: "
                msg_for_opponent = f"{current_player_tag} fired at {guess_input.upper()}: "

                if result == 'hit':
                    send_both_boards_to_spectators(spectators)
                    if sunk_ship:
                        msg_for_active_player += f"HIT! You sank their {sunk_ship}!"
                        msg_for_opponent += f"HIT! Your {sunk_ship} has been SUNK!"
                        broadcast_to_spectators(spectators, f"{current_player_tag} sunked {opponent_player_tag}'s {sunk_ship}!")
                    else:
                        msg_for_active_player += "HIT!"
                        msg_for_opponent += "HIT on one of your ships!"
                        broadcast_to_spectators(spectators, f"{current_player_tag} hits {opponent_player_tag}'s ship!")
                elif result == 'miss':
                    send_both_boards_to_spectators(spectators)
                    broadcast_to_spectators(spectators, f"{current_player_tag} fired at {opponent_player_tag} and missed.")
                    msg_for_active_player += "MISS."
                    msg_for_opponent += "MISS."
                elif result == 'already_shot':
                    send_both_boards_to_spectators(spectators)
                    broadcast_to_spectators(spectators, f"{current_player_tag} fired at an already targeted location.")
                    msg_for_active_player += "ALREADY SHOT there. Your turn is wasted."
                    msg_for_opponent += "They fired at an already targeted location."

                send_msg_to_player(current_player_tag, msg_for_active_player)
                send_msg_to_player(opponent_player_tag, msg_for_opponent)

                send_msg_to_player(opponent_player_tag, f"\n{opponent_player_tag}'s board after {current_player_tag}'s shot:")
                send_board_to_player(opponent_player_tag, target_board, show_hidden=True)

                if target_board.all_ships_sunk():
                    game_active = False
                    final_win_msg = f"GAME OVER! {current_player_tag} WINS! All {opponent_player_tag}'s ships are sunk."
                    send_msg_to_player(current_player_tag, final_win_msg)
                    send_msg_to_player(current_player_tag, f"\nFinal state of {opponent_player_tag}'s board (what you saw):")
                    send_board_to_player(current_player_tag, target_board, show_hidden=False)

                    send_msg_to_player(opponent_player_tag, final_win_msg)
                    send_msg_to_player(opponent_player_tag, f"\nYour final board state (all ships shown):")
                    send_board_to_player(opponent_player_tag, target_board, show_hidden=True)
                    break

                turn_count += 1

            except PlayerTimeoutException:
                print("[DEBUG] BATTLESHIP.PY: run_multiplayer_game: caught PlayerTimeoutException in main game loop")
                timeout_count[current_player_tag] += 1
                timeout_msg = f"{current_player_tag} did not respond within {INACTIVITY_TIMEOUT} seconds. "

                if timeout_count[current_player_tag] >= MAX_TIMEOUTS:
                    forfeit_msg = f"{current_player_tag} has forfeited the game due to {MAX_TIMEOUTS} consecutive timeouts."
                    print(f"[GAME INFO] {forfeit_msg}")

                    try:
                        send_msg_to_player(current_player_tag,
                                          f"You have forfeited the game due to {MAX_TIMEOUTS} consecutive timeouts. Game over.")
                    except PlayerDisconnectedException:
                        pass

                    try:
                        send_msg_to_player(opponent_player_tag,
                                          f"\n{forfeit_msg} You win!")
                    except PlayerDisconnectedException:
                        pass

                    game_active = False
                    break
                else:
                    timeout_msg += f"Turn skipped ({timeout_count[current_player_tag]}/{MAX_TIMEOUTS} strikes)."
                    print(f"[GAME INFO] {timeout_msg}")

                    try:
                        send_msg_to_player(current_player_tag,
                                          f"You did not respond in time. Your turn has been skipped. "
                                          f"Warning: {timeout_count[current_player_tag]}/{MAX_TIMEOUTS} timeouts.")
                    except PlayerDisconnectedException:
                        raise PlayerDisconnectedException(f"{current_player_tag} disconnected after timeout")

                    try:
                        send_msg_to_player(opponent_player_tag,
                                          f"\n{current_player_tag} did not respond in time. Their turn has been skipped. "
                                          f"Warning: They have {timeout_count[current_player_tag]}/{MAX_TIMEOUTS} timeouts.")
                    except PlayerDisconnectedException:
                        raise PlayerDisconnectedException(f"{opponent_player_tag} disconnected during opponent timeout handling")

            except ValueError as e_parse_fire:
                print("[DEBUG] BATTLESHIP.PY: run_multiplayer_game: caught ValueError in main game loop")
                send_msg_to_player(current_player_tag, f"[!] Invalid move input ('{guess_input}'): {e_parse_fire}. Please try again this turn.")
                continue

            except (ConnectionResetError, BrokenPipeError, OSError, PlayerDisconnectedException) as e_disconnect_main:
                print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: caught PlayerDisconnectedException in main game loop: {e_disconnect_main}")
                disconnected_msg_detail = str(e_disconnect_main)
                disconnected_player = None
                remaining_player = None

                if username1 in disconnected_msg_detail:
                    disconnected_player = username1
                    remaining_player = username2
                elif username2 in disconnected_msg_detail:
                    disconnected_player = username2
                    remaining_player = username1
                else:
                    # Fallback: use current_player_tag
                    disconnected_player = current_player_tag
                    remaining_player = opponent_player_tag

                if disconnected_player:
                    print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: Marking {disconnected_player} as disconnected")
                    mark_player_disconnected(disconnected_player, active_games)

                if remaining_player:
                    try:
                        notification_msg = (
                            f"\nPlayer '{disconnected_player}' disconnected. Waiting up to 20 seconds for reconnection..."
                        )
                        send_msg_to_player(remaining_player, notification_msg)
                        broadcast_to_spectators(spectators, notification_msg)
                    except PlayerDisconnectedException:
                        pass

                RECONNECT_TIMEOUT = 30
                reconnect_deadline = time.time() + RECONNECT_TIMEOUT

                reconnected = False
                while time.time() < reconnect_deadline:
                    if disconnected_player in active_games and not active_games[disconnected_player].get("disconnected", True):
                        try:
                            print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: {disconnected_player} has reconnected, resuming game")
                            if remaining_player:
                                send_msg_to_player(remaining_player, f"Player '{disconnected_player}' has reconnected! Resuming game.")
                                broadcast_to_spectators(spectators, f"Player '{disconnected_player}' has reconnected! Game resuming.")
                        except Exception:
                            pass
                        player_files[disconnected_player]["r"] = active_games[disconnected_player]["rfile"]
                        player_files[disconnected_player]["w"] = active_games[disconnected_player]["wfile"]
                        print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: Updated file handles for {disconnected_player}")

                        send_msg_to_player(disconnected_player, "You have reconnected! Here is your current board:")
                        send_board_to_player(disconnected_player, player_boards[disconnected_player], show_hidden=True)
                        reconnected = True
                        break
                    else:
                        if disconnected_player in active_games:
                            print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: Waiting for {disconnected_player} to reconnect. disconnected={active_games[disconnected_player].get('disconnected', True)}")
                        else:
                            print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: Waiting for {disconnected_player} to reconnect. Not in active_games.")
                    time.sleep(1)

                if not reconnected:
                    if remaining_player:
                        try:
                            send_msg_to_player(remaining_player, "Opponent failed to reconnect in time. You win by forfeit.")
                            broadcast_to_spectators(spectators, "Opponent failed to reconnect in time. Game over.")
                        except Exception:
                            pass
                    e_main_handler = e_disconnect_main
                    game_active = False
                else:
                    print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: Reconnection successful, continuing game loop")
                    continue
    except PlayerDisconnectedException as e_disconnect_main:
        print(f"[DEBUG] BATTLESHIP.PY: run_multiplayer_game: Last resort disconnect handling")
        print(f"[INFO] Player disconnected outside main loop: {e_disconnect_main}")
        e_main_handler = e_disconnect_main
        game_active = False
    except Exception as e_critical:
        e_critical_main = e_critical  # Store for finally
        game_active = False
        print(f"[CRITICAL ERROR in run_multiplayer_game] Type: {type(e_critical)}, Error: {e_critical}")
        # Attempt to notify both players if a very unexpected error occurs
        critical_error_msg = "A critical server error occurred in the game. The game has to end."
        for p_tag_crit_notify in [username1, username2]:
            try: send_msg_to_player(p_tag_crit_notify, critical_error_msg)
            except: pass  # Best effort notification

    finally:
        print(f"[INFO] run_multiplayer_game is concluding for players associated with this game instance.")

        # Determine the final message based on how the game ended
        final_goodbye_msg = "The game session has ended. Goodbye."  # Default

        if e_critical_main:  # A critical, unexpected error occurred
            final_goodbye_msg = "The game session has ended due to a server error. Goodbye."
        elif e_main_handler:  # A player disconnected (PlayerDisconnectedException was caught)
            final_goodbye_msg = f"The game session has ended due to a disconnection. Goodbye."
        elif not game_active:  # Game ended by win/loss or explicit "quit" command
            # Fix: Include a goodbye message even if the game ended normally
            final_goodbye_msg = "The game has ended. Thank you for playing Battleship!"

        # Send the final goodbye message to both players
        for p_tag_final_cleanup in [username1, username2]:
            wfile_cleanup = player_files[p_tag_final_cleanup]["w"]
            rfile_cleanup = player_files[p_tag_final_cleanup]["r"]

            if wfile_cleanup and not wfile_cleanup.closed:
                try:
                    if final_goodbye_msg:  # Only send if a message is determined
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
        # print("[INFO] If you would like, reconnect to the server to keep playing!")


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