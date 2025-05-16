# server.py

import socket
import threading
import time
import gc
from battleship import Board, parse_coordinate, SHIPS, BOARD_SIZE, run_multiplayer_game

HOST = '127.0.0.1'
PORT = 5001

players = []
spectators = []
lock = threading.RLock()
game_in_progress = False
GAME_START_COUNTDOWN = 5  # seconds

print(f"[DEBUG] Initializing server with HOST: {HOST}, PORT: {PORT}")
print(f"[DEBUG] Initial state: players={players}, spectators={spectators}, game_in_progress={game_in_progress}")


def handle_client(conn, addr):
    """Handles a new client connection."""
    global players, spectators, game_in_progress
    rfile = conn.makefile('r')
    wfile = conn.makefile('w')

    client_id = f"Client-{addr[0]}:{addr[1]}"
    print(f"[INFO] New connection from {client_id}")
    print(f"[DEBUG] handle_client started for {client_id}")

    print(f"[DEBUG] Acquiring lock in handle_client for {client_id}")
    with lock:
        print(f"[DEBUG] Lock acquired in handle_client for {client_id}")
        print(f"[DEBUG] Current state in handle_client: len(players)={len(players)}, game_in_progress={game_in_progress}")

        if len(players) < 2 and not game_in_progress:
            print(f"[DEBUG] {client_id} is eligible to be a player.")
            player_num = len(players) + 1
            player_data = {"r": rfile, "w": wfile, "addr": addr, "id": client_id}
            players.append(player_data)
            print(f"[DEBUG] Added {client_id} to players list. Current players: {[p['id'] for p in players]}")
            player_role = f"Player {player_num}"
            try:
                print(f"[DEBUG] Attempting to write welcome message to {client_id}")
                wfile.write(f"Welcome! You are {player_role}.\n")
                if player_num == 1:
                    print(f"[DEBUG] {client_id} is Player 1, waiting for Player 2.")
                    wfile.write("Waiting for another player to join...\n")
                wfile.flush()
                print(f"[DEBUG] Welcome message sent to {client_id}")
            except Exception as e:
                print(f"[INFO] {client_id} disconnected during initial message sending: {e}")
                print(f"[DEBUG] Removing {client_id} due to disconnection.")
                # conn.close() # Close outside the lock
                # return # Return outside the lock
                pass # Handle removal after releasing lock if needed, or rely on later checks

            if len(players) == 2:
                print(f"[DEBUG] Two players are now connected. Initiating game start process.")
                # start_new_game() # Called outside the lock to avoid deadlock
            else:
                print(f"[DEBUG] Waiting for another player. Current players: {len(players)}")

        else:
            print(f"[DEBUG] {client_id} is not eligible to be a player. Adding as spectator.")
            spectator_data = {"r": rfile, "w": wfile, "addr": addr, "id": client_id}
            spectators.append(spectator_data)
            print(f"[DEBUG] Added {client_id} to spectators list. Current spectators: {[s['id'] for s in spectators]}")
            try:
                position = len(spectators)
                print(f"[DEBUG] Attempting to write welcome message to spectator {client_id}")
                wfile.write(f"Welcome! You are Spectator #{position} in the waiting queue.\n")
                if game_in_progress:
                    print(f"[DEBUG] Game is in progress. Informing spectator {client_id}.")
                    wfile.write("A game is currently in progress. You will receive updates about the game.\n")
                    if position <= 2:
                        print(f"[DEBUG] Spectator {client_id} (pos {position}) is in line for the next game.")
                        wfile.write(f"You will be Player {position} in the next game!\n")
                    else:
                        games_to_wait = (position - 1) // 2
                        print(f"[DEBUG] Spectator {client_id} (pos {position}) has ~{games_to_wait} games to wait.")
                        wfile.write(f"You will need to wait for approximately {games_to_wait} game(s) before playing.\n")
                else:
                    print(f"[DEBUG] No game in progress. Informing spectator {client_id}.")
                    if position <= 2:
                        print(f"[DEBUG] Spectator {client_id} (pos {position}) will play in the next game.")
                        wfile.write("The next game is about to start. Preparing players...\n")
                wfile.flush()
                print(f"[DEBUG] Welcome message sent to spectator {client_id}")
                print(f"[DEBUG] Starting spectator input thread for {client_id}")
                threading.Thread(target=handle_spectator_input, args=(spectator_data,), daemon=True).start()
            except Exception as e:
                print(f"[INFO] Spectator {client_id} disconnected during initial message sending: {e}")
                print(f"[DEBUG] Removing spectator {client_id} due to disconnection.")
                # remove_player_or_spectator(client_id) # Removal happens later or rely on thread exit
                # conn.close() # Close outside the lock
                # return # Return outside the lock
                pass # Handle removal after releasing lock if needed

    print(f"[DEBUG] Lock released in handle_client for {client_id}")

    # Check if game should start after releasing lock
    if len(players) == 2 and not game_in_progress:
        print(f"[DEBUG] Two players are ready, game not in progress. Calling start_new_game() outside lock.")
        start_new_game()
    elif len(players) != 2 and not game_in_progress:
         print(f"[DEBUG] Still waiting for players. Current count: {len(players)}")


