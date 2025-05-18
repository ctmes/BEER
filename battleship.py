"""
battleship.py

Contains core data structures and logic for Battleship, including:
 - Board class for storing ship positions, hits, misses
 - Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)
 - A test harness run_single_player_game() to demonstrate the logic in a local, single-player mode
 - run_multiplayer_game() for networked play, now with disconnection handling and timeout detection,
   and integration with server-side input handling for commands/chat.
"""

import random
import threading
import socket
import time
import queue


BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2)
]

# TIER 2.3 TIMEOUT HANDLING - Defines the timeout period for player inactivity.
INACTIVITY_TIMEOUT = 30


class PlayerDisconnectedException(Exception):
    """
    TIER 1.5 NO DISCONNECTION HANDLING / TIER 2.4 DISCONNECTION HANDLING -
    Custom exception for handling player disconnections during the game.
    """
    pass


class PlayerTimeoutException(Exception):
    """
    TIER 2.3 TIMEOUT HANDLING - Custom exception for handling player timeouts during the game.
    """
    pass


class Board:
    """
    Represents a single Battleship board with hidden ships, and a display grid
    to show hit/miss information.
    """

    def __init__(self, size=BOARD_SIZE):
        """
        Initializes a new Battleship board.

        Args:
            size (int): The size of the square board grid.
        """
        self.size = size
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.placed_ships = []

    def place_ships_randomly(self, ships=SHIPS):
        """
        TIER 1.3 BASIC GAME FLOW - Places ships on the board randomly.
        """
        for ship_name, ship_size in ships:
            placed = False
            while not placed:
                orientation = random.randint(0, 1)
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({'name': ship_name, 'positions': occupied_positions.copy()})
                    placed = True

    def place_ships_manually(self, ships=SHIPS):
        """
        TIER 1.3 BASIC GAME FLOW - Allows manual placement of ships via console input (for local testing).
        """
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
                    print(f"  [!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). It overlaps existing ships or is out of bounds. Try again.")

    def can_place_ship(self, row, col, ship_size, orientation):
        """
        TIER 1.3 BASIC GAME FLOW - Checks if a ship can be placed at the given coordinates with the given orientation.

        Args:
            row (int): The starting row.
            col (int): The starting column.
            ship_size (int): The size of the ship.
            orientation (int): 0 for horizontal, 1 for vertical.

        Returns:
            bool: True if the ship can be placed, False otherwise.
        """
        if orientation == 0:
            if not (0 <= row < self.size and 0 <= col < self.size and col + ship_size <= self.size): return False
            for c_offset in range(ship_size):
                if self.hidden_grid[row][col + c_offset] != '.': return False
        else:
            if not (0 <= row < self.size and 0 <= col < self.size and row + ship_size <= self.size): return False
            for r_offset in range(ship_size):
                if self.hidden_grid[row + r_offset][col] != '.': return False
        return True

    def do_place_ship(self, row, col, ship_size, orientation):
        """
        TIER 1.3 BASIC GAME FLOW - Places the ship on the hidden grid. Assumes can_place_ship has been called and returned True.

        Args:
            row (int): The starting row.
            col (int): The starting column.
            ship_size (int): The size of the ship.
            orientation (int): 0 for horizontal, 1 for vertical.

        Returns:
            set: A set of (row, col) tuples occupied by the placed ship.
        """
        occupied = set()
        if orientation == 0:
            for c_offset in range(ship_size):
                self.hidden_grid[row][col + c_offset] = 'S'
                occupied.add((row, col + c_offset))
        else:
            for r_offset in range(ship_size):
                self.hidden_grid[row + r_offset][col] = 'S'
                occupied.add((row + r_offset, col))
        return occupied

    def fire_at(self, row, col):
        """
        TIER 1.3 BASIC GAME FLOW, TIER 2.1 EXTENDED INPUT VALIDATION -
        Processes a shot at the given coordinates, reporting the outcome and handling already shot locations.

        Args:
            row (int): The target row.
            col (int): The target column.

        Returns:
            tuple: A tuple containing the result ('hit', 'miss', 'already_shot', 'error')
                   and the name of the sunk ship if applicable (str or None).
        """
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
        """
        TIER 1.3 BASIC GAME FLOW - Marks a ship segment as hit and checks if the entire ship is sunk.

        Args:
            row (int): The row of the hit segment.
            col (int): The column of the hit segment.

        Returns:
            str or None: The name of the sunk ship if one was sunk, otherwise None.
        """
        for ship in self.placed_ships:
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if not ship['positions']:
                    return ship['name']
                break
        return None

    def all_ships_sunk(self):
        """
        TIER 1.3 BASIC GAME FLOW - Checks if all ships on the board have been sunk, indicating game end.

        Returns:
            bool: True if all ships are sunk, False otherwise.
        """
        if not self.placed_ships: return False
        return all(not ship['positions'] for ship in self.placed_ships)

    def print_display_grid(self, show_hidden_board=False):
        """
        TIER 1.3 BASIC GAME FLOW - Prints the display grid (or hidden grid for debugging) to the console for local testing.

        Args:
            show_hidden_board (bool): If True, prints the hidden grid.
        """
        grid_to_print = self.hidden_grid if show_hidden_board else self.display_grid
        print("  " + "".join(str(i + 1).rjust(2) for i in range(self.size)))
        for r_idx in range(self.size):
            row_label = chr(ord('A') + r_idx)
            row_str = " ".join(grid_to_print[r_idx][c_idx] for c_idx in range(self.size))
            print(f"{row_label:2} {row_str}")


