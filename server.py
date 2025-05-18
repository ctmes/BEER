# server.py

import socket
import threading
import time
import gc
import queue
from battleship import Board, parse_coordinate, SHIPS, BOARD_SIZE, run_multiplayer_game, PlayerDisconnectedException, PlayerTimeoutException

HOST = '127.0.0.1'
PORT = 5001

# Global server state
clients = {}
players_waiting = []
spectators_waiting = []
game_in_progress = False
game_thread = None
lock = threading.RLock()

GAME_START_COUNTDOWN = 5

MAX_CONNECTIONS = 6
INPUT_RATE_LIMIT_PER_SECOND = 2
INPUT_RATE_DELAY = 1.0 / INPUT_RATE_LIMIT_PER_SECOND

print(f"[DEBUG] Initializing server with HOST: {HOST}, PORT: {PORT}")


def send_message_to_client(client_id, message):
    """
    TIER 1.4 SIMPLE CLIENT/SERVER MESSAGE EXCHANGE, TIER 1.5 NO DISCONNECTION HANDLING / TIER 2.4 DISCONNECTION HANDLING -
    Safely sends a message to a client, handling potential disconnection errors during the send operation.

    Args:
        client_id (str): The ID of the client to send the message to.
        message (str): The message string to send.
    """
    with lock:
        client_data = clients.get(client_id)
        if client_data and client_data.get("w") and not client_data["w"].closed:
            try:
                client_data["w"].write(message + '\n')
                client_data["w"].flush()
            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                print(f"[INFO] Client {client_id} disconnected during send: {e}")
                remove_client(client_id)
            except Exception as e:
                 print(f"[ERROR] Unexpected error sending to {client_id}: {e}")
                 remove_client(client_id)


def broadcast_to_all(message, sender_id=None):
    """
    TIER 4.2 INSTANT MESSAGING (IM) CHANNEL - Broadcasts a message to all connected clients except the sender.

    Args:
        message (str): The message string to broadcast.
        sender_id (str, optional): The ID of the client who sent the message (to exclude them from broadcast). Defaults to None.
    """
    client_ids_to_send = []
    with lock:
        client_ids_to_send = list(clients.keys())

    for client_id in client_ids_to_send:
        if client_id != sender_id:
            send_message_to_client(client_id, message)


def broadcast_game_board_state(player1_board, player2_board):
    """
    TIER 3.2 SPECTATOR EXPERIENCE - Sends the current public board state (opponent's view) to all spectators in a formatted way.

    Args:
        player1_board (Board): The board object for Player 1.
        player2_board (Board): The board object for Player 2.
    """
    board_message = "GRID\n"
    board_message += "PLAYER 1                  PLAYER 2\n"
    separator_len = (BOARD_SIZE * 2) + 2 + len("    |    ") + (BOARD_SIZE * 2) + 2
    board_message += "-" * (separator_len if separator_len > 0 else 40) + "\n"

    p1_grid = player1_board.display_grid
    p2_grid = player2_board.display_grid

    for r_idx in range(BOARD_SIZE):
        row_label = chr(ord('A') + r_idx)

        row_p1 = " ".join(p1_grid[r_idx][c_idx] for c_idx in range(BOARD_SIZE))
        row_p2 = " ".join(p2_grid[r_idx][c_idx] for c_idx in range(BOARD_SIZE))

        board_message += f"{row_label:2} {row_p1}    |    {row_label:2} {row_p2}\n"
    board_message += "\n"

    with lock:
        spectator_ids = [cid for cid, data in clients.items() if data.get("role") == "spectator"]

    for spec_id in spectator_ids:
         send_message_to_client(spec_id, board_message)