def handle_spectator_input(spectator_data):
    """Handles input commands from a spectator."""
    rfile = spectator_data["r"]
    wfile = spectator_data["w"]
    client_id = spectator_data["id"]
    addr = spectator_data["addr"]
    print(f"[DEBUG] handle_spectator_input started for {client_id}")

    try:
        while True:
            print(f"[DEBUG] Waiting for input from spectator {client_id}")
            line = rfile.readline()
            if not line:
                print(f"[INFO] Spectator {client_id} disconnected (readline returned empty).")
                break
            cmd = line.strip().lower()
            print(f"[DEBUG] Received command '{cmd}' from spectator {client_id}")

            if cmd == "quit":
                print(f"[DEBUG] Spectator {client_id} issued quit command.")
                wfile.write("Thank you for watching. Goodbye!\n")
                wfile.flush()
                print(f"[DEBUG] Sent goodbye to spectator {client_id}")
                break
            elif cmd == "status":
                print(f"[DEBUG] Spectator {client_id} issued status command.")
                print(f"[DEBUG] Acquiring lock in handle_spectator_input for {client_id} status.")
                with lock:
                    print(f"[DEBUG] Lock acquired in handle_spectator_input for {client_id} status.")
                    try:
                        position = spectators.index(spectator_data) + 1
                        print(f"[DEBUG] Spectator {client_id} is position #{position} in queue.")
                        if game_in_progress:
                            wfile.write(f"A game is in progress. You are Spectator #{position} in queue.\n")
                            games_to_wait = (position - 1) // 2
                            if games_to_wait == 0:
                                wfile.write("You will play in the next game!\n")
                            else:
                                wfile.write(f"You will need to wait for approximately {games_to_wait} more game(s).\n")
                        else:
                            wfile.write(f"No game in progress. You are Spectator #{position} in queue.\n")
                        wfile.flush()
                        print(f"[DEBUG] Sent status to spectator {client_id}")
                    except ValueError:
                         print(f"[ERROR] Spectator {client_id} not found in spectator list during status check.")
                         break # Exit loop if not found (shouldn't happen unless removed unexpectedly)
                    except Exception as e:
                        print(f"[ERROR] Error sending status to spectator {client_id}: {e}")
                        break # Exit loop on error
                print(f"[DEBUG] Lock released in handle_spectator_input for {client_id} status.")
            else:
                print(f"[DEBUG] Spectator {client_id} sent unknown command '{cmd}'.")
                wfile.write("Spectator commands: status, quit\n")
                wfile.flush()
                print(f"[DEBUG] Sent help text to spectator {client_id}")
    except Exception as e:
        print(f"[ERROR] Error in handle_spectator_input for {client_id}: {e}")
    finally:
        print(f"[DEBUG] handle_spectator_input ending for {client_id}. Removing from queue.")
        remove_player_or_spectator(client_id)
        print(f"[DEBUG] Spectator {client_id} thread finished.")