def parse_coordinate(coord_str):
    """
    TIER 1.3 BASIC GAME FLOW, TIER 2.1 EXTENDED INPUT VALIDATION -
    Parses a coordinate string (e.g., 'A1', 'J10') into a (row, col) tuple and validates its format and range.

    Args:
        coord_str (str): The coordinate string to parse.

    Returns:
        tuple: A tuple (row, col) representing the grid coordinates.

    Raises:
        ValueError: If the coordinate string is in an invalid format or out of bounds.
    """
    coord_str = coord_str.strip().upper()
    if not (2 <= len(coord_str) <= 3): raise ValueError(f"Invalid coordinate format '{coord_str}'. Expected e.g., A1 or J10.")
    row_letter = coord_str[0]
    col_digits = coord_str[1:]
    if not ('A' <= row_letter < chr(ord('A') + BOARD_SIZE)):
        raise ValueError(f"Invalid row letter '{row_letter}'. Must be A-{chr(ord('A') + BOARD_SIZE - 1)}.")
    if not col_digits.isdigit(): raise ValueError(f"Column part '{col_digits}' must be a number.")

    col = int(col_digits) - 1
    row = ord(row_letter) - ord('A')

    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
        raise ValueError(f"Coordinate {row_letter}{int(col_digits)} is out of board range (A1-{chr(ord('A') + BOARD_SIZE - 1)}{BOARD_SIZE}).")
    return (row, col)


