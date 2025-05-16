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
lock = threading.Lock()
game_in_progress = False
GAME_START_COUNTDOWN = 5  # seconds


def handle_client(conn, addr):
    global players, spectators, game_in_progress
    rfile = conn.makefile('r')
    wfile = conn.makefile('w')

    client_id = f"Client-{addr[0]}:{addr[1]}"
    print(f"[INFO] New connection from {client_id}")

    with lock:
        if len(players) < 2 and not game_in_progress:
            player_num = len(players) + 1
            players.append({"r": rfile, "w": wfile, "addr": addr, "id": client_id})
            player_role = f"Player {player_num}"
            try:
                wfile.write(f"Welcome! You are {player_role}.\n")
                if player_num == 1:
                    wfile.write("Waiting for another player to join...\n")
                wfile.flush()
            except:
                print(f"[INFO] {client_id} disconnected before pairing.")
                remove_player_or_spectator(client_id)
                conn.close()
                return

            if len(players) == 2:
                start_new_game()

        else:
            spectator_data = {"r": rfile, "w": wfile, "addr": addr, "id": client_id}
            spectators.append(spectator_data)
            try:
                position = spectators.index(spectator_data) + 1
                wfile.write(f"Welcome! You are Spectator #{position} in the waiting queue.\n")
                if game_in_progress:
                    wfile.write("A game is currently in progress. You will receive updates about the game.\n")
                    if position <= 2:
                        wfile.write(f"You will be Player {position} in the next game!\n")
                    else:
                        games_to_wait = (position - 1) // 2
                        wfile.write(f"You will need to wait for approximately {games_to_wait} game(s) before playing.\n")
                else:
                    if position <= 2:
                        wfile.write("The next game is about to start. Preparing players...\n")
                wfile.flush()
                threading.Thread(target=handle_spectator_input, args=(spectator_data,), daemon=True).start()
            except:
                print(f"[INFO] Spectator {client_id} disconnected.")
                remove_player_or_spectator(client_id)
                conn.close()


def handle_spectator_input(spectator_data):
    rfile = spectator_data["r"]
    wfile = spectator_data["w"]
    client_id = spectator_data["id"]

    try:
        while True:
            line = rfile.readline()
            if not line:
                break
            cmd = line.strip().lower()
            if cmd == "quit":
                wfile.write("Thank you for watching. Goodbye!\n")
                wfile.flush()
                break
            elif cmd == "status":
                with lock:
                    position = spectators.index(spectator_data) + 1
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
            else:
                wfile.write("Spectator commands: status, quit\n")
                wfile.flush()
    except:
        print(f"[INFO] Spectator {client_id} disconnected.")
    finally:
        remove_player_or_spectator(client_id)


def remove_player_or_spectator(client_id):
    global players, spectators
    with lock:
        players = [p for p in players if p.get("id") != client_id]
        spectators = [s for s in spectators if s.get("id") != client_id]
        update_spectator_positions()


def update_spectator_positions():
    with lock:
        for i, spec in enumerate(spectators):
            try:
                position = i + 1
                spec["w"].write(f"Queue update: You are now Spectator #{position} in line.\n")
                if position <= 2:
                    spec["w"].write("Preparing for your game soon...\n")
                spec["w"].flush()
            except:
                continue


def broadcast_to_all(message):
    for client in players + spectators:
        try:
            client["w"].write(message + "\n")
            client["w"].flush()
        except:
            continue


def recycle_players_to_spectators():
    global players, spectators
    with lock:
        for player in players:
            try:
                player["w"].write("Game has ended. You are being returned to the spectator queue.\n")
                player["w"].flush()
                spectators.append(player)
                print(f"[INFO] Recycled {player['id']} to spectators.")
            except:
                print(f"[INFO] Player {player['id']} has closed connection, not recycling to queue")
        players.clear()
        update_spectator_positions()


def promote_spectators():
    global players, spectators
    with lock:
        if len(spectators) >= 2:
            players.extend(spectators[:2])
            spectators = spectators[2:]
            try:
                players[0]["w"].write("You are Player 1 in the new game. Preparing to start...\n")
                players[1]["w"].write("You are Player 2 in the new game. Preparing to start...\n")
                players[0]["w"].flush()
                players[1]["w"].flush()
            except:
                pass
            for i, spec in enumerate(spectators):
                try:
                    spec["w"].write("New game starting with Spectators #1 and #2 as players.\n")
                    spec["w"].write(f"You are now Spectator #{i + 1} in the queue.\n")
                    spec["w"].flush()
                except:
                    pass
            return True
        return False


def run_game_countdown():
    for i in range(GAME_START_COUNTDOWN, 0, -1):
        broadcast_to_all(f"New game starting in {i} seconds...")
        time.sleep(1)
    broadcast_to_all("Game is starting now!")


def start_new_game():
    global game_in_progress
    if len(players) != 2:
        return
    game_in_progress = True
    broadcast_to_all("A new game is starting!")
    threading.Thread(
        target=run_game_wrapper,
        args=(players[0]["r"], players[0]["w"], players[1]["r"], players[1]["w"], spectators),
        daemon=True
    ).start()


def run_game_wrapper(rfile1, wfile1, rfile2, wfile2, spectator_list):
    global game_in_progress
    try:
        run_multiplayer_game(rfile1, wfile1, rfile2, wfile2, spectator_list)
    except Exception as e:
        print(f"[ERROR] Game error: {e}")
    finally:
        game_in_progress = False
        time.sleep(1)
        broadcast_to_all("The current game has ended.")
        recycle_players_to_spectators()
        gc.collect()
        broadcast_to_all("Preparing for the next match...")

        if promote_spectators():
            time.sleep(1)
            run_game_countdown()
            start_new_game()
        else:
            broadcast_to_all("Waiting for more players to join...")


def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        while True:
            try:
                conn, addr = s.accept()
                print(f"[INFO] Connection established with {addr}")
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"[ERROR] Error accepting connection: {e}")


if __name__ == "__main__":
    main()