def handle_command(client_id, command):
    """
    TIER 1.4 SIMPLE CLIENT/SERVER MESSAGE EXCHANGE, TIER 2.1 EXTENDED INPUT VALIDATION, TIER 4.2 INSTANT MESSAGING (IM) CHANNEL -
    Handles commands received from clients (e.g., /help, /quit, /chat, /status), processing valid commands and informing about unknown ones.

    Args:
        client_id (str): The ID of the client who sent the command.
        command (str): The command string.
    """
    command_parts = command.lower().strip().split(maxsplit=1)
    cmd = command_parts[0]
    args = command_parts[1] if len(command_parts) > 1 else ""
    print(f"[DEBUG] {client_id} issued command: {command}")

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
        else:
             help_text = "Available commands: /help, /quit (You are in a transitional state)"

        send_message_to_client(client_id, f"[SYSTEM] {help_text}")

    elif cmd == "/status":
        """
        TIER 2.4 DISCONNECTION HANDLING - Provides the client with their current status and queue position if they are a spectator.
        """
        if client_role == "player":
            with lock:
                if game_in_progress:
                    send_message_to_client(client_id, "[SYSTEM] You are currently playing a game.")
                else:
                    send_message_to_client(client_id, "[SYSTEM] You are registered as a player. Waiting for the game to start.")
        elif client_role == "spectator":
            with lock:
                try:
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
                            games_to_wait = (remaining_in_queue + 1) // 2
                            if games_to_wait == 0:
                                 send_message_to_client(client_id, "[SYSTEM] You will play in the next game!")
                            else:
                                 send_message_to_client(client_id, f"[SYSTEM] You will need to wait for approximately {games_to_wait} more game(s).")
                        else:
                            estimated_games_in_queue = (len(players_waiting) + len(spectators_waiting) + 1) // 2
                            games_to_wait = max(0, estimated_games_in_queue - (position + 1) // 2)

                            if position <= 2:
                                send_message_to_client(client_id, "[SYSTEM] You are next in line for the game!")
                            else:
                                games_to_wait_further = (position - (len(players_waiting) + 1)) // 2 + 1 if len(players_waiting) < 2 else (position - 3) // 2 + 1
                                send_message_to_client(client_id, f"[SYSTEM] Waiting for enough players. You are #{position} in queue.")


                    else:
                         send_message_to_client(client_id, "[SYSTEM] Could not determine your position in the queue.")
                except Exception as e:
                    print(f"[ERROR] Error sending status to spectator {client_id}: {e}")


    elif cmd == "/quit":
        send_message_to_client(client_id, "[SYSTEM] You have chosen to quit. Disconnecting.")
        pass

    elif cmd == "/chat":
         if args:
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
    """
    TIER 1.1 CONCURRENCY ISSUES, TIER 1.4 SIMPLE CLIENT/SERVER MESSAGE EXCHANGE,
    TIER 1.5 NO DISCONNECTION HANDLING / TIER 2.4 DISCONNECTION HANDLING,
    TIER 2.1 EXTENDED INPUT VALIDATION, TIER 3.1 MULTIPLE CONCURRENT CONNECTIONS,
    TIER 3.2 SPECTATOR EXPERIENCE, TIER 4.4 SECURITY FLAWS & MITIGATIONS -
    Thread function to continuously read input from a client, process commands, game input, and chat messages,
    handle disconnections, and enforce input rate limiting.

    Args:
        client_id (str): The ID of the client whose input is being handled.
    """
    print(f"[DEBUG] handle_client_input thread started for {client_id}")
    rfile = None

    with lock:
        client_data = clients.get(client_id)
        if client_data:
            rfile = client_data["r"]
        else:
            print(f"[ERROR] handle_client_input started for unknown client_id {client_id}")
            return

    try:
        while True:
            line = rfile.readline()
            if not line:
                print(f"[INFO] Client {client_id} disconnected (readline returned empty).")
                break

            line = line.strip()
            if not line:
                continue

            print(f"[DEBUG] Received from {client_id}: '{line}'")

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
        print(f"[ERROR] Error in handle_client_input for {client_id}: {e}")
    finally:
        print(f"[DEBUG] handle_client_input thread for {client_id} ending. Ensuring client removal.")
        remove_client(client_id)
        print(f"[DEBUG] Client input thread for {client_id} finished.")

def remove_client(client_id):
    """
    TIER 1.5 NO DISCONNECTION HANDLING / TIER 2.4 DISCONNECTION HANDLING -
    Removes a client from the server state, cleans up resources, and updates spectator positions.

    Args:
        client_id (str): The ID of the client to remove.
    """
    global clients, players_waiting, spectators_waiting, game_in_progress, game_thread
    print(f"[DEBUG] Attempting to remove client {client_id}")

    client_data = None
    client_was_player_in_game = False
    game_player_ids = []

    with lock:
        client_data = clients.pop(client_id, None)
        if client_data:
            print(f"[INFO] Removed client {client_id} from clients dictionary.")
            if client_id in players_waiting:
                players_waiting.remove(client_id)
                print(f"[DEBUG] Removed {client_id} from players_waiting.")
            if client_id in spectators_waiting:
                spectators_waiting.remove(client_id)
                print(f"[DEBUG] Removed {client_id} from spectators_waiting.")

        else:
            print(f"[DEBUG] Client {client_id} not found in clients dictionary during removal attempt.")


    if client_data:
        sock = client_data.get("socket")
        if client_data.get("r") and not client_data["r"].closed:
            try: client_data["r"].close()
            except: pass
        if client_data.get("w") and not client_data["w"].closed:
            try: client_data["w"].close()
            except: pass
        if sock:
            try: sock.close()
            except: pass


    with lock:
        print(f"[DEBUG] Client removal occurred. Updating spectator positions.")
        update_spectator_positions()

    print(f"[DEBUG] remove_client finished for {client_id}")
    check_start_game()


def update_spectator_positions():
    """
    TIER 2.4 DISCONNECTION HANDLING / TIER 3.2 SPECTATOR EXPERIENCE -
    Informs spectators about their updated position in the queue.
    """
    print(f"[DEBUG] update_spectator_positions called.")
    with lock:
        current_queue = players_waiting + spectators_waiting

        messages_to_send = []

        for i, client_id in enumerate(current_queue):
            position = i + 1
            client_data = clients.get(client_id)
            if client_data:
                try:
                    message = f"[SYSTEM] Queue update: You are now #{position} in line."
                    if position <= 2 and not game_in_progress:
                         message += " Preparing for your game soon..."
                    messages_to_send.append((client_id, message))

                except Exception as e:
                    print(f"[ERROR] Error preparing position update for {client_id}: {e}")

        for client_id, message in messages_to_send:
             send_message_to_client(client_id, message)

    print(f"[DEBUG] update_spectator_positions finished.")


def recycle_players_to_spectators(game_player_ids):
    """
    TIER 2.2 SUPPORT MULTIPLE GAMES / TIER 3.4 TRANSITION TO NEXT MATCH -
    Moves players from the just-finished game back to the spectator queue, if they are still connected.

    Args:
        game_player_ids (list): A list of client IDs that were playing in the finished game.
    """
    global players_waiting, spectators_waiting, clients
    print(f"[DEBUG] Recycling players {game_player_ids} to spectators called.")
    with lock:
        recycled_count = 0
        for player_id in game_player_ids:
            client_data = clients.get(player_id)
            if client_data and client_data.get("role") == "player":
                if client_data.get("w") and not client_data["w"].closed:
                    try:
                        send_message_to_client(player_id, "[SYSTEM] Game has ended. You are being returned to the spectator queue.")
                        client_data["role"] = "spectator"
                        client_data.pop("input_queue", None)
                        spectators_waiting.append(player_id)
                        recycled_count += 1
                        print(f"[INFO] Recycled {player_id} to spectators queue.")
                    except Exception as e:
                        print(f"[INFO] Player {player_id} connection issue during recycling: {e}. Not recycling to queue.")
                        remove_client(player_id)
                else:
                    print(f"[INFO] Player {player_id} already disconnected. Not recycling.")

        print(f"[DEBUG] {recycled_count} players recycled.")
        print(f"[DEBUG] Players waiting after recycling: {players_waiting}")
        print(f"[DEBUG] Spectators waiting after recycling: {spectators_waiting}")
        update_spectator_positions()
    print(f"[DEBUG] recycle_players_to_spectators finished.")


def promote_spectators_to_players():
    """
    TIER 1.2 SERVER AND TWO CLIENTS, TIER 2.2 SUPPORT MULTIPLE GAMES / TIER 3.4 TRANSITION TO NEXT MATCH, TIER 3.1 MULTIPLE CONCURRENT CONNECTIONS -
    Promotes the first two eligible clients from the combined waiting queue to players for a new game, updating their roles and creating input queues.

    Returns:
        tuple: A tuple containing a boolean (True if two players were promoted, False otherwise)
               and a list of the client IDs of the promoted players.
    """
    print(f"[DEBUG] promote_spectators_to_players called.")
    promoted = False
    players_for_game = []

    with lock:
        combined_queue = players_waiting + spectators_waiting
        eligible_clients_ids = [cid for cid in combined_queue if cid in clients and clients[cid].get("w") and not clients[cid]["w"].closed]

        print(f"[DEBUG] Eligible clients in queue: {eligible_clients_ids}")

        if len(eligible_clients_ids) >= 2:
            print(f"[DEBUG] Enough eligible clients ({len(eligible_clients_ids)}) to promote two.")
            players_for_game = eligible_clients_ids[:2]

            for player_id in players_for_game:
                if player_id in players_waiting:
                    players_waiting.remove(player_id)
                elif player_id in spectators_waiting:
                    spectators_waiting.remove(player_id)

                client_data = clients.get(player_id)
                if client_data:
                    client_data["role"] = "player"
                    client_data["input_queue"] = queue.Queue()
                    print(f"[DEBUG] Promoted {player_id} to player role and assigned new queue.")
                else:
                    print(f"[ERROR] Promoted client {player_id} not found in clients dict during role update.")
                    if player_id in players_for_game: players_for_game.remove(player_id)


            if len(players_for_game) == 2:
                 promoted = True
                 print(f"[DEBUG] Successfully promoted {players_for_game[0]} and {players_for_game[1]} to players for the next game.")

                 try:
                    send_message_to_client(players_for_game[0], "[SYSTEM] You are Player 1 in the new game. Preparing to start...")
                    send_message_to_client(players_for_game[1], "[SYSTEM] You are Player 2 in the new game. Preparing to start...")
                 except Exception as e:
                     print(f"[ERROR] Error informing new players after promotion: {e}")
                     pass


            else:
                print(f"[DEBUG] Failed to get exactly two eligible players after processing ({len(players_for_game)} found).")
                players_for_game = []
                promoted = False

            update_spectator_positions()

        else:
            print(f"[DEBUG] Not enough eligible clients to start a game. Waiting.")

        print(f"[DEBUG] Players for next game: {[p for p in players_for_game]}")
        print(f"[DEBUG] Players waiting after promotion attempt: {players_waiting}")
        print(f"[DEBUG] Spectators waiting after promotion attempt: {spectators_waiting}")

    print(f"[DEBUG] promote_spectators_to_players finished. Promoted: {promoted}")
    return promoted, players_for_game


def run_game_countdown():
    """
    TIER 2.2 SUPPORT MULTIPLE GAMES / TIER 3.4 TRANSITION TO NEXT MATCH -
    Runs the countdown before a game starts, broadcasting the countdown to all clients.
    """
    print(f"[DEBUG] run_game_countdown called.")
    client_ids_at_countdown_start = []
    with lock:
         client_ids_at_countdown_start = list(clients.keys())

    for i in range(GAME_START_COUNTDOWN, 0, -1):
        message = f"[SYSTEM] New game starting in {i} seconds..."
        broadcast_to_all(message)
        time.sleep(1)
    broadcast_to_all("[SYSTEM] Game is starting now!")
    print(f"[DEBUG] Countdown finished. Game start message sent.")


def check_start_game():
    """
    TIER 1.2 SERVER AND TWO CLIENTS, TIER 2.2 SUPPORT MULTIPLE GAMES / TIER 3.4 TRANSITION TO NEXT MATCH -
    Checks if a new game can be started based on the waiting queues and initiates it if possible by promoting players and starting the game wrapper thread.
    """
    global game_in_progress, game_thread
    print(f"[DEBUG] check_start_game called.")
    with lock:
        if game_in_progress:
            print(f"[DEBUG] Game already in progress. Skipping check_start_game.")
            return

        promoted, players_for_game = promote_spectators_to_players()

        if promoted:
            print(f"[DEBUG] Two players ({players_for_game[0]}, {players_for_game[1]}) are ready for a new game.")
            game_in_progress = True
            print(f"[DEBUG] game_in_progress set to {game_in_progress}.")

            player1_data = clients.get(players_for_game[0])
            player2_data = clients.get(players_for_game[1])

            if not player1_data or player1_data.get("role") != "player" or not player2_data or player2_data.get("role") != "player":
                 print(f"[ERROR] Promoted player data became invalid before starting game. Cannot start game.")
                 game_in_progress = False
                 check_start_game()
                 return

            print(f"[DEBUG] Broadcasting game start.")
            broadcast_to_all("[SYSTEM] A new game is starting!")
            print(f"[DEBUG] Broadcasting successful.")

            print(f"[DEBUG] Starting run_game_wrapper thread.")
            game_thread = threading.Thread(
                target=run_game_wrapper,
                args=(player1_data, player2_data),
                daemon=True
            )
            game_thread.start()
            print(f"[DEBUG] Game wrapper thread started.")
        else:
            print(f"[DEBUG] Not enough eligible clients to start a game. Waiting.")


def run_game_wrapper(player1_data, player2_data):
    """
    TIER 2.2 SUPPORT MULTIPLE GAMES / TIER 3.4 TRANSITION TO NEXT MATCH, TIER 1.5 NO DISCONNECTION HANDLING / TIER 2.4 DISCONNECTION HANDLING -
    Wrapper thread to run the game logic and handle post-game cleanup, including recycling players and checking for the next game, and catching exceptions to gracefully end the game.

    Args:
        player1_data (dict): Data for Player 1.
        player2_data (dict): Data for Player 2.
    """
    print(f"[DEBUG] run_game_wrapper started with players {player1_data['id']} and {player2_data['id']}.")

    player_ids_in_game = [player1_data['id'], player2_data['id']]

    with lock:
        p1_client_data = clients.get(player1_data['id'])
        p2_client_data = clients.get(player2_data['id'])
        if p1_client_data: p1_client_data["role"] = "player"
        if p2_client_data: p2_client_data["role"] = "player"


    try:
        run_game_countdown()

        print(f"[DEBUG] Calling run_multiplayer_game...")
        run_multiplayer_game(
            player1_data,
            player2_data,
            player1_data.get("input_queue"),
            player2_data.get("input_queue"),
            send_message_to_client,
            broadcast_game_board_state
        )
        print(f"[DEBUG] run_multiplayer_game finished without exception.")

    except PlayerDisconnectedException as e:
         print(f"[GAME INFO] Game ended due to player disconnection: {e}")
         disconnected_player_id = None
         if str(e).startswith(player1_data['id']): disconnected_player_id = player1_data['id']
         elif str(e).startswith(player2_data['id']): disconnected_player_id = player2_data['id']

         remaining_player_id = None
         if disconnected_player_id == player1_data['id']: remaining_player_id = player2_data['id']
         elif disconnected_player_id == player2_data['id']: remaining_player_id = player1_data['id']

         if remaining_player_id:
             try:
                 send_message_to_client(remaining_player_id, f"[SYSTEM] Your opponent disconnected. Game ending.")
             except Exception: pass

         broadcast_to_all(f"[SYSTEM] The game has ended because a player disconnected.", sender_id=remaining_player_id)


    except PlayerTimeoutException as e:
         print(f"[GAME INFO] Game ended due to player timeout/forfeit: {e}")
         broadcast_to_all(f"[SYSTEM] The game has ended because a player timed out/forfeited.")

    except Exception as e:
        print(f"[ERROR] Exception caught in run_game_wrapper during game execution: {type(e).__name__}: {e}")
        broadcast_to_all(f"[SYSTEM] The game ended due to an unexpected server error: {type(e).__name__}")
    finally:
        print(f"[DEBUG] Game execution finished or errored. Starting cleanup.")
        with lock:
            game_in_progress = False
            game_thread = None
            print(f"[DEBUG] game_in_progress set to {game_in_progress}.")

        time.sleep(1)

        print(f"[DEBUG] Recycling players {player_ids_in_game}.")
        recycle_players_to_spectators(player_ids_in_game)
        print(f"[DEBUG] Running garbage collection.")
        gc.collect()
        broadcast_to_all("[SYSTEM] The current game has ended. Preparing for the next match...")

        print(f"[DEBUG] Checking if next game can start.")
        check_start_game()


def main():
    """
    TIER 1.1 CONCURRENCY ISSUES, TIER 1.2 SERVER AND TWO CLIENTS,
    TIER 2.4 DISCONNECTION HANDLING, TIER 3.1 MULTIPLE CONCURRENT CONNECTIONS,
    TIER 4.4 SECURITY FLAWS & MITIGATIONS -
    Main function to set up the server socket, accept connections,
    manage connection limits, assign roles (player/spectator),
    and start threads for each client to handle their input.
    Also triggers checks for starting new games.
    """
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    print(f"[DEBUG] main function started.")
    server_socket = None

    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"[DEBUG] Socket created.")
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        print(f"[DEBUG] Socket option SO_REUSEADDR set.")
        server_socket.bind((HOST, PORT))
        print(f"[INFO] Socket bound to {HOST}:{PORT}")
        server_socket.listen()
        print(f"[INFO] Server listening for incoming connections...")

        while True:
            print(f"[DEBUG] Waiting for a new connection...")
            try:
                conn, addr = server_socket.accept()


                with lock:
                    if len(clients) >= MAX_CONNECTIONS:
                        print(f"[INFO] Connection from {addr} refused. Max connections ({MAX_CONNECTIONS}) reached.")
                        try:
                            temp_wfile = conn.makefile('w')
                            temp_wfile.write(f"[SYSTEM] Connection refused: Maximum connections ({MAX_CONNECTIONS}) reached. Please try again later.\n")
                            temp_wfile.flush()
                            temp_wfile.close()
                        except Exception as e:
                            print(f"[ERROR] Error sending refusal message to {addr}: {e}")
                        finally:
                            conn.close()
                        continue


                client_id = f"Client-{addr[0]}:{addr[1]}-{time.time()}"
                print(f"[INFO] Connection established with {addr}, assigned ID {client_id}")
                print(f"[DEBUG] Accepted connection. Setting up client data.")

                rfile = conn.makefile('r')
                wfile = conn.makefile('w')

                with lock:
                    role = "spectator"
                    if len(players_waiting) < 2 and not game_in_progress:
                        role = "player"
                        players_waiting.append(client_id)
                        print(f"[DEBUG] {client_id} added to players_waiting.")

                    else:
                        spectators_waiting.append(client_id)
                        print(f"[DEBUG] {client_id} added to spectators_waiting.")

                    clients[client_id] = {
                        "r": rfile,
                        "w": wfile,
                        "socket": conn,
                        "addr": addr,
                        "id": client_id,
                        "role": role,
                        "input_queue": None,
                        "last_input_time": time.time()
                    }
                    print(f"[DEBUG] Client data stored for {client_id} with role {role}. Total clients: {len(clients)}")


                threading.Thread(target=handle_client_input, args=(client_id,), daemon=True).start()
                print(f"[DEBUG] handle_client_input thread started for {client_id}")

                welcome_message = f"[SYSTEM] Welcome! Your ID is {client_id}.\n"
                with lock:
                    if role == "player":
                         position_in_queue = players_waiting.index(client_id) + 1 if client_id in players_waiting else -1
                         if position_in_queue != -1:
                             welcome_message += f"[SYSTEM] You are #{position_in_queue} in the player queue.\n"
                         welcome_message += f"[SYSTEM] Waiting for another player to join...\n"
                    else:
                         combined_queue = players_waiting + spectators_waiting
                         position = -1
                         try:
                             position = combined_queue.index(client_id) + 1
                         except ValueError:
                              pass

                         if position != -1:
                            welcome_message += f"[SYSTEM] You are Spectator #{position} in the queue.\n"
                            if game_in_progress:
                                welcome_message += "[SYSTEM] A game is currently in progress. You will receive updates.\n"
                            else:
                                welcome_message += "[SYSTEM] Waiting for players to start a new game.\n"

                send_message_to_client(client_id, welcome_message)
                send_message_to_client(client_id, "[SYSTEM] Type /help for available commands.")

                check_start_game()


            except KeyboardInterrupt:
                print(f"[INFO] Server shutting down due to KeyboardInterrupt.")
                break
            except Exception as e:
                print(f"[ERROR] Error accepting connection: {e}")

    except Exception as e:
        print(f"[CRITICAL ERROR] Server failed to start or run: {e}")
    finally:
        print(f"[INFO] Server main loop ended. Shutting down.")
        if server_socket:
            server_socket.close()
            print("[INFO] Server socket closed.")

        client_ids_to_close = []
        with lock:
             client_ids_to_close = list(clients.keys())
        for client_id in client_ids_to_close:
            print(f"[INFO] Cleaning up resources for client {client_id} during shutdown.")
            remove_client(client_id)

        print(f"[INFO] Server has shut down.")


if __name__ == "__main__":
    print(f"[DEBUG] Script started. Calling main().")
    main()
    print(f"[DEBUG] main() finished.")