def remove_player_or_spectator(client_id):
    """Removes a client from either the players or spectators list."""
    global players, spectators
    print(f"[DEBUG] Attempting to remove client {client_id}")
    print(f"[DEBUG] Acquiring lock in remove_player_or_spectator for {client_id}")
    with lock:
        print(f"[DEBUG] Lock acquired in remove_player_or_spectator for {client_id}")
        initial_players_len = len(players)
        initial_spectators_len = len(spectators)
        print(f"[DEBUG] Before removal: players_len={initial_players_len}, spectators_len={initial_spectators_len}")

        players_before = [p['id'] for p in players]
        spectators_before = [s['id'] for s in spectators]
        print(f"[DEBUG] Players before removal: {players_before}")
        print(f"[DEBUG] Spectators before removal: {spectators_before}")

        players = [p for p in players if p.get("id") != client_id]
        spectators = [s for s in spectators if s.get("id") != client_id]

        players_after = [p['id'] for p in players]
        spectators_after = [s['id'] for s in spectators]
        print(f"[DEBUG] Players after removal: {players_after}")
        print(f"[DEBUG] Spectators after removal: {spectators_after}")

        if len(players) < initial_players_len:
            print(f"[INFO] Removed player {client_id}")
        elif len(spectators) < initial_spectators_len:
            print(f"[INFO] Removed spectator {client_id}")
        else:
            print(f"[DEBUG] Client {client_id} not found in players or spectators list during removal attempt.")

        print(f"[DEBUG] Updating spectator positions after removal.")
        update_spectator_positions()
        print(f"[DEBUG] Lock released in remove_player_or_spectator for {client_id}")
    print(f"[DEBUG] remove_player_or_spectator finished for {client_id}")


def update_spectator_positions():
    """Informs spectators about their updated position in the queue."""
    print(f"[DEBUG] update_spectator_positions called.")
    print(f"[DEBUG] Acquiring lock in update_spectator_positions.")
    with lock:
        print(f"[DEBUG] Lock acquired in update_spectator_positions.")
        print(f"[DEBUG] Current spectators: {[s['id'] for s in spectators]}")
        for i, spec in enumerate(spectators):
            client_id = spec.get('id', 'Unknown')
            try:
                position = i + 1
                print(f"[DEBUG] Updating position for spectator {client_id} to #{position}")
                spec["w"].write(f"Queue update: You are now Spectator #{position} in line.\n")
                if position <= 2:
                    spec["w"].write("Preparing for your game soon...\n")
                spec["w"].flush()
                print(f"[DEBUG] Sent position update to {client_id}")
            except Exception as e:
                print(f"[ERROR] Error sending position update to spectator {client_id}: {e}")
                # Mark for removal or handle disconnection
                # Note: Modifying list while iterating is bad. Handle removals elsewhere.
                continue # Continue with the next spectator
        print(f"[DEBUG] Lock released in update_spectator_positions.")
    print(f"[DEBUG] update_spectator_positions finished.")


def broadcast_to_all(message):
    print(f"[DEBUG] Broadcasting message: '{message}'")
    client_list = []
    print(f"[DEBUG] Attempting to acquire lock in broadcast_to_all.") # Added print
    with lock:
        print(f"[DEBUG] Lock acquired in broadcast_to_all.") # This was the last print
        print(f"[DEBUG] Preparing client list for broadcast.") # Added print
        client_list = players + spectators
        print(f"[DEBUG] Broadcasting to {len(client_list)} clients.")
        print(f"[DEBUG] Lock released in broadcast_to_all (inside block).") # Added print
    print(f"[DEBUG] Lock released in broadcast_to_all (outside block).") # This print should appear after the block

    disconnected_clients = []
    print(f"[DEBUG] Starting loop to send broadcast messages.") # Added print
    for client in client_list:
        client_id = client.get('id', 'Unknown')
        print(f"[DEBUG] Attempting to send broadcast to {client_id}") # Added print inside loop
        try:
            client["w"].write(message + "\n")
            client["w"].flush()
            print(f"[DEBUG] Broadcast sent to {client_id}") # Added print inside loop
        except Exception as e:
            print(f"[ERROR] Error sending broadcast to {client_id}: {e}")
            disconnected_clients.append(client_id)
    print(f"[DEBUG] Finished loop to send broadcast messages.") # Added print

    if disconnected_clients:
        print(f"[INFO] Detected disconnected clients during broadcast: {disconnected_clients}. Attempting removal.")
        for client_id in disconnected_clients:
             remove_player_or_spectator(client_id)
    print(f"[DEBUG] broadcast_to_all finished.") # Added print


