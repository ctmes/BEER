"""
battleship.py

Main code for our Battleship game:
 - Board class to track ships, hits, etc
 - coordinate parsing (like turning B5 into actual grid positions)
 - single-player mode for quick testing
 - multiplayer support with some basic timeout stuff
"""

import random
import threading
import socket  # need this for error types
import time    # for timeouts
import queue   # thread communication


# globals
BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2)
]

# TODO: make this configurable from settings file
INACTIVITY_TIMEOUT = 60  # seconds before we skip a player's turn


class PlayerDisconnectedException(Exception):
    """When a player disconnects mid-game"""
    pass


class PlayerTimeoutException(Exception):
    """When a player doesn't respond for too long"""
    pass


class Board:
    """
    Represents a battleship board with ships
    """

    def __init__(self, size=BOARD_SIZE):
        self.size = size
        # hidden grid has the ships, display is what opponent sees
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.placed_ships = []  # will contain ship info

    def place_ships_randomly(self, ships=SHIPS):
        for ship_name, ship_size in ships:
            placed = False
            tries = 0  # just in case we get stuck in a loop
            while not placed and tries < 100:
                tries += 1
                horizontal = random.randint(0, 1) == 0  # true=horizontal, false=vertical
                orientation = 0 if horizontal else 1  # code uses 0/1 internally

                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)

                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({'name': ship_name, 'positions': occupied_positions.copy()})
                    placed = True

    def place_ships_manually(self, ships=SHIPS):
        print("\nLet's place your ships on the board.")
        for ship_name, ship_len in ships:
            while True:
                self.print_display_grid(show_hidden_board=True)
                print(f"\nPlacing your {ship_name} (size {ship_len}).")
                coord_str = input("  Where to start? (e.g. A1): ").strip()
                orientation_str = input("  Direction? ('H' for horizontal, 'V' for vertical): ").strip().upper()

                try:
                    row, col = parse_coordinate(coord_str)
                except ValueError as e:
                    print(f"  [!] Bad coordinate: {e}")
                    continue

                # convert orientation to internal format
                if orientation_str == 'H':
                    orientation = 0
                elif orientation_str == 'V':
                    orientation = 1
                else:
                    print("  [!] I need 'H' or 'V' for direction. Try again.")
                    continue

                if self.can_place_ship(row, col, ship_len, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_len, orientation)
                    self.placed_ships.append({'name': ship_name, 'positions': occupied_positions.copy()})
                    break
                else:
                    print(f"  [!] Can't put {ship_name} at {coord_str} ({orientation_str}). Check if it fits or overlaps other ships.")

    def can_place_ship(self, row, col, ship_size, orientation):
        # Check if we can put the ship here
        if orientation == 0:  # Horizontal
            if col + ship_size > self.size:  # ship would go off the right edge
                return False
            if row < 0 or row >= self.size:  # row out of bounds
                return False

            # Check if spaces are empty
            for c_offset in range(ship_size):
                if self.hidden_grid[row][col + c_offset] != '.':
                    return False
        else:  # Vertical
            if row + ship_size > self.size:  # ship would go off the bottom
                return False
            if col < 0 or col >= self.size:  # column out of bounds
                return False

            # Check if spaces are empty
            for r_offset in range(ship_size):
                if self.hidden_grid[row + r_offset][col] != '.':
                    return False

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
        # Fire at the given spot
        cell = self.hidden_grid[row][col]

        if cell == 'S':  # Hit a ship!
            self.hidden_grid[row][col] = 'X'
            self.display_grid[row][col] = 'X'
            sunk_ship_name = self._mark_hit_and_check_sunk(row, col)
            return ('hit', sunk_ship_name)
        elif cell == '.':  # Miss
            self.hidden_grid[row][col] = 'o'
            self.display_grid[row][col] = 'o'
            return ('miss', None)
        elif cell in ('X', 'o'):  # Already shot here
            return ('already_shot', None)

        # something weird happened
        return ('error', "Unknown cell state")

    def _mark_hit_and_check_sunk(self, row, col):
        # Mark a hit on a ship and check if it sank
        for ship in self.placed_ships:
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if len(ship['positions']) == 0:
                    return ship['name']  # whole ship is sunk!
                break
        return None  # ship was hit but not sunk

    def all_ships_sunk(self):
        if not self.placed_ships:
            return False  # no ships placed yet

        # Check if all ships have empty position sets
        for ship in self.placed_ships:
            if len(ship['positions']) > 0:
                return False
        return True

    def print_display_grid(self, show_hidden_board=False):  # For local testing
        grid_to_print = self.hidden_grid if show_hidden_board else self.display_grid

        # Print column headers (1-10)
        print("  " + "".join(str(i + 1).rjust(2) for i in range(self.size)))

        # Print each row with label
        for r_idx in range(self.size):
            row_label = chr(ord('A') + r_idx)
            row_str = " ".join(grid_to_print[r_idx][c_idx] for c_idx in range(self.size))
            print(f"{row_label:2} {row_str}")


