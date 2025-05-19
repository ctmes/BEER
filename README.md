# BEER: Battleships - Engage in Explosive Rivalry
This project implements a networked, turn-based Battleship game named "BEER" as part of the CITS3002 Computer Networks course at the University of Western Australia. The project involves developing a multiplayer server and client(s) capable of handling players, managing game states, broadcasting results, and addressing network challenges.

![image](https://github.com/user-attachments/assets/d1955370-efb4-4aeb-b85d-98b34dffd051)


## Project Overview
The game follows the standard Battleship rules:

- Players secretly place a set of ships on a 10x10 grid,
- Players take turns "firing" at specific grid coordinates (e.g., B5),
- The server announces whether each shot is a hit, miss, or sunk a ship, and
- The game ends when one player's entire fleet is destroyed.
  
The project is structured into four tiers of increasing complexity, building from a basic two-player game to advanced features like custom protocols and security.

## Files
- `battleship.py`: Essential constants and gameplay logic which is shared by both the client and the server. It includes the Board class to track ships, hits, etc., coordinate parsing, single-player mode, and multiplayer support.
- `server.py`: Implements the game server. It handles client connections, manages game flow, and broadcasts updates. Based on the code content and project tiers, it includes features for multiple concurrent connections, spectator support, timeout handling, and reconnection support.
- `client.py`: Implements the game client with a minimal implementation for connecting to the server. It uses threading to separate receiving and sending operations to fix message synchronization issues where server responses appear out of order or prompts are late.
- `packet.py`: A rudimentary custom packet format and includes functions for packing and unpacking packets and receiving data. It incorporates a byte sum checksum for verifying data integrity.
- `p1.py` and `p2.py`: Simple client scripts designed for testing, sending predefined inputs for ship placement to the server.


## Setup and Running
1. Make sure you have Python installed
2. The game server is configured to listen on `127.0.0.1` (localhost) on port `5001` by default
3. To run the server: `python server.py` (in a terminal)
4. To run a client: `python client.py` (in a different terminal)
#### Notes: 
- The `battleship.py` script can be run directly to play a local, single-player version of Battleship for testing the expected gameplay loop: `python battleship.py`.
- There must be a minimum of 2 clients connected to play a game
- Any extra clients are spectators in a lobby that can see both players grids

## Commands

Clients can use the following commands by typing them into their terminal and using `/`:

* `/help`: Displays the list of available commands for your current role (player or spectator).
* `/quit`: Initiates disconnection from the server. If you are a player in an active game, this may be treated as a forfeit (depending on the server's implementation tier).
* `/chat <message>`: Sends a chat message to all connected participants (players and spectators).
* `/status`: (Likely available to spectators) Shows your current position in the waiting queue.

## Gameplay
Players firstly place ships into their grid by specifying the top-left coordinate and an orientation. E.g., the player types "A1" and "H" and repeats until all ships are played. 
After all ships are placed, simply guess coordinates you want to fire.

## Implemented Features from Tiers
The implementation described by the files aims to fulfill requirements outlined in the project description:

### Tier 1: Basic 2-Player Game with Concurrency in BEER 

- Concurrency in the client using threading to separate receiving and sending messages.
- Server accepts connections from exactly two players to start a game.
- Implements standard Battleship mechanics: ship placement, alternate firing, reporting hit/miss/sunk, and ending the game when all ships are sunk.
- Uses a simple message exchange between client and server.
- Assumes connections remain stable, and disconnection can end the game.

### Tier 2: Gameplay Quality-of-Life & Scalability 

- Extended input validation on the server to handle invalid commands gracefully.
- Server supports running multiple games sequentially after one ends.
- Timeout handling implemented to skip a player's turn or result in a forfeit after inactivity.
- Server detects and handles disconnections gracefully, often treating a mid-game disconnect as a forfeit while the server continues running.
- Communication with idle or extra clients (e.g., placing them in a waiting lobby).

### Tier 3: Multiple Connections 

- Server accepts more than two clients concurrently, with two being players and extras becoming spectators.
- Spectators receive real-time game updates like board changes and shot outcomes.
- Simple mechanism for player reconnection within a short timeframe, maintaining game state.
- Defined method for selecting the next two players from connected clients when a game ends.

### Tier 4: Advanced Features 

- T4.1 Custom Low-Level Protocol with Checksum: Implementation includes a custom packet format with a header (sequence number, packet type, payload length) and a byte sum checksum to detect corrupted packets.
- T4.2 Instant Messaging (IM) Channel: A chat system is implemented allowing players and spectators to send messages using a /chat command, broadcasted to all participants.
- T4.4 Denial of Service (DoS) Connection and Input-flooding Countermeasures: There are rate limits for inputs (2 messages/second) for clients and a maximum of 6 connections to the server, preventing spam that can consume excessive memory and CPU usage. More details are in the report.

By David Poh and Colin Melville