def recycle_players_to_spectators():
    """Moves current players back to the spectator queue."""
    global players, spectators
    print(f"[DEBUG] Recycling players to spectators called.")
    print(f"[DEBUG] Acquiring lock in recycle_players_to_spectators.")
    with lock:
        print(f"[DEBUG] Lock acquired in recycle_players_to_spectators.")
        print(f"[DEBUG] Players before recycling: {[p['id'] for p in players]}")
        print(f"[DEBUG] Spectators before recycling: {[s['id'] for s in spectators]}")
        disconnected_players = []
        for player in players:
            client_id = player.get('id', 'Unknown')
            try:
                print(f"[DEBUG] Attempting to inform player {client_id} about recycling.")
                player["w"].write("Game has ended. You are being returned to the spectator queue.\n")
                player["w"].flush()
                spectators.append(player)
                print(f"[INFO] Recycled {client_id} to spectators.")
            except Exception as e:
                print(f"[INFO] Player {client_id} has closed connection, not recycling to queue: {e}")
                disconnected_players.append(client_id)

        players.clear()
        print(f"[DEBUG] Players list cleared.")

        if disconnected_players:
             print(f"[INFO] Removing disconnected players during recycling: {disconnected_players}")
             # Remove disconnected players who weren't added back to spectators
             spectators = [s for s in spectators if s.get('id') not in disconnected_players]


        print(f"[DEBUG] Players after recycling: {[p['id'] for p in players]}")
        print(f"[DEBUG] Spectators after recycling: {[s['id'] for s in spectators]}")
        print(f"[DEBUG] Updating spectator positions after recycling.")
        update_spectator_positions()
        print(f"[DEBUG] Lock released in recycle_players_to_spectators.")
    print(f"[DEBUG] recycle_players_to_spectators finished.")


def promote_spectators():
    """Promotes the first two spectators to players if available."""
    global players, spectators
    print(f"[DEBUG] promote_spectators called.")
    promoted = False
    print(f"[DEBUG] Acquiring lock in promote_spectators.")
    with lock:
        print(f"[DEBUG] Lock acquired in promote_spectators.")
        print(f"[DEBUG] Current spectator count: {len(spectators)}")
        if len(spectators) >= 2:
            print(f"[DEBUG] Enough spectators ({len(spectators)}) to promote two.")
            players.extend(spectators[:2])
            promoted_player1_id = spectators[0].get('id', 'Unknown')
            promoted_player2_id = spectators[1].get('id', 'Unknown')
            print(f"[DEBUG] Promoted {promoted_player1_id} and {promoted_player2_id} to players.")
            spectators = spectators[2:]
            print(f"[DEBUG] Remaining spectators: {[s['id'] for s in spectators]}")
            promoted = True
            try:
                print(f"[DEBUG] Attempting to inform new players.")
                players[0]["w"].write("You are Player 1 in the new game. Preparing to start...\n")
                players[1]["w"].write("You are Player 2 in the new game. Preparing to start...\n")
                players[0]["w"].flush()
                players[1]["w"].flush()
                print(f"[DEBUG] Informed new players.")
            except Exception as e:
                print(f"[ERROR] Error informing new players after promotion: {e}")
                # This is problematic if they disconnected here. Need robust handling.
                # For now, let the next game setup deal with disconnections.

            print(f"[DEBUG] Informing remaining spectators about queue change.")
            for i, spec in enumerate(spectators):
                client_id = spec.get('id', 'Unknown')
                try:
                    spec["w"].write("New game starting with Spectators #1 and #2 as players.\n")
                    spec["w"].write(f"You are now Spectator #{i + 1} in the queue.\n")
                    spec["w"].flush()
                    print(f"[DEBUG] Informed spectator {client_id} about new queue position.")
                except Exception as e:
                     print(f"[ERROR] Error informing spectator {client_id} about queue change: {e}")
                     # Handle disconnection?

        else:
            print(f"[DEBUG] Not enough spectators ({len(spectators)}) to promote.")

        print(f"[DEBUG] Players after promotion attempt: {[p['id'] for p in players]}")
        print(f"[DEBUG] Spectators after promotion attempt: {[s['id'] for s in spectators]}")
        print(f"[DEBUG] Lock released in promote_spectators.")
    print(f"[DEBUG] promote_spectators finished. Promoted: {promoted}")
    return promoted