def parse_coordinate(coord_str):
    coord_str = coord_str.strip().upper()

    # Basic validation
    if len(coord_str) < 2 or len(coord_str) > 3:
        raise ValueError(f"Bad format '{coord_str}'. Should be like A1 or J10.")

    # Split into letter and number parts
    row_letter = coord_str[0]
    col_digits = coord_str[1:]

    # Check valid letter (A-J for 10x10)
    if not ('A' <= row_letter < chr(ord('A') + BOARD_SIZE)):
        raise ValueError(f"Row letter '{row_letter}' is wrong. Need A-{chr(ord('A') + BOARD_SIZE - 1)}.")

    # Make sure column part is a number
    if not col_digits.isdigit():
        raise ValueError(f"Column part '{col_digits}' isn't a number.")

    # Convert to actual row/col numbers
    col = int(col_digits) - 1  # Humans start at 1, we start at 0
    row = ord(row_letter) - ord('A')  # A=0, B=1, etc.

    # Check within board bounds
    if row < 0 or row >= BOARD_SIZE or col < 0 or col >= BOARD_SIZE:
        raise ValueError(f"Coordinate {row_letter}{int(col_digits)} is outside the board (A1-{chr(ord('A') + BOARD_SIZE - 1)}{BOARD_SIZE}).")

    return (row, col)


