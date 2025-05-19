# server.py

import socket
import threading
import time
import gc
import queue
from battleship import Board, parse_coordinate, SHIPS, BOARD_SIZE, run_multiplayer_game, PlayerDisconnectedException, PlayerTimeoutException
from packet import pack_packet, SYSTEM_MESSAGE, receive_packet, USER_INPUT

HOST = '127.0.0.1'
PORT = 5001

# Global server state
# Added 'last_input_time' to client data for input rate limiting
clients = {} # {client_id: 
                #{"r": rfile, "w": wfile, 
                # "addr": addr, 
                # "id": client_id, 
                # "role": "player" or "spectator", 
                # "input_queue": queue.Queue() if player, 
                # "last_input_time": float, 
                # "socket": socket_obj}}

disconnected_players = {}
active_games = {}  # {username:
                #        {"board": ..., 
                #         "rfile": ..., 
                #         "wfile": ..., 
                #         "disconnected": False, 
                #         "reconnect_deadline": None, ...}}
                
players_waiting = [] # List of client_ids waiting for a game
spectators_waiting = [] # List of client_ids waiting for a game or spectating
game_in_progress = False
game_thread = None # Thread for the current game instance
lock = threading.RLock() # Lock for accessing shared server state

GAME_START_COUNTDOWN = 5  # seconds
RECONNECT_TIMEOUT = 30

# --- Rate Limiting and Connection Limits ---
MAX_CONNECTIONS = 6
INPUT_RATE_LIMIT_PER_SECOND = 10
INPUT_RATE_DELAY = 1.0 / INPUT_RATE_LIMIT_PER_SECOND

print(f"[DEBUG] SERVER.PY: <module>: Initializing server with HOST: {HOST}, PORT: {PORT}")


def send_message_to_client(client_id, message, pkt_type=SYSTEM_MESSAGE):
    """Safely sends a message to a client."""
    # print(f"[DEBUG] SERVER.PY: send_message_to_client: Attempting to send message to {client_id}: {message[:50]}...") # Log message attempt
    with lock:
        client_data = clients.get(client_id)
        conn = client_data.get("socket") if client_data else None
    if conn:
        try:
            packet = pack_packet(0, pkt_type, message.encode())
            conn.sendall(packet)
        except (socket.error, BrokenPipeError, ConnectionResetError) as e:
            print(f"[INFO] Client {client_id} disconnected during send: {e}")
            # Connection lost, handle removal
            remove_client(client_id)
        except Exception as e:
             print(f"[ERROR] SERVER.PY: send_message_to_client: Unexpected error sending to {client_id}: {e}")
             remove_client(client_id)
        # else:
            # print(f"[DEBUG] SERVER.PY: send_message_to_client: Attempted to send to non-existent or closed client {client_id}")


def broadcast_to_all(message, sender_id=None):
    """Broadcasts a message to all connected clients except the sender."""
    # print(f"[DEBUG] SERVER.PY: broadcast_to_all: Broadcasting message: '{message}'") # Too verbose
    client_ids_to_send = []
    with lock:
        client_ids_to_send = list(clients.keys())

    for client_id in client_ids_to_send:
        if client_id != sender_id:
            send_message_to_client(client_id, message)

def get_client_username(conn, addr):
    """Prompt the client for a username using the packet protocol. Returns None if not received."""
    try:
        # Send prompt as a SYSTEM_MESSAGE packet
        prompt_packet = pack_packet(0, SYSTEM_MESSAGE, b"Enter your username:")
        conn.sendall(prompt_packet)

        # Receive the response packet
        result = receive_packet(conn)
        if result is None:
            print(f"[ERROR] SERVER.PY: get_client_username: No valid packet received from {addr}. Closing connection.")
            return None

        seq, pkt_type, payload = result
        if pkt_type != USER_INPUT:
            print(f"[ERROR] SERVER.PY: get_client_username: Expected USER_INPUT, got {pkt_type} from {addr}")
            return None

        username = payload.decode().strip()
        if not username:
            print(f"[ERROR] SERVER.PY: get_client_username: No username received or username empty from {addr}.")
            return None
        return username
    except Exception as e:
        print(f"[ERROR] SERVER.PY: get_client_username: Failed during packet-based username exchange: {e}")
        return None
    
def broadcast_game_board_state(player1_board, player2_board):
    """Sends the current public board state to all spectators."""
    # Format the boards side-by-side
    board_message = "GRID\n" # Indicate start of grid data
    board_message += "PLAYER 1                  PLAYER 2\n"
    # Calculate separator length based on expected grid width + spacing
    separator_len = (BOARD_SIZE * 2) + 2 + len("    |    ") + (BOARD_SIZE * 2) + 2 # Adjusted length calculation
    board_message += "-" * (separator_len if separator_len > 0 else 40) + "\n" # Ensure min length

    p1_grid = player1_board.display_grid
    p2_grid = player2_board.display_grid

    for r_idx in range(BOARD_SIZE):
        row_label = chr(ord('A') + r_idx)

        row_p1 = " ".join(p1_grid[r_idx][c_idx] for c_idx in range(BOARD_SIZE))
        row_p2 = " ".join(p2_grid[r_idx][c_idx] for c_idx in range(BOARD_SIZE))

        board_message += f"{row_label:2} {row_p1}    |    {row_label:2} {row_p2}\n"
    board_message += "\n" # Indicate end of grid data

    with lock:
        spectator_ids = [cid for cid, data in clients.items() if data.get("role") == "spectator"]

    for spec_id in spectator_ids:
         send_message_to_client(spec_id, board_message)
    # print("[DEBUG] SERVER.PY: broadcast_game_board_state: Broadcasted game board state to spectators.")