def run_game_countdown():
    """Runs the countdown before a game starts."""
    print(f"[DEBUG] run_game_countdown called.")
    for i in range(GAME_START_COUNTDOWN, 0, -1):
        message = f"New game starting in {i} seconds..."
        print(f"[DEBUG] Countdown: {message}")
        broadcast_to_all(message)
        time.sleep(1)
    broadcast_to_all("Game is starting now!")
    print(f"[DEBUG] Countdown finished. Game start message sent.")


def start_new_game():
    """Initiates a new game thread."""
    global game_in_progress
    print(f"[DEBUG] start_new_game called.")
    print(f"[DEBUG] Acquiring lock in start_new_game.")
    with lock:
        print(f"[DEBUG] Lock acquired in start_new_game.")
        if len(players) != 2:
            print(f"[DEBUG] Cannot start game, not exactly 2 players ({len(players)}).")
            game_in_progress = False # Ensure flag is correct if check fails
            print(f"[DEBUG] game_in_progress set to {game_in_progress}.")
            print(f"[DEBUG] Lock released in start_new_game.")
            return
        if game_in_progress:
            print(f"[DEBUG] Game already in progress. Skipping start_new_game.")
            print(f"[DEBUG] Lock released in start_new_game.")
            return

        game_in_progress = True
        print(f"[DEBUG] game_in_progress set to {game_in_progress}.")
        print(f"[DEBUG] Two players ready. Broadcasting game start.")
        broadcast_to_all("A new game is starting!")
        print(f"[DEBUG] Broadcasting successful.")

        player1 = players[0]
        player2 = players[1]
        print(f"[DEBUG] Player 1: {player1['id']}, Player 2: {player2['id']}")
        print(f"[DEBUG] Starting run_game_wrapper thread.")
        threading.Thread(
            target=run_game_wrapper,
            args=(player1["r"], player1["w"], player2["r"], player2["w"], spectators), # Pass spectator list here? Or access global in wrapper? Accessing global in wrapper is safer with lock.
            daemon=True
        ).start()
        print(f"[DEBUG] Game wrapper thread started.")
        print(f"[DEBUG] Lock released in start_new_game.")
    print(f"[DEBUG] start_new_game finished.")