# Network game handling stuff below
def run_multiplayer_game(player1_data, player2_data, p1_input_queue, p2_input_queue, send_message_func, broadcast_board_func):
    """
    Main multiplayer game function - manages a complete game between two players

    Args:
        player1_data (dict): Player 1 info
        player2_data (dict): Player 2 info
        p1_input_queue (queue.Queue): Queue for Player 1 input
        p2_input_queue (queue.Queue): Queue for Player 2 input
        send_message_func (callable): Function to send messages to players
        broadcast_board_func (callable): Function to update spectators
    """
    # Setup player data with shorter names for readability
    player_tags = {player1_data['id']: "Player 1", player2_data['id']: "Player 2"}
    player_ids = {"Player 1": player1_data['id'], "Player 2": player2_data['id']}
    player_boards = {player1_data['id']: Board(BOARD_SIZE), player2_data['id']: Board(BOARD_SIZE)}
    player_queues = {player1_data['id']: p1_input_queue, player2_data['id']: p2_input_queue}

    # --- Helper Functions ---
    def send_msg_to_player(player_id, message):
        send_message_func(player_id, message)

    def send_board_to_player(player_id, board_to_send, show_hidden=False):
         # Format the board as text and send it to the player
         try:
            grid_to_print = board_to_send.hidden_grid if show_hidden else board_to_send.display_grid
            message_lines = ["GRID"]
            header = "  " + "".join(str(i + 1).rjust(2) for i in range(board_to_send.size))
            message_lines.append(header)

            for r_idx in range(board_to_send.size):
                row_label = chr(ord('A') + r_idx)
                row_content = " ".join(grid_to_print[r_idx][c_idx] for c_idx in range(board_to_send.size))
                message_lines.append(f"{row_label:2} {row_content}")

            message_lines.append("") # Empty line = end of grid
            send_message_func(player_id, "\n".join(message_lines))

         except Exception as e:
             print(f"[ERROR] Failed to send board to {player_id}: {e}")
             # Server should've handled disconnects already
             pass

    # --- Ship Placement Phase ---
    def place_ships_for_player(player_id):
        board = player_boards[player_id]
        player_tag = player_tags[player_id]
        player_queue = player_queues[player_id]
        print(f"[DEBUG] Starting ship placement for {player_tag} ({player_id}).")

        send_msg_to_player(player_id, f"[SYSTEM] Welcome, {player_tag}! Time to place your ships.")

        for ship_name, ship_size in SHIPS:
            while True:  # Loop until this ship is placed
                send_msg_to_player(player_id, f"\n[SYSTEM] {player_tag}, here's your board:")
                send_board_to_player(player_id, board, show_hidden=True)
                send_msg_to_player(player_id, f"[SYSTEM] Place your {ship_name} (size {ship_size}).")
                send_msg_to_player(player_id, "[SYSTEM] Enter start coordinate (like A1):")

                try:
                    # Get starting position
                    print(f"[DEBUG] {player_tag} ({player_id}) waiting for coordinate input...")
                    coord_str = player_queue.get(timeout=INACTIVITY_TIMEOUT * 2)
                    print(f"[DEBUG] {player_tag} ({player_id}) entered: '{coord_str}'")

                    # Player wants to quit?
                    if coord_str.lower() == 'quit':
                        raise PlayerDisconnectedException(f"{player_id} quit during ship placement.")

                    # Get orientation
                    send_msg_to_player(player_id, "[SYSTEM] Enter orientation ('H' or 'V'):")
                    print(f"[DEBUG] {player_tag} ({player_id}) waiting for orientation...")
                    orient_str = player_queue.get(timeout=INACTIVITY_TIMEOUT * 2).upper()
                    print(f"[DEBUG] {player_tag} ({player_id}) entered orient: '{orient_str}'")

                    if orient_str.lower() == 'quit':
                         raise PlayerDisconnectedException(f"{player_id} quit during ship placement.")

                    # Process the inputs
                    row, col = parse_coordinate(coord_str)

                    # Convert orientation string to internal number
                    orientation_val = -1  # invalid default
                    if orient_str == 'H':
                        orientation_val = 0
                    elif orient_str == 'V':
                        orientation_val = 1

                    # Error checks
                    if orientation_val == -1:
                        send_msg_to_player(player_id, "[!] I need 'H' for horizontal or 'V' for vertical. Try again.")
                        continue

                    # Try to place the ship
                    if board.can_place_ship(row, col, ship_size, orientation_val):
                        positions = board.do_place_ship(row, col, ship_size, orientation_val)
                        board.placed_ships.append({'name': ship_name, 'positions': positions.copy()})
                        send_msg_to_player(player_id, f"[SYSTEM] {ship_name} placed successfully at {coord_str}{orient_str}.")
                        break  # Ship placed, go to next ship
                    else:
                        send_msg_to_player(player_id, f"[!] Can't place {ship_name} at {coord_str}{orient_str}. It doesn't fit or overlaps. Try again.")

                except queue.Empty:
                    # Player took too long
                    print(f"[DEBUG] {player_tag} ({player_id}) placement timeout.")
                    raise PlayerTimeoutException(f"{player_id} took too long during ship placement (>{INACTIVITY_TIMEOUT * 2}s)")

                except ValueError as e:  # Coordinate parsing error
                    print(f"[DEBUG] {player_tag} ({player_id}) bad input: {e}")
                    send_msg_to_player(player_id, f"[!] Invalid input: {e}. Try again.")

                except PlayerDisconnectedException:
                    raise  # Pass this up the chain

                except Exception as e:
                     print(f"[ERROR] Weird error during placement for {player_id}: {type(e).__name__}: {e}")
                     send_msg_to_player(player_id, f"[SYSTEM] Something went wrong. Let's try again.")

        # All ships placed
        send_msg_to_player(player_id, f"\n[SYSTEM] {player_tag}, all ships placed!")
        send_board_to_player(player_id, board, show_hidden=True)
        send_msg_to_player(player_id, "[SYSTEM] Waiting for the other player...")
        print(f"[DEBUG] Ship placement done for {player_tag} ({player_id}).")


    # --- Main Game Logic ---
    game_active = True  # Controls main game loop
    timeout_count = {player1_data['id']: 0, player2_data['id']: 0}  # Track timeouts
    MAX_TIMEOUTS = 2  # Forfeit after this many consecutive timeouts


    try:
        # --- Set up ship placement threads ---
        placement_threads = []
        placement_status = {}  # Will hold results of placement
        print("[DEBUG] Starting placement threads.")

        def placement_worker(player_id_worker):
            # Thread function for ship placement
            try:
                place_ships_for_player(player_id_worker)
                placement_status[player_id_worker] = "success"
            except (PlayerDisconnectedException, PlayerTimeoutException, Exception) as e:
                print(f"[ERROR] Problem with placement for {player_id_worker}: {type(e).__name__}: {e}")
                placement_status[player_id_worker] = e

        # Start a thread for each player's ship placement
        for player_data in [player1_data, player2_data]:
            p_id = player_data['id']
            thread = threading.Thread(target=placement_worker, args=(p_id,))
            placement_threads.append(thread)
            thread.start()

        print("[DEBUG] Waiting for placement to finish.")
        for thread in placement_threads:
            thread.join()  # Wait for placements to complete
        print("[DEBUG] Placement threads finished.")

        # Check how placement went
        print("[DEBUG] Checking placement results.")
        for player_data in [player1_data, player2_data]:
             p_id = player_data['id']
             status = placement_status.get(p_id)

             if isinstance(status, Exception):
                 # Something went wrong during placement
                 print(f"[INFO] Placement failed for {p_id}: {type(status).__name__}")

                 # Let the other player know what happened
                 other_p_id = player2_data['id'] if p_id == player1_data['id'] else player1_data['id']
                 send_msg_to_player(other_p_id, f"[SYSTEM] {player_tags[p_id]} couldn't place ships ({type(status).__name__}). Game over.")
                 raise status

             elif status != "success":
                 # Should never happen, but just in case
                 print(f"[ERROR] Unexpected placement status for {p_id}: {status}")
                 raise Exception(f"Weird placement status for {p_id}: {status}")

        print("[DEBUG] Ships placed successfully. Starting battle phase!")

        # Ready to play
        send_msg_to_player(player1_data['id'], "[SYSTEM] Both players ready. Let the battle begin!")
        send_msg_to_player(player2_data['id'], "[SYSTEM] Both players ready. Let the battle begin!")
        broadcast_board_func(player_boards[player1_data['id']], player_boards[player2_data['id']])  # Update spectators


        # --- Main Game Loop ---
        turn_count = 0
        print("[DEBUG] Starting main game turns.")

        while game_active:
            # Figure out whose turn it is
            current_player_id = player1_data['id'] if turn_count % 2 == 0 else player2_data['id']
            opponent_player_id = player2_data['id'] if turn_count % 2 == 0 else player1_data['id']
            current_player_tag = player_tags[current_player_id]
            opponent_player_tag = player_tags[opponent_player_id]

            target_board = player_boards[opponent_player_id]  # Board to shoot at
            current_player_queue = player_queues[current_player_id]

            print(f"[DEBUG] Turn {turn_count+1}: {current_player_tag}'s turn")

            # Tell players what's happening
            send_msg_to_player(current_player_id, f"\n--- {current_player_tag}, your turn! ---")
            send_msg_to_player(current_player_id, f"[SYSTEM] Your view of {opponent_player_tag}'s board:")
            send_board_to_player(current_player_id, target_board, show_hidden=False)  # Don't show hidden ships

            # Let them know about the timeout
            send_msg_to_player(current_player_id, f"[SYSTEM] You have {INACTIVITY_TIMEOUT} seconds to make your move.")

            # Let the other player know they're waiting
            send_msg_to_player(opponent_player_id, f"\n[SYSTEM] Waiting for {current_player_tag} to move...")

            # Get their move
            guess_input = None
            try:
                print(f"[DEBUG] {current_player_tag} ({current_player_id}) waiting for move input...")
                guess_input = current_player_queue.get(timeout=INACTIVITY_TIMEOUT)
                print(f"[DEBUG] {current_player_tag} ({current_player_id}) entered: '{guess_input}'")

                # Reset timeout counter since they responded
                timeout_count[current_player_id] = 0

            except queue.Empty:
                 # They took too long
                 print(f"[DEBUG] {current_player_tag} ({current_player_id}) timed out.")
                 timeout_count[current_player_id] += 1

                 timeout_msg = f"{current_player_tag} took too long (>{INACTIVITY_TIMEOUT}s). "

                 if timeout_count[current_player_id] >= MAX_TIMEOUTS:
                     # Too many timeouts = forfeit
                     forfeit_msg = f"[SYSTEM] {current_player_tag} forfeits after {MAX_TIMEOUTS} timeouts."
                     print(f"[GAME INFO] {forfeit_msg}")

                     send_msg_to_player(current_player_id,
                                       f"[SYSTEM] You forfeited after {MAX_TIMEOUTS} timeouts. Game over.")

                     send_msg_to_player(opponent_player_id,
                                       f"\n[SYSTEM] {forfeit_msg} You win!")

                     game_active = False
                     break
                 else:
                     # First timeout, just skip turn
                     timeout_msg += f"Turn skipped ({timeout_count[current_player_id]}/{MAX_TIMEOUTS} strikes)."
                     print(f"[GAME INFO] {timeout_msg}")

                     send_msg_to_player(current_player_id,
                                       f"[SYSTEM] Move timeout. Turn skipped. "
                                       f"Warning: {timeout_count[current_player_id]}/{MAX_TIMEOUTS} timeouts.")

                     send_msg_to_player(opponent_player_id,
                                       f"\n[SYSTEM] {current_player_tag} timed out. Their turn was skipped. "
                                       f"They have {timeout_count[current_player_id]}/{MAX_TIMEOUTS} timeouts.")

                 # Next player's turn
                 turn_count += 1
                 continue

            # Process their move (if we got one)
            if guess_input is not None:
                print(f"[DEBUG] Processing move: '{guess_input}'")
                try:
                    # Convert coordinate string to board position
                    row, col = parse_coordinate(guess_input)

                    # Fire at that spot
                    result, sunk_ship = target_board.fire_at(row, col)

                    # Update anyone watching
                    broadcast_board_func(player_boards[player1_data['id']], player_boards[player2_data['id']])

                    # Prepare messages
                    msg_for_active_player = f"You fired at {guess_input.upper()}: "
                    msg_for_opponent = f"{current_player_tag} fired at {guess_input.upper()}: "

                    # Handle different shot results
                    if result == 'hit':
                        if sunk_ship:
                            msg_for_active_player += f"[SYSTEM] HIT! You sank their {sunk_ship}!"
                            msg_for_opponent += f"[SYSTEM] HIT! Your {sunk_ship} was SUNK!"
                        else:
                            msg_for_active_player += "[SYSTEM] HIT!"
                            msg_for_opponent += "[SYSTEM] HIT! One of your ships was hit!"
                    elif result == 'miss':
                        msg_for_active_player += "[SYSTEM] MISS!"
                        msg_for_opponent += "[SYSTEM] MISS!"
                    elif result == 'already_shot':
                        msg_for_active_player += "[SYSTEM] You already shot there! Turn wasted."
                        msg_for_opponent += "[SYSTEM] They fired at a spot they already tried."
                    elif result == 'error':
                         # This shouldn't happen but just in case
                         msg_for_active_player += f"[SYSTEM] Error: {sunk_ship}"
                         msg_for_opponent += f"[SYSTEM] Error with opponent's shot: {sunk_ship}"
                         print(f"[ERROR] fire_at error: {sunk_ship}")

                    # Send results to players
                    send_msg_to_player(current_player_id, msg_for_active_player)
                    send_msg_to_player(opponent_player_id, msg_for_opponent)

                    # Show opponent their updated board
                    send_msg_to_player(opponent_player_id, f"\n[SYSTEM] Your board after their shot:")
                    send_board_to_player(opponent_player_id, target_board, show_hidden=True)

                    # Check if game is over
                    if target_board.all_ships_sunk():
                        game_active = False  # Game over
                        final_msg = f"[SYSTEM] GAME OVER! {current_player_tag} WINS! All {opponent_player_tag}'s ships are sunk."
                        print(f"[GAME INFO] Game over. {current_player_tag} wins.")

                        # Send final info to winner
                        send_msg_to_player(current_player_id, final_msg)
                        send_msg_to_player(current_player_id, f"\n[SYSTEM] Final enemy board:")
                        send_board_to_player(current_player_id, target_board, show_hidden=False)

                        # Send final info to loser
                        send_msg_to_player(opponent_player_id, final_msg)
                        send_msg_to_player(opponent_player_id, f"\n[SYSTEM] Your final board:")
                        send_board_to_player(opponent_player_id, target_board, show_hidden=True)
                        break  # Exit game loop
                    else:
                         # Next turn
                         turn_count += 1

                except ValueError as e:  # Bad coordinate
                    print(f"[DEBUG] Bad coordinate: '{guess_input}' - {e}")
                    send_msg_to_player(current_player_id, f"[!] Invalid move '{guess_input}': {e}. Try again.")
                    # Don't change turns, they get to try again
                    continue

    except (PlayerDisconnectedException, Exception) as e:
         # Handle any other errors
         print(f"[GAME INFO] Game interrupted: {type(e).__name__}: {e}")
         game_active = False

    finally:
        print(f"[INFO] Game ending for {player1_data['id']} vs {player2_data['id']}.")

        # Update server with final board state
        try:
            import server
            with server.lock:
                server.active_games[player1_data['id']]["board"] = player_boards[player1_data['id']]
                server.active_games[player2_data['id']]["board"] = player_boards[player2_data['id']]
        except Exception as e:
            print(f"[DEBUG] Couldn't save final boards: {e}")


# Single player test mode (unchanged)
def run_single_player_game_locally():
    board = Board(BOARD_SIZE)

    # Ask how to place ships
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
            print("Thanks for playing! Exiting...")
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
    # Just for local testing, server runs the multiplayer game
    print("Running local single-player game for testing...")
    run_single_player_game_locally()