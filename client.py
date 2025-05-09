import socket
import threading

HOST = '127.0.0.1'
PORT = 5000
running = True

def receive_messages(rfile):
    while running:
        line = rfile.readline()
        if not line:
            print("[INFO] Server disconnected.")
            break

        line = line.strip()
        if line == "GRID":
            print("\n[Opponent's Board]")
            while True:
                board_line = rfile.readline()
                if not board_line or board_line.strip() == "":
                    break
                print(board_line.strip())
        else:
            print(line)

def main():
    global running
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        rfile = s.makefile('r')
        wfile = s.makefile('w')

        receiver = threading.Thread(target=receive_messages, args=(rfile,), daemon=True)
        receiver.start()

        try:
            while running:
                user_input = input(">> ")
                wfile.write(user_input + '\n')
                wfile.flush()
                if user_input.lower() == "quit":
                    running = False
                    break
        except KeyboardInterrupt:
            running = False
            print("\n[INFO] Client exiting.")

if __name__ == "__main__":
    main()