def run_multiplayer_game(player1_data, player2_data, p1_input_queue, p2_input_queue, send_message_func, broadcast_board_func):
    """
    TIER 1.3 BASIC GAME FLOW, TIER 1.5 NO DISCONNECTION HANDLING / TIER 2.4 DISCONNECTION HANDLING,
    TIER 2.3 TIMEOUT HANDLING, TIER 3.1 MULTIPLE CONCURRENT CONNECTIONS, TIER 3.2 SPECTATOR EXPERIENCE -
    Runs a multiplayer game instance. Receives player input via queues,
    handles ship placement, turn-based firing, hit/miss/sunk reporting,
    game end conditions, disconnections, timeouts, and broadcasts board state to spectators.

    Args:
        player1_data (dict): Data for Player 1 (including id).
        player2_data (dict): Data for Player 2 (including id).
        p1_input_queue (queue.Queue): Queue for input from Player 1.
        p2_input_queue (queue.Queue): Queue for input from Player 2.
        send_message_func (callable): Function to send a message to a specific client (player_id, message).
        broadcast_board_func (callable): Function to send board states to all clients (player1_board, player2_board).
    """
    player_tags = {player1_data['id']: "Player 1", player2_data['id']: "Player 2"}
    player_ids = {"Player 1": player1_data['id'], "Player 2": player2_data['id']}
    player_boards = {player1_data['id']: Board(BOARD_SIZE), player2_data['id']: Board(BOARD_SIZE)}
    player_queues = {player1_data['id']: p1_input_queue, player2_data['id']: p2_input_queue}

    def send_msg_to_player(player_id, message):
        """Sends a message to a specific player using the provided server function."""
        send_message_func(player_id, message)

    def send_board_to_player(player_id, board_to_send, show_hidden=False):
         """
         TIER 1.4 SIMPLE CLIENT/SERVER MESSAGE EXCHANGE, TIER 3.2 SPECTATOR EXPERIENCE -
         Formats and sends a board state to a specific player using the GRID protocol.
         """
         try:
            grid_to_print = board_to_send.hidden_grid if show_hidden else board_to_send.display_grid
            message_lines = ["GRID"]
            header = "  " + "".join(str(i + 1).rjust(2) for i in range(board_to_send.size))
            message_lines.append(header)
            for r_idx in range(BOARD_SIZE):
                row_label = chr(ord('A') + r_idx)
                row_str = " ".join(grid_to_print[r_idx][c_idx] for c_idx in range(board_to_send.size))
                message_lines.append(f"{row_label:2} {row_str}")
            message_lines.append("")

            send_message_func(player_id, "\n".join(message_lines))

         except Exception as e:
             print(f"[ERROR] Failed to send board to {player_id}: {e}")
             pass

    def place_ships_for_player(player_id):
        """
        TIER 1.3 BASIC GAME FLOW, TIER 2.1 EXTENDED INPUT VALIDATION, TIER 2.3 TIMEOUT HANDLING,
        TIER 1.5 NO DISCONNECTION HANDLING / TIER 2.4 DISCONNECTION HANDLING -
        Manages the manual ship placement process for a single player, handling input validation, timeouts, and disconnects.
        """
        board = player_boards[player_id]
        player_tag = player_tags[player_id]
        player_queue = player_queues[player_id]
        print(f"[DEBUG:run_multiplayer_game] Starting ship placement for {player_tag} ({player_id}).")

        send_msg_to_player(player_id, f"[SYSTEM] Welcome, {player_tag}. It's time to place your ships.")
        for ship_name, ship_size in SHIPS:
            while True:
                send_msg_to_player(player_id, f"\n[SYSTEM] {player_tag}, your current board setup:")
                send_board_to_player(player_id, board, show_hidden=True)
                send_msg_to_player(player_id, f"[SYSTEM] Place your {ship_name} (size {ship_size}).")
                send_msg_to_player(player_id, "[SYSTEM] Enter start coordinate (e.g., A1):")

                try:
                    print(f"[DEBUG:run_multiplayer_game] {player_tag} ({player_id}) is waiting for placement coordinate.")
                    coord_str = player_queue.get(timeout=INACTIVITY_TIMEOUT * 2)
                    print(f"[DEBUG:run_multiplayer_game] {player_tag} ({player_id}) received placement coordinate: '{coord_str}'")

                    if coord_str.lower() == 'quit':
                        raise PlayerDisconnectedException(f"{player_id} quit during ship placement.")

                    send_msg_to_player(player_id, "[SYSTEM] Enter orientation ('H' or 'V'):")
                    print(f"[DEBUG:run_multiplayer_game] {player_tag} ({player_id}) is waiting for placement orientation.")
                    orient_str = player_queue.get(timeout=INACTIVITY_TIMEOUT * 2).upper()
                    print(f"[DEBUG:run_multiplayer_game] {player_tag} ({player_id}) received placement orientation: '{orient_str}'")

                    if orient_str.lower() == 'quit':
                         raise PlayerDisconnectedException(f"{player_id} quit during ship placement.")


                    row, col = parse_coordinate(coord_str)
                    orientation_val = -1
                    if orient_str == 'H': orientation_val = 0
                    elif orient_str == 'V': orientation_val = 1

                    if orientation_val == -1:
                        send_msg_to_player(player_id, "[!] Invalid orientation. Use 'H' for horizontal or 'V' for vertical. Try again.")
                        continue
                    if board.can_place_ship(row, col, ship_size, orientation_val):
                        positions = board.do_place_ship(row, col, ship_size, orientation_val)
                        board.placed_ships.append({'name': ship_name, 'positions': positions.copy()})
                        send_msg_to_player(player_id, f"[SYSTEM] {ship_name} placed successfully at {coord_str}{orient_str}.")
                        break
                    else:
                        send_msg_to_player(player_id, f"[!] Cannot place {ship_name} at {coord_str}{orient_str}. It overlaps existing ships or is out of bounds. Try again.")
                except queue.Empty:
                    print(f"[DEBUG:run_multiplayer_game] {player_tag} ({player_id}) placement input timed out.")
                    raise PlayerTimeoutException(f"{player_id} timed out during ship placement after {INACTIVITY_TIMEOUT * 2} seconds")
                except ValueError as e:
                    print(f"[DEBUG:run_multiplayer_game] {player_tag} ({player_id}) invalid placement input: {e}")
                    send_msg_to_player(player_id, f"[!] Invalid input for {ship_name} placement: {e}. Try again.")
                except PlayerDisconnectedException:
                    raise
                except Exception as e:
                     print(f"[ERROR:run_multiplayer_game] Unexpected error during placement for {player_id}: {type(e).__name__}: {e}")
                     send_msg_to_player(player_id, f"[SYSTEM] An unexpected error occurred during placement. Please try again.")


        send_msg_to_player(player_id, f"\n[SYSTEM] {player_tag}, all your ships have been placed:")
        send_board_to_player(player_id, board, show_hidden=True)
        send_msg_to_player(player_id, "[SYSTEM] Waiting for the other player to finish placing ships...")
        print(f"[DEBUG:run_multiplayer_game] Ship placement finished for {player_tag} ({player_id}).")


    game_active = True
    timeout_count = {player1_data['id']: 0, player2_data['id']: 0}
    MAX_TIMEOUTS = 2

    try:
        placement_threads = []
        placement_status = {}
        print("[DEBUG:run_multiplayer_game] Starting ship placement threads.")

        def placement_worker(player_id_worker):
            """Worker function for ship placement thread."""
            try:
                place_ships_for_player(player_id_worker)
                placement_status[player_id_worker] = "success"
            except (PlayerDisconnectedException, PlayerTimeoutException, Exception) as e:
                print(f"[ERROR:run_multiplayer_game] Exception during placement worker for {player_id_worker}: {type(e).__name__}: {e}")
                placement_status[player_id_worker] = e

        for player_data in [player1_data, player2_data]:
            player_id_for_thread = player_data['id']
            thread = threading.Thread(target=placement_worker, args=(player_id_for_thread,))
            placement_threads.append(thread)
            thread.start()

        print("[DEBUG:run_multiplayer_game] Waiting for placement threads to join.")
        for thread in placement_threads:
            thread.join()
        print("[DEBUG:run_multiplayer_game] Placement threads joined.")

        print("[DEBUG:run_multiplayer_game] Checking placement status.")
        for player_data in [player1_data, player2_data]:
             p_id_check = player_data['id']
             status = placement_status.get(p_id_check)
             if isinstance(status, Exception):
                 print(f"[INFO:run_multiplayer_game] Placement failed for {p_id_check} with exception: {type(status).__name__}")
                 other_player_id = player2_data['id'] if p_id_check == player1_data['id'] else player1_data['id']
                 send_msg_to_player(other_player_id, f"[SYSTEM] {player_tags[p_id_check]} failed to place ships ({type(status).__name__}: {status}). Game ending.")
                 raise status
             elif status != "success":
                 print(f"[ERROR:run_multiplayer_game] Unexpected placement status for {p_id_check}: {status}")
                 raise Exception(f"Unexpected placement status for {p_id_check}: {status}")

        print("[DEBUG:run_multiplayer_game] Ship placement successful for both players. Starting main game loop.")

        send_msg_to_player(player1_data['id'], "[SYSTEM] Both players have placed ships. The battle begins!")
        send_msg_to_player(player2_data['id'], "[SYSTEM] Both players have placed ships. The battle begins!")
        broadcast_board_func(player_boards[player1_data['id']], player_boards[player2_data['id']])


        turn_count = 0
        print("[DEBUG:run_multiplayer_game] Entering main game loop.")

        while game_active:
            current_player_id = player1_data['id'] if turn_count % 2 == 0 else player2_data['id']
            opponent_player_id = player2_data['id'] if turn_count % 2 == 0 else player1_data['id']
            current_player_tag = player_tags[current_player_id]
            opponent_player_tag = player_tags[opponent_player_id]

            target_board = player_boards[opponent_player_id]
            current_player_queue = player_queues[current_player_id]

            print(f"[DEBUG:run_multiplayer_game] Start of turn {turn_count+1}. Current player: {current_player_tag} ({current_player_id})")

            send_msg_to_player(current_player_id, f"\n--- {current_player_tag}, it's your turn! ---")
            send_msg_to_player(current_player_id, f"[SYSTEM] Your view of {opponent_player_tag}'s board:")
            send_board_to_player(current_player_id, target_board, show_hidden=False)

            send_msg_to_player(current_player_id, f"[SYSTEM] You have {INACTIVITY_TIMEOUT} seconds to make your move.")

            send_msg_to_player(opponent_player_id, f"\n[SYSTEM] Waiting for {current_player_tag} to make a move...")


            guess_input = None
            try:
                print(f"[DEBUG:run_multiplayer_game] {current_player_tag} ({current_player_id}) is waiting for move input from queue (timeout: {INACTIVITY_TIMEOUT}s).")
                guess_input = current_player_queue.get(timeout=INACTIVITY_TIMEOUT)
                print(f"[DEBUG:run_multiplayer_game] {current_player_tag} ({current_player_id}) received input from queue: '{guess_input}'")

                timeout_count[current_player_id] = 0

            except queue.Empty:
                 print(f"[DEBUG:run_multiplayer_game] {current_player_tag} ({current_player_id}) queue get timed out.")
                 timeout_count[current_player_id] += 1

                 timeout_msg = f"{current_player_tag} did not provide a valid move within {INACTIVITY_TIMEOUT} seconds. "

                 if timeout_count[current_player_id] >= MAX_TIMEOUTS:
                     forfeit_msg = f"[SYSTEM] {current_player_tag} has forfeited the game due to {MAX_TIMEOUTS} consecutive timeouts."
                     print(f"[GAME INFO] {forfeit_msg}")

                     send_msg_to_player(current_player_id,
                                       f"[SYSTEM] You have forfeited the game due to {MAX_TIMEOUTS} consecutive timeouts. Game over.")

                     send_msg_to_player(opponent_player_id,
                                       f"\n[SYSTEM] {forfeit_msg} You win!")

                     game_active = False
                     break
                 else:
                     timeout_msg += f"Turn skipped ({timeout_count[current_player_id]}/{MAX_TIMEOUTS} strikes)."
                     print(f"[GAME INFO] {timeout_msg}")

                     send_msg_to_player(current_player_id,
                                       f"[SYSTEM] You did not provide a move in time. Your turn has been skipped. "
                                       f"Warning: {timeout_count[current_player_id]}/{MAX_TIMEOUTS} timeouts.")

                     send_msg_to_player(opponent_player_id,
                                       f"\n[SYSTEM] {current_player_tag} did not provide a move in time. Their turn has been skipped. "
                                       f"Warning: They have {timeout_count[current_player_id]}/{MAX_TIMEOUTS} timeouts.")

                 turn_count += 1
                 continue

            if guess_input is not None:
                print(f"[DEBUG:run_multiplayer_game] {current_player_tag} ({current_player_id}) processing input '{guess_input}' as a potential move.")
                try:
                    row, col = parse_coordinate(guess_input)
                    result, sunk_ship = target_board.fire_at(row, col)

                    broadcast_board_func(player_boards[player1_data['id']], player_boards[player2_data['id']])

                    msg_for_active_player = f"You fired at {guess_input.upper()}: "
                    msg_for_opponent = f"{current_player_tag} fired at {guess_input.upper()}: "

                    if result == 'hit':
                        if sunk_ship:
                            msg_for_active_player += f"[SYSTEM] HIT! You sank their {sunk_ship}!"
                            msg_for_opponent += f"[SYSTEM] HIT! Your {sunk_ship} has been SUNK!"
                        else:
                            msg_for_active_player += "[SYSTEM] HIT!"
                            msg_for_opponent += "[SYSTEM] HIT on one of your ships!"
                    elif result == 'miss':
                        msg_for_active_player += "[SYSTEM] MISS."
                        msg_for_opponent += "[SYSTEM] MISS."
                    elif result == 'already_shot':
                        msg_for_active_player += "[SYSTEM] ALREADY SHOT there. Your turn is wasted."
                        msg_for_opponent += "[SYSTEM] They fired at an already targeted location."
                    elif result == 'error':
                         msg_for_active_player += f"[SYSTEM] Error firing: {sunk_ship}"
                         msg_for_opponent += f"[SYSTEM] Opponent's fire resulted in an error: {sunk_ship}"
                         print(f"[ERROR:run_multiplayer_game] Error result from fire_at: {sunk_ship}")


                    send_msg_to_player(current_player_id, msg_for_active_player)
                    send_msg_to_player(opponent_player_id, msg_for_opponent)

                    send_msg_to_player(opponent_player_id, f"\n[SYSTEM] {opponent_player_tag}'s board after {current_player_tag}'s shot:")
                    send_board_to_player(opponent_player_id, target_board, show_hidden=True)


                    if target_board.all_ships_sunk():
                        game_active = False
                        final_win_msg = f"[SYSTEM] GAME OVER! {current_player_tag} WINS! All {opponent_player_tag}'s ships are sunk."
                        print(f"[GAME INFO] Game ended. {current_player_tag} wins.")
                        send_msg_to_player(current_player_id, final_win_msg)
                        send_msg_to_player(current_player_id, f"\n[SYSTEM] Final state of {opponent_player_tag}'s board (what you saw):")
                        send_board_to_player(current_player_id, target_board, show_hidden=False)

                        send_msg_to_player(opponent_player_id, final_win_msg)
                        send_msg_to_player(opponent_player_id, f"\n[SYSTEM] Your final board state (all ships shown):")
                        send_board_to_player(opponent_player_id, target_board, show_hidden=True)
                        break
                    else:
                         turn_count += 1

                except ValueError as e_parse_fire:
                    print(f"[DEBUG:run_multiplayer_game] Invalid move format from {current_player_tag}: '{guess_input}' - {e_parse_fire}")
                    send_msg_to_player(current_player_id, f"[!] Invalid move input ('{guess_input}'): {e_parse_fire}. Please provide a valid coordinate.")
                    continue


    except (PlayerDisconnectedException, Exception) as e_game_end:
         print(f"[GAME INFO] Game ended due to exception: {type(e_game_end).__name__}: {e_game_end}")
         game_active = False

    finally:
        print(f"[INFO:run_multiplayer_game] run_multiplayer_game is concluding for players {player1_data['id']} and {player2_data['id']}.")


def run_single_player_game_locally():
    """
    PROJECT DETAILS - Runs a local, single-player version of the game for testing the core logic.
    """
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
    print(f"[DEBUG] Script started. Calling main().")
    run_single_player_game_locally()
    print(f"[DEBUG] main() finished.")