def run_game_wrapper(rfile1, wfile1, rfile2, wfile2, spectator_list_at_start):
    """Wrapper to run the game and handle post-game cleanup."""
    global game_in_progress, spectators # Need access to global spectators list for updates
    print(f"[DEBUG] run_game_wrapper started.")
    # It's better to access spectators list inside the wrapper with the lock when needed,
    # rather than passing a potentially stale list from outside the lock.
    current_spectators = []
    print(f"[DEBUG] Acquiring lock in run_game_wrapper to get spectator list.")
    with lock:
        print(f"[DEBUG] Lock acquired in run_game_wrapper.")
        current_spectators = list(spectators) # Get a snapshot under lock if needed, though passing it to run_multiplayer_game might be okay if it doesn't modify it. Let's stick to accessing global with lock inside if modifications are needed.
        # The run_multiplayer_game function itself needs to handle spectator broadcasts,
        # so it should probably be passed the *global* spectators list or a mechanism
        # to safely access it (like the lock).
        # Let's assume run_multiplayer_game needs the lock to interact with spectators.
        # We'll pass the lock and the global spectators list.
        # (Requires modifying run_multiplayer_game signature if it doesn't already support this)
        # Assuming run_multiplayer_game uses the global `spectators` and the `lock`.
        # The original code passed `spectators` by value. Let's update the plan.
        # Pass the lock and access the global spectators inside run_multiplayer_game if it needs to write.
        # OR, modify run_multiplayer_game to accept a broadcast function.
        # Let's stick to the original design and assume run_multiplayer_game handles
        # communication and potentially needs to broadcast/message spectators from its end.
        # Passing the *current* list snapshot is safer if the game code itself doesn't use the global lock.
        # However, the game code likely needs to send real-time updates, so it needs to
        # be aware of the changing spectator list, which means it needs the lock or
        # a safe way to broadcast.
        # Given the original code, passing the snapshot is what was intended. Let's stick to that
        # but acknowledge the potential issue if spectators join/leave *during* the game
        # and the game code doesn't handle dynamic list changes.
        # A robust solution would involve passing the `broadcast_to_all` function or the lock+list
        # to the game logic. For now, sticking to the original arg structure.
        spectators_for_game = list(spectators) # Snapshot for the game function
        print(f"[DEBUG] Snapshot of spectators taken for game: {[s['id'] for s in spectators_for_game]}")
        print(f"[DEBUG] Lock released in run_game_wrapper after getting spectator snapshot.")

    try:
        print(f"[DEBUG] Calling run_multiplayer_game...")
        # The run_multiplayer_game function (imported from battleship) needs to handle
        # sending messages to players and spectators. It needs access to their wfiles.
        # It also needs to know who the current spectators are *during* the game.
        # The original code passes the spectator list. Let's assume it uses this list
        # to send updates. If new spectators join during the game, they won't get updates
        # from the game itself, only server-level messages. This is a limitation of the design.
        run_multiplayer_game(rfile1, wfile1, rfile2, wfile2, spectators_for_game)
        print(f"[DEBUG] run_multiplayer_game finished without exception.")
    except Exception as e:
        print(f"[ERROR] Exception caught in run_game_wrapper during game execution: {e}")
    finally:
        print(f"[DEBUG] Game execution finished or errored. Starting cleanup.")
        print(f"[DEBUG] Setting game_in_progress to False.")
        game_in_progress = False
        time.sleep(1) # Give a moment for final messages/cleanup
        print(f"[DEBUG] Game ended. Broadcasting game over message.")
        broadcast_to_all("The current game has ended.")

        print(f"[DEBUG] Recycling players.")
        recycle_players_to_spectators()
        print(f"[DEBUG] Running garbage collection.")
        gc.collect()
        print(f"[DEBUG] Broadcasting preparation for next match.")
        broadcast_to_all("Preparing for the next match...")

        print(f"[DEBUG] Attempting to promote spectators for the next game.")
        if promote_spectators():
            print(f"[DEBUG] Spectators promoted. Starting countdown.")
            time.sleep(1) # Pause before countdown
            run_game_countdown()
            print(f"[DEBUG] Countdown finished. Calling start_new_game for next match.")
            start_new_game()
        else:
            print(f"[DEBUG] Not enough spectators to promote. Waiting for more players.")
            broadcast_to_all("Waiting for more players to join...")
        print(f"[DEBUG] run_game_wrapper finished.")


def main():
    """Main function to start the server."""
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    print(f"[DEBUG] main function started.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        print(f"[DEBUG] Socket created.")
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        print(f"[DEBUG] Socket option SO_REUSEADDR set.")
        try:
            s.bind((HOST, PORT))
            print(f"[INFO] Socket bound to {HOST}:{PORT}")
        except Exception as e:
            print(f"[ERROR] Failed to bind socket: {e}")
            return

        try:
            s.listen()
            print(f"[INFO] Server listening for incoming connections...")
        except Exception as e:
            print(f"[ERROR] Failed to listen on socket: {e}")
            return

        while True:
            print(f"[DEBUG] Waiting for a new connection...")
            try:
                conn, addr = s.accept()
                print(f"[INFO] Connection established with {addr}")
                print(f"[DEBUG] Accepted connection. Starting handle_client thread for {addr}")
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
                print(f"[DEBUG] handle_client thread started for {addr}")
            except KeyboardInterrupt:
                print(f"[INFO] Server shutting down due to KeyboardInterrupt.")
                break # Exit the loop on Ctrl+C
            except Exception as e:
                print(f"[ERROR] Error accepting connection: {e}")
                # Continue listening even if one connection fails

    print(f"[INFO] Server main loop ended. Shutting down.")


if __name__ == "__main__":
    print(f"[DEBUG] Script started. Calling main().")
    main()
    print(f"[DEBUG] main() finished.")
    print(f"[INFO] Server has shut down.")