def handle_command(client_id, command):
    """Handles commands received from clients."""
    print(f"[DEBUG] SERVER.PY: handle_command: {client_id} issued command: {command}")

    command_parts = command.lower().strip().split(maxsplit=1)
    cmd = command_parts[0]
    args = command_parts[1] if len(command_parts) > 1 else ""

    client_role = None
    with lock:
        client_data = clients.get(client_id)
        if client_data:
            client_role = client_data.get("role")

    if cmd == "/help":
        if client_role == "player":
            help_text = "Available commands: /help, /quit, /chat <message>"
        elif client_role == "spectator":
             help_text = "Available commands: /help, /quit, /status, /chat <message>"
        else: # Should not happen if role is set correctly
             help_text = "Available commands: /help, /quit (You are in a transitional state)"

        send_message_to_client(client_id, f"[SYSTEM] {help_text}")

    elif cmd == "/status":
        if client_role == "player":
            with lock: # Access game_in_progress state under lock
                if game_in_progress:
                    send_message_to_client(client_id, "[SYSTEM] You are currently playing a game.")
                else:
                    # Player role but game not in progress - should only happen briefly
                    send_message_to_client(client_id, "[SYSTEM] You are registered as a player. Waiting for the game to start.")
        elif client_role == "spectator":
            with lock:
                try:
                    # Find position in the combined waiting queue
                    combined_queue = players_waiting + spectators_waiting
                    position = -1
                    for i, cid in enumerate(combined_queue):
                         if cid == client_id:
                              position = i + 1
                              break

                    if position != -1:
                        send_message_to_client(client_id, f"[SYSTEM] You are #{position} in the queue.")
                        if game_in_progress:
                            remaining_in_queue = len(combined_queue) - position
                            # Simple estimate: 2 players per game
                            games_to_wait = (remaining_in_queue + 1) // 2
                            if games_to_wait == 0:
                                 send_message_to_client(client_id, "[SYSTEM] You will play in the next game!")
                            else:
                                 send_message_to_client(client_id, f"[SYSTEM] You will need to wait for approximately {games_to_wait} more game(s).")
                        else:
                            # No game in progress, estimate games to wait based on current queue size
                            estimated_games_in_queue = (len(players_waiting) + len(spectators_waiting) + 1) // 2
                            games_to_wait = max(0, estimated_games_in_queue - (position + 1) // 2) # crude estimate

                            if position <= 2:
                                send_message_to_client(client_id, "[SYSTEM] You are next in line for the game!")
                            else:
                                # Another crude estimate considering those who might become players first
                                games_to_wait_further = (position - (len(players_waiting) + 1)) // 2 + 1 if len(players_waiting) < 2 else (position - 3) // 2 + 1 # rough estimate
                                send_message_to_client(client_id, f"[SYSTEM] Waiting for enough players. You are #{position} in queue.")


                    else:
                         send_message_to_client(client_id, "[SYSTEM] Could not determine your position in the queue.")
                except Exception as e:
                    print(f"[ERROR] SERVER.PY: handle_command: Error sending status to spectator {client_id}: {e}")


    elif cmd == "/quit":
        send_message_to_client(client_id, "[SYSTEM] You have chosen to quit. Disconnecting.")
        # Signal to remove client - removal happens outside command handling to avoid issues
        # Let the handle_client_input thread detect the connection close after sending this.
        # Or we could put a special message in the queue/flag for the handle_client_input thread.
        # For now, rely on connection close detection.
        pass # Removal is handled by the thread detecting disconnection

    elif cmd == "/chat":
         if args:
            # Format the chat message and broadcast
            # Use client ID as name for now, could use a player/spectator prefix
            sender_info = client_id
            with lock:
                 client_data = clients.get(client_id)
                 if client_data and client_data.get("role"):
                     sender_info = f"{client_data['role'].capitalize()} {client_id}"
            chat_message = f"[CHAT] {sender_info}: {args}"
            broadcast_to_all(chat_message, sender_id=client_id)
            print(f"[INFO] Chat from {client_id}: {args}")
         else:
             send_message_to_client(client_id, "[SYSTEM] Usage: /chat <your message>")

    else:
        send_message_to_client(client_id, f"[SYSTEM] Unknown command: {command}. Type /help for available commands.")


def handle_client_input(client_id):
    """Thread function to continuously read input from a client."""
    print(f"[DEBUG] SERVER.PY: handle_client_input: handle_client_input thread started for {client_id}")

    with lock:
        client_data = clients.get(client_id)
        conn = client_data["socket"] if client_data else None
        if not conn:
            print(f"[ERROR] SERVER.PY: handle_client_input started for unknown client_id {client_id}")
            return

    try:
        while True:
            result = receive_packet(conn)
            if not result:
                print(f"[INFO] Client {client_id} disconnected (no packet received).")
                break

            seq, pkt_type, payload = result
            line = payload.decode().strip()
            if not line:
                continue

            print(f"[DEBUG] SERVER.PY: handle_client_input: Received from {client_id}: '{line}'")

            # --- Input Rate Limiting Check ---
            current_time = time.time()
            with lock:
                client_data = clients.get(client_id)
                if client_data:
                    time_since_last_input = current_time - client_data['last_input_time']
                    if time_since_last_input < INPUT_RATE_DELAY:
                        send_message_to_client(client_id, "[SYSTEM] Input rate limit exceeded. Slow down.")
                        continue
                    client_data['last_input_time'] = current_time

                current_role = client_data.get("role") if client_data else None
                player_input_queue = client_data.get("input_queue") if client_data else None
                current_game_in_progress = game_in_progress

            if line.startswith('/'):
                handle_command(client_id, line)
            else:
                if current_role == "player" and current_game_in_progress and player_input_queue:
                    try:
                        print(f"[DEBUG:handle_client_input] Putting input '{line}' into {client_id}'s queue (Role: {current_role}, Game: {current_game_in_progress}).")
                        player_input_queue.put_nowait(line)
                    except queue.Full:
                        send_message_to_client(client_id, "[SYSTEM] Input queue is full. Please wait a moment.")
                    except Exception as e:
                        print(f"[ERROR:handle_client_input] Error putting input into {client_id}'s queue: {e}")
                        send_message_to_client(client_id, "[SYSTEM] An error occurred processing your input.")
                else:
                    sender_info = f"{current_role.capitalize()} {client_id}" if current_role else client_id
                    chat_message = f"[CHAT] {sender_info}: {line}"
                    broadcast_to_all(chat_message, sender_id=client_id)
                    print(f"[INFO] Chat from {client_id}: {line}")

    except Exception as e:
        print(f"[ERROR] SERVER.PY: handle_client_input: Error in handle_client_input for {client_id}: {e}")
    finally:
        print(f"[DEBUG] SERVER.PY: handle_client_input: handle_client_input thread for {client_id} ending. Ensuring client removal.")
        remove_client(client_id)
        print(f"[DEBUG] SERVER.PY: handle_client_input: Client input thread for {client_id} finished.")

def remove_client(client_id):
    print(f"[DEBUG] SERVER.PY: remove_client: Attempting to remove client {client_id}")

    with lock:
        client_data = clients.get(client_id)
        # If client is a player in an active game, mark as disconnected instead of full removal
        if client_id in active_games and active_games[client_id].get("disconnected") is False:
            print(f"[DEBUG] SERVER.PY: remove_client: {client_id} is a player in an active game. Marking as disconnected.")
            mark_player_disconnected(client_id, active_games)
            return  # Do not fully remove yet

        # Remove from waiting queues if present
        if client_id in players_waiting:
            players_waiting.remove(client_id)
            print(f"[DEBUG] SERVER.PY: remove_client: Removed {client_id} from players_waiting.")
        if client_id in spectators_waiting:
            spectators_waiting.remove(client_id)
            print(f"[DEBUG] SERVER.PY: remove_client: Removed {client_id} from spectators_waiting.")

        # Check if this client was one of the players in the active game
        if game_in_progress and game_thread and game_thread.is_alive():
            # We need a way to access the player IDs from the game_thread.
            # A robust way is for the game_thread to store/expose player IDs.
            # For now, let's rely on the game logic detecting the disconnection.
            # A more direct approach would involve signaling the game thread.
             pass # Game termination handled by game logic or wrapper detection


        else:
            print(f"[DEBUG] SERVER.PY: remove_client: Client {client_id} not found in clients dictionary during removal attempt.")


    if client_data:
        # Close file objects and socket outside the lock
        # Closing rfile/wfile should signal the corresponding thread reading/writing to them.
        # The socket itself should also be closed. Let's add socket closing if available.
        sock = client_data.get("socket") # Assuming we store socket object now
        if client_data.get("r") and not client_data["r"].closed:
            try: client_data["r"].close()
            except: pass
        if client_data.get("w") and not client_data["w"].closed:
            try: client_data["w"].close()
            except: pass
        if sock:
            try: sock.close()
            except: pass


    # Update spectator positions after removal if the removal affected the queue
    with lock:
        # Update positions if the removal affected the queue length
        # This check is simplified - any removal *could* affect positions
        print(f"[DEBUG] SERVER.PY: remove_client: Client removal occurred. Updating spectator positions.")
        update_spectator_positions()

    print(f"[DEBUG] SERVER.PY: remove_client: remove_client finished for {client_id}")
    # Check if game should start if enough players are now waiting
    # This might be redundant if run_game_wrapper calls check_start_game, but ensures
    # a game starts if players disconnect before a game starts.
    check_start_game()


def update_spectator_positions():
    """Informs spectators about their updated position in the queue."""
    print(f"[DEBUG] SERVER.PY: update_spectator_positions: update_spectator_positions called.")
    with lock:
        # Combine players_waiting and spectators_waiting to get the full queue
        current_queue = players_waiting + spectators_waiting
        # print(f"[DEBUG] SERVER.PY: update_spectator_positions: Current queue: {current_queue}") # Too verbose

        # Build messages first, then send outside this loop to minimize time under lock
        messages_to_send = [] # List of (client_id, message)

        for i, client_id in enumerate(current_queue):
            position = i + 1
            # Get client data to confirm role for messaging
            client_data = clients.get(client_id)
            if client_data: # Ensure client still exists
                try:
                    message = f"[SYSTEM] Queue update: You are now #{position} in line."
                    if position <= 2 and not game_in_progress:
                         message += " Preparing for your game soon..."
                    # More detailed wait time estimation could go here
                    messages_to_send.append((client_id, message))

                except Exception as e:
                    print(f"[ERROR] SERVER.PY: update_spectator_positions: Error preparing position update for {client_id}: {e}")
                    # This client might be disconnecting, handle removal later

        # Send messages outside the lock
        for client_id, message in messages_to_send:
             # remove_client might be called inside send_message_to_client,
             # modifying the clients dict. This is handled by send_message_to_client's check.
             send_message_to_client(client_id, message)

    print(f"[DEBUG] SERVER.PY: update_spectator_positions: update_spectator_positions finished.")


def recycle_players_to_spectators(game_player_ids):
    """Moves players from the just-finished game back to the spectator queue."""
    print(f"[DEBUG] SERVER.PY: recycle_players_to_spectators: Recycling players {game_player_ids} to spectators called.")
    with lock:
        recycled_count = 0
        for player_id in game_player_ids:
            client_data = clients.get(player_id)
            if client_data and client_data.get("role") == "player":
                # Check if client is still connected before trying to recycle
                if client_data:
                    # Close the socket outside the lock if it exists
                    sock = client_data.get("socket")
                    if sock:
                        try:
                            sock.close()
                        except:
                            pass
                    try:
                        send_message_to_client(player_id, "[SYSTEM] Game has ended. You are being returned to the spectator queue.")
                        client_data["role"] = "spectator" # Change role
                        client_data.pop("input_queue", None) # Remove player-specific queue
                        spectators_waiting.append(player_id) # Add back to waiting list
                        recycled_count += 1
                        print(f"[INFO] Recycled {player_id} to spectators queue.")
                    except Exception as e:
                         # If sending fails here, they are effectively disconnected
                        print(f"[INFO] Player {player_id} connection issue during recycling: {e}. Not recycling to queue.")
                        remove_client(player_id) # Ensure removal
                else:
                    print(f"[INFO] Player {player_id} already disconnected. Not recycling.")
                    # No need to call remove_client here, handle_client_input thread should have done it
                    # or it will be cleaned up by removing from clients dict.

        # Note: Disconnected players are not added back to spectators_waiting.
        # remove_client handles their removal from clients and existing waiting lists.

        print(f"[DEBUG] SERVER.PY: recycle_players_to_spectators: {recycled_count} players recycled.")
        print(f"[DEBUG] SERVER.PY: recycle_players_to_spectators: Players waiting after recycling: {players_waiting}")
        print(f"[DEBUG] SERVER.PY: recycle_players_to_spectators: Spectators waiting after recycling: {spectators_waiting}")
        # Update positions for those remaining in queue
        update_spectator_positions()
    print(f"[DEBUG] SERVER.PY: recycle_players_to_spectators: recycle_players_to_spectators finished.")


def promote_spectators_to_players():
    """Promotes the first two eligible clients from the waiting queue to players."""
    print(f"[DEBUG] SERVER.PY: promote_spectators_to_players: promote_spectators_to_players called.")
    promoted = False
    players_for_game = [] # Store client_ids of promoted players

    with lock:
        # Combine and filter for clients that are still connected
        combined_queue = players_waiting + spectators_waiting
        eligible_clients_ids = [cid for cid in combined_queue if cid in clients and clients[cid].get("socket")] # Check if connection is active

        print(f"[DEBUG] SERVER.PY: promote_spectators_to_players: Eligible clients in queue: {eligible_clients_ids}")

        if len(eligible_clients_ids) >= 2:
            print(f"[DEBUG] SERVER.PY: promote_spectators_to_players: Enough eligible clients ({len(eligible_clients_ids)}) to promote two.")
            # Promote the first two eligible clients
            players_for_game = eligible_clients_ids[:2]

            # Remove promoted players from the waiting queues and update roles/queues in clients dict
            for player_id in players_for_game:
                # Remove from whichever queue they were in
                if player_id in players_waiting:
                    players_waiting.remove(player_id)
                elif player_id in spectators_waiting:
                    spectators_waiting.remove(player_id)

                # Update client data
                client_data = clients.get(player_id)
                if client_data:
                    client_data["role"] = "player"
                    client_data["input_queue"] = queue.Queue() # Create a new input queue for the game
                    # last_input_time already exists from when they connected
                    print(f"[DEBUG] SERVER.PY: promote_spectators_to_players: Promoted {player_id} to player role and assigned new queue.")
                else:
                    print(f"[ERROR] SERVER.PY: promote_spectators_to_players: Promoted client {player_id} not found in clients dict during role update.")
                    # This is a critical issue, ideally shouldn't happen if eligible_clients_ids was correct.
                    # Remove this client from the list of players for the game.
                    if player_id in players_for_game: players_for_game.remove(player_id)


            if len(players_for_game) == 2:
                 promoted = True
                 print(f"[DEBUG] SERVER.PY: promote_spectators_to_players: Successfully promoted {players_for_game[0]} and {players_for_game[1]} to players for the next game.")

                 try:
                    # Inform the new players
                    send_message_to_client(players_for_game[0], f"[SYSTEM] You are {players_for_game[0]} in the new game. Preparing to start...")
                    send_message_to_client(players_for_game[1], f"[SYSTEM] You are {players_for_game[1]} in the new game. Preparing to start...")
                 except Exception as e:
                     print(f"[ERROR] SERVER.PY: promote_spectators_postions: Error informing new players after promotion: {e}")
                     # If we can't message a new player, they are likely disconnected.
                     # The game wrapper will need to handle this if it starts.
                     pass


            else:
                print(f"[DEBUG] SERVER.PY: promote_spectators_to_players: Failed to get exactly two eligible players after processing ({len(players_for_game)} found).")
                # If we promoted less than 2, put the ones we did promote back to spectator role/queue?
                # Or just rely on the game wrapper failing to start with < 2 players.
                # Let's rely on the wrapper for now.
                players_for_game = [] # Reset if not exactly two promoted
                promoted = False


            # Update positions for remaining spectators in the queue
            update_spectator_positions()

        else:
            print(f"[DEBUG] SERVER.PY: promote_spectators_to_players: Not enough eligible clients ({len(eligible_clients_ids)}) to promote.")

        print(f"[DEBUG] SERVER.PY: promote_spectators_to_players: Players for next game: {[p for p in players_for_game]}") # Print the list directly
        print(f"[DEBUG] SERVER.PY: promote_spectators_to_players: Players waiting after promotion attempt: {players_waiting}")
        print(f"[DEBUG] SERVER.PY: promote_spectators_to_players: Spectators waiting after promotion attempt: {spectators_waiting}")

    print(f"[DEBUG] SERVER.PY: promote_spectators_to_players: promote_spectators_to_players finished. Promoted: {promoted}")
    return promoted, players_for_game


def run_game_countdown():
    """Runs the countdown before a game starts."""
    print(f"[DEBUG] SERVER.PY: run_game_countdown: run_game_countdown called.")
    # Ensure clients list is stable during broadcast by taking snapshot
    client_ids_at_countdown_start = []
    with lock:
         client_ids_at_countdown_start = list(clients.keys())

    for i in range(GAME_START_COUNTDOWN, 0, -1):
        message = f"[SYSTEM] New game starting in {i} seconds..."
        # print(f"[DEBUG] SERVER.PY: run_game_countdown: Countdown: {message}") # Too verbose
        # Broadcast to all *currently connected* clients
        broadcast_to_all(message) # broadcast_to_all handles disconnects
        time.sleep(1)
    broadcast_to_all("[SYSTEM] Game is starting now!")
    print(f"[DEBUG] SERVER.PY: run_game_countdown: Countdown finished. Game start message sent.")


def check_start_game():
    """Checks if a new game can be started and initiates it."""
    global game_in_progress, game_thread
    print(f"[DEBUG] SERVER.PY: check_start_game: check_start_game called.")
    with lock:
        if game_in_progress:
            print(f"[DEBUG] SERVER.PY: check_start_game: Game already in progress. Skipping check_start_game.")
            return

        # Try to promote players from the waiting queue
        promoted, players_for_game = promote_spectators_to_players()

        if promoted:
            print(f"[DEBUG] SERVER.PY: check_start_game: Two players ({players_for_game[0]}, {players_for_game[1]}) are ready for a new game.")
            game_in_progress = True
            print(f"[DEBUG] SERVER.PY: check_start_game: game_in_progress set to {game_in_progress}.")

            # Get the client data and input queues for the players
            player1_data = clients.get(players_for_game[0])
            player2_data = clients.get(players_for_game[1])

            # Double check if player data is still valid (e.g., not removed between promote and here)
            if not player1_data or player1_data.get("role") != "player" or not player2_data or player2_data.get("role") != "player":
                 print(f"[ERROR] SERVER.PY: check_start_game: Promoted player data became invalid before starting game. Cannot start game.")
                 game_in_progress = False # Reset flag
                 # Requeue or drop these clients? For now, let remove_client handle it.
                 # Re-check for next game opportunities.
                 check_start_game()
                 return

            # Initialize active_games for reconnection and per-player state
            active_games[player1_data['id']] = {
                "board": None,
                "disconnected": False,
                "reconnect_deadline": None,
                "opponent": player2_data['id'],
            }
            active_games[player2_data['id']] = {
                "board": None,
                "disconnected": False,
                "reconnect_deadline": None,
                "opponent": player1_data['id'],
            }

            print(f"[DEBUG] SERVER.PY: check_start_game: Broadcasting game start.")
            broadcast_to_all("[SYSTEM] A new game is starting!")
            print(f"[DEBUG] SERVER.PY: check_start_game: Broadcasting successful.")

            # Now start the game thread
            print(f"[DEBUG] SERVER.PY: check_start_game: Starting run_game_wrapper thread.")
            game_thread = threading.Thread(
                target=run_game_wrapper,
                args=(player1_data, player2_data),
                daemon=True
            )
            game_thread.start()
            print(f"[DEBUG] SERVER.PY: check_start_game: Game wrapper thread started.")
        else:
            print(f"[DEBUG] SERVER.PY: check_start_game: Not enough eligible clients to start a game. Waiting.")
            # Inform waiting players/spectators if the game just ended and not enough players for next
            # This is handled by run_game_wrapper's cleanup.


def run_game_wrapper(player1_data, player2_data):
    """Wrapper to run the game and handle post-game cleanup."""
    global game_in_progress, game_thread
    print(f"[DEBUG] SERVER.PY: run_game_wrapper: run_game_wrapper started with players {player1_data['id']} and {player2_data['id']}.")

    player_ids_in_game = [player1_data['id'], player2_data['id']]

    # Ensure player roles are correctly set for the duration of the game
    with lock:
        p1_client_data = clients.get(player1_data['id'])
        p2_client_data = clients.get(player2_data['id'])
        if p1_client_data: p1_client_data["role"] = "player"
        if p2_client_data: p2_client_data["role"] = "player"


    try:
        # Run the countdown first
        run_game_countdown()

        # Run the actual game logic
        print(f"[DEBUG] SERVER.PY: run_game_wrapper: Calling run_multiplayer_game...")
        run_multiplayer_game(
            player1_data,
            player2_data,
            player1_data.get("input_queue"), # Pass the input queue for Player 1
            player2_data.get("input_queue"), # Pass the input queue for Player 2
            send_message_to_client, # Pass the server's send function
            broadcast_game_board_state # Pass the server's board broadcast function
        )
        print(f"[DEBUG] SERVER.PY: run_game_wrapper: run_multiplayer_game finished without exception.")

    except PlayerDisconnectedException as e:
         print(f"[GAME INFO] Game ended due to player disconnection: {e}")
         # The handle_client_input thread already called remove_client.
         # Notify remaining player if any.
         disconnected_player_id = None # Need to determine which player disconnected
         if str(e).startswith(player1_data['id']): disconnected_player_id = player1_data['id']
         elif str(e).startswith(player2_data['id']): disconnected_player_id = player2_data['id']

         remaining_player_id = None
         if disconnected_player_id == player1_data['id']: remaining_player_id = player2_data['id']
         elif disconnected_player_id == player2_data['id']: remaining_player_id = player1_data['id']

         if remaining_player_id:
             try:
                 send_message_to_client(remaining_player_id, f"[SYSTEM] Your opponent disconnected. Game ending.")
             except Exception: pass # Ignore errors sending final message

         broadcast_to_all(f"[SYSTEM] The game has ended because a player disconnected.", sender_id=remaining_player_id)


    except PlayerTimeoutException as e:
         print(f"[GAME INFO] Game ended due to player timeout/forfeit: {e}")
         # Game logic already sent forfeit messages, just broadcast general end message.
         broadcast_to_all(f"[SYSTEM] The game has ended because a player timed out/forfeited.")

    except Exception as e:
        print(f"[ERROR] SERVER.PY: run_game_wrapper: Exception caught in run_game_wrapper during game execution: {type(e).__name__}: {e}")
        broadcast_to_all(f"[SYSTEM] The game ended due to an unexpected server error: {type(e).__name__}")
    finally:
        print(f"[DEBUG] SERVER.PY: run_game_wrapper: Game execution finished or errored. Starting cleanup.")
        with lock:
            game_in_progress = False
            game_thread = None # Clear the game thread reference
            print(f"[DEBUG] SERVER.PY: run_game_wrapper: game_in_progress set to {game_in_progress}.")

        time.sleep(1) # Give a moment for final messages/cleanup

        print(f"[DEBUG] SERVER.PY: run_game_wrapper: Recycling players {player_ids_in_game}.")
        recycle_players_to_spectators(player_ids_in_game)
        print(f"[DEBUG] SERVER.PY: run_game_wrapper: Running garbage collection.")
        gc.collect()
        print(f"[DEBUG] SERVER.PY: run_game_wrapper: Broadcasting preparation for next match.")
        broadcast_to_all("[SYSTEM] The current game has ended. Preparing for the next match...")
        print(f"[DEBUG] SERVER.PY: run_game_wrapper: Checking if next game can start.")
        check_start_game() # Check if there are enough players for the next game


def mark_player_disconnected(client_id, active_games):
    """Mark a player as disconnected and start a reconnection timer with countdown messages."""
    global disconnected_players

    print(f"[INFO] Marking player {client_id} as disconnected. Starting reconnection timer.")

    player_data = clients.get(client_id)
    if not player_data:
        print(f"[WARN] Tried to mark unknown player {client_id} as disconnected.")
        return

    opponent_id = active_games.get(client_id, {}).get("opponent")
    opponent_data = clients.get(opponent_id) if opponent_id else None

    # Store in the disconnected_players dict BEFORE starting the thread
    disconnected_players[client_id] = {"player_data": player_data}

    # Optionally, mark in player_data that they're disconnected
    player_data["disconnected"] = True

    if client_id in active_games:
        active_games[client_id]["disconnected"] = True
        active_games[client_id]["reconnect_deadline"] = time.time() + RECONNECT_TIMEOUT

    def countdown_and_remove():
        remaining = RECONNECT_TIMEOUT
        while remaining > 0:
            print(f"\n[DEBUG] SERVER.PY: ----------countdown_and_remove called--------------------") 
            print(f"[DEBUG] SERVER.PY Countdown running for {client_id}: {remaining} seconds left") 
            if client_id not in disconnected_players or not active_games[client_id].get("disconnected", True):
                print(f"[INFO] Countdown stopped: {client_id} has reconnected.")
                return
            try:
                send_message_to_client(client_id, f"[SYSTEM] Reconnect within {remaining} seconds or you will forfeit!")
            except Exception as e:
                print(f"[DEBUG] Countdown send_message_to_client failed for {client_id}: {e}")
            try:
                if opponent_data:
                    send_message_to_client(opponent_id, f"[SYSTEM] Opponent has {remaining} seconds to reconnect or you will win by forfeit.")
            except Exception as e:
                print(f"[DEBUG] Countdown send_message_to_client failed for opponent {opponent_id}: {e}")
            time.sleep(1)
            remaining -= 1
        print(f"[INFO] Player {client_id} did not reconnect in time. Removing from game.")
        broadcast_to_all("[SYSTEM] Game closed due to disconnect/timeout.")
        remove_client(client_id)
        disconnected_players.pop(client_id, None)

    # Start the countdown in a thread AFTER updating state
    timer_thread = threading.Thread(target=countdown_and_remove, daemon=True)
    timer_thread.start()

    # Optionally, store the timer thread if you want to reference it later
    disconnected_players[client_id]["timer"] = timer_thread


def format_board_for_display(board):
    # Returns a string representation of the board's display_grid
    lines = []
    header = "  " + "".join(str(i + 1).rjust(2) for i in range(board.size))
    lines.append(header)
    for r_idx in range(board.size):
        row_label = chr(ord('A') + r_idx)
        row_str = " ".join(board.display_grid[r_idx][c_idx] for c_idx in range(board.size))
        lines.append(f"{row_label:2} {row_str}")
    return "\n".join(lines)

def main():
    """Main function to start the server."""
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    print(f"[DEBUG] SERVER.PY: main: main function started.")
    server_socket = None

    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"[DEBUG] SERVER.PY: main: Socket created.")
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        print(f"[DEBUG] SERVER.PY: main: Socket option SO_REUSEADDR set.")
        server_socket.bind((HOST, PORT))
        print(f"[INFO] Socket bound to {HOST}:{PORT}")
        server_socket.listen()
        print(f"[INFO] Server listening for incoming connections...")

        while True:
            print(f"[DEBUG] SERVER.PY: main: Waiting for a new connection...")
            try:
                conn, addr = server_socket.accept()

                username = get_client_username(conn, addr)
                if not username:
                    conn.close()
                    continue  # Skip to next accept loop iteration
                client_id = username
                with lock:
                    if client_id in disconnected_players:
                        print(f"\n[DEBUG] SERVER.PY: main: -----Reconnection handling for {client_id}-----")
                        game_state = active_games.get(client_id)
                        if game_state and game_state.get("disconnected"):
                            deadline = game_state.get("reconnect_deadline", 0)
                            if time.time() < deadline:
                                print(f"[INFO] {client_id} is reconnecting within allowed window.")

                                # --- CLEAN UP OLD HANDLES ---
                                old_client_data = clients.get(client_id)
                                if old_client_data:
                                    try:
                                        print(f"[DEBUG] SERVER.PY: main: Cleaning up old socket for {client_id}.")
                                        if old_client_data.get("socket"):
                                            old_client_data["socket"].close()
                                    except Exception:
                                        pass

                                # Update reconnection state
                                game_state["disconnected"] = False
                                disconnected_players.pop(client_id, None)

                                # Update client data with new socket
                                clients[client_id]["socket"] = conn

                                # Optionally notify opponent
                                opponent_id = game_state.get("opponent")
                                if opponent_id and opponent_id in active_games:
                                    try:
                                        send_message_to_client(opponent_id, f"[INFO] Player '{client_id}' has reconnected!")
                                        print(f"[DEBUG] SERVER.PY: main: Notifying opponent {opponent_id} of {client_id} reconnection.")
                                    except Exception:
                                        pass

                                # Notify the reconnected player
                                try:
                                    send_message_to_client(client_id, "[SYSTEM] You have reconnected to your game!")
                                    print(f"[DEBUG] SERVER.PY: main: Notifying {client_id} of successful reconnection.")
                                except Exception:
                                    pass

                                # Send the board state
                                board = game_state.get("board")
                                if board:
                                    send_message_to_client(client_id, "Here is your current board state:")
                                    send_message_to_client(client_id, format_board_for_display(board))
                                # --- ONLY SEND THE APPROPRIATE MESSAGE BASED ON TURN ---
                                if game_state.get("is_current_turn"):
                                    try:
                                        board = game_state.get("board")
                                        if board:
                                            send_message_to_client(client_id, "Here is your current board state:")
                                            send_message_to_client(client_id, format_board_for_display(board))
                                        send_message_to_client(client_id, "\n--- It's your turn! ---")
                                        send_message_to_client(client_id, "[SYSTEM] Your view of the opponent's board:")
                                        opponent_id = game_state.get("opponent")
                                        if opponent_id and opponent_id in active_games:
                                            opponent_board = active_games[opponent_id]["board"]
                                            send_message_to_client(client_id, format_board_for_display(opponent_board))
                                        send_message_to_client(client_id, "[SYSTEM] Please enter your move (e.g., A1):")
                                        print(f"[DEBUG] SERVER.PY: main: Re-sent turn prompt to {client_id} after reconnection.")
                                    except Exception as e:
                                        print(f"[ERROR] SERVER.PY: main: Failed to re-send turn prompt to {client_id}: {e}")
                                else:
                                    board = game_state.get("board")
                                    if board:
                                        send_message_to_client(client_id, "Here is your current board state:")
                                        send_message_to_client(client_id, format_board_for_display(board))
                                    send_message_to_client(client_id, "[SYSTEM] Please wait for your turn or continue playing.")

                                # --- THIS IS CRUCIAL: restart input handler thread ---
                                threading.Thread(target=handle_client_input, args=(client_id,), daemon=True).start()
                                print(f"[DEBUG] SERVER.PY: main: Restarting handle_client_input thread for {client_id} after reconnection.")

                                # Broadcast the updated board state to spectators
                                if game_state.get("board"):
                                    print(f"[DEBUG] SERVER.PY: main: Broadcasting board state to spectators after {client_id} reconnected.")
                                    broadcast_game_board_state(game_state["board"], game_state["board"]) # Both players' boards are the same for reconnection

                                continue  # Skip to next accept loop iteration
                            else:
                                print(f"[INFO] {client_id} tried to reconnect but missed the deadline.")
                                try:
                                    send_message_to_client(client_id, "Reconnect window expired. You have forfeited your game.")
                                except Exception:
                                    pass
                                conn.close()
                                continue


                with lock:
                    # --- Connection Limit Check ---
                    if len(clients) >= MAX_CONNECTIONS:
                        print(f"[INFO] Connection from {addr} refused. Max connections ({MAX_CONNECTIONS}) reached.")
                        try:
                            temp_wfile = conn.makefile('w')
                            temp_wfile.write(f"[SYSTEM] Connection refused: Maximum connections ({MAX_CONNECTIONS}) reached. Please try again later.\n")
                            temp_wfile.flush()
                            temp_wfile.close()
                        except Exception as e:
                            print(f"[ERROR] SERVER.PY: main: Error sending refusal message to {addr}: {e}")
                        finally:
                            conn.close()
                        continue

                    # --- Username uniqueness check ---
                    if username in clients:
                        print(f"[INFO] SERVER.PY: main: Username '{username}' already in use. Refusing connection from {addr}.")
                        try:
                            # Use packet-based message instead of wfile
                            packet = pack_packet(0, SYSTEM_MESSAGE, b"Username already in use. Please reconnect with a different name.")
                            conn.sendall(packet)
                        except Exception:
                            pass
                        conn.close()
                        continue

                    client_id = username  # Use username as client_id
                with lock:
                    # --- Connection Limit Check ---
                    if len(clients) >= MAX_CONNECTIONS:
                        print(f"[INFO] Connection from {addr} refused. Max connections ({MAX_CONNECTIONS}) reached.")
                        try:
                            # Attempt to send a message before closing
                            temp_wfile = conn.makefile('w')
                            temp_wfile.write(f"[SYSTEM] Connection refused: Maximum connections ({MAX_CONNECTIONS}) reached. Please try again later.\n")
                            temp_wfile.flush()
                            temp_wfile.close()
                        except Exception as e:
                            print(f"[ERROR] SERVER.PY: main: Error sending refusal message to {addr}: {e}")
                        finally:
                            conn.close() # Ensure the socket is closed
                        continue # Skip to the next accept loop iteration

                print(f"[INFO] Connection established with {addr}, assigned ID {client_id}")
                print(f"[DEBUG] SERVER.PY: main: Accepted connection. Setting up client data.")

                with lock:
                    # Determine role (player or spectator)
                    role = "spectator" # Default to spectator
                    if len(players_waiting) < 2 and not game_in_progress:
                        role = "player"
                        players_waiting.append(client_id)
                        print(f"[DEBUG] SERVER.PY: main: {client_id} added to players_waiting.")
                        # Input queue for players is created when they are promoted to a game

                    else:
                        spectators_waiting.append(client_id)
                        print(f"[DEBUG] SERVER.PY: main: {client_id} added to spectators_waiting.")

                    clients[client_id] = {
                        "socket": conn,
                        "addr": addr,
                        "id": client_id,
                        "role": role,
                        "input_queue": None,
                        "last_input_time": time.time()
                    }   
                    print(f"[DEBUG] SERVER.PY: main: Client data stored for {client_id} with role {role}. Total clients: {len(clients)}")


                # Start a dedicated thread to handle input from this client
                threading.Thread(target=handle_client_input, args=(client_id,), daemon=True).start()
                print(f"[DEBUG] SERVER.PY: main: handle_client_input thread started for {client_id}")

                # Send initial welcome message
                welcome_message = f"[SYSTEM] Welcome! Your ID is {client_id}.\n"
                with lock: # Access waiting lists under lock for accurate position
                    if role == "player":
                         position_in_queue = players_waiting.index(client_id) + 1 if client_id in players_waiting else -1 # Should be in list
                         if position_in_queue != -1:
                             welcome_message += f"[SYSTEM] You are #{position_in_queue} in the player queue.\n"
                         welcome_message += f"[SYSTEM] Waiting for another player to join...\n"
                    else: # Spectator
                         # Find position in the combined queue for initial message
                         combined_queue = players_waiting + spectators_waiting
                         position = -1
                         try:
                             position = combined_queue.index(client_id) + 1
                         except ValueError: # Should not happen
                              pass # Keep position as -1

                         if position != -1:
                            welcome_message += f"[SYSTEM] You are Spectator #{position} in the queue.\n"
                            if game_in_progress:
                                welcome_message += "[SYSTEM] A game is currently in progress. You will receive updates.\n"
                            else:
                                welcome_message += "[SYSTEM] Waiting for players to start a new game.\n"

                send_message_to_client(client_id, welcome_message)
                send_message_to_client(client_id, "[SYSTEM] Type /help for available commands.")


                # Check if a new game can start after a new client connects
                check_start_game()


            except KeyboardInterrupt:
                print(f"[INFO] Server shutting down due to KeyboardInterrupt.")
                break # Exit the loop on Ctrl+C
            except Exception as e:
                print(f"[ERROR] SERVER.PY: main: Error accepting connection: {e}")
                # Continue listening even if one connection fails

    except Exception as e:
        print(f"[CRITICAL ERROR] Server failed to start or run: {e}")
    finally:
        print(f"[INFO] Server main loop ended. Shutting down.")
        if server_socket:
            server_socket.close()
            print("[INFO] Server socket closed.")

        # Attempt to clean up all client connections
        client_ids_to_close = []
        with lock:
             client_ids_to_close = list(clients.keys())
        for client_id in client_ids_to_close:
            print(f"[INFO] Cleaning up resources for client {client_id} during shutdown.")
            remove_client(client_id) # This handles closing files and socket

        print(f"[INFO] Server has shut down.")

if __name__ == "__main__":
    print(f"[DEBUG] SERVER.PY: <module>: Script started. Calling main().")
    main()
    print(f"[DEBUG] SERVER.PY: <module>: main() finished.")