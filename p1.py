import socket
import time

HOST = '127.0.0.1'
PORT = 5001

# Pretend inputs (should validate this later maybe)
inputsToSend = [
    "a1",    # 1st ship coordinate
    "h",    # 1st ship orientation
    "b1",   # 2nd ship coordinate
    "h",    # 2nd ship orientation
    "c1",   # 3rd ship coordinate
    "h",    # 3rd ship orientation
    "d1",   # 4th ship coordinate
    "h",    # 4th ship orientation
    "e1",   # 5th ship coordinate
    "h"     # 5th ship orientation
]

def main():
    with socket.create_connection((HOST, PORT)) as sock:
        rfile = sock.makefile('r')
        wfile = sock.makefile('w')

        # This should probably be read from user input but hardcoding for now
        wfile.write("P1\n")
        wfile.flush()
        print("[CLIENT] Sent username: P1")

        ix = 0
        while ix < len(inputsToSend):
            server_line = rfile.readline()
            if not server_line:
                break
            print(f"[SERVER] {server_line.strip()}")
            # lazy prompt checkign
            if "[SYSTEM] Enter start coordinate" in server_line or "[SYSTEM] Enter orientation" in server_line:
                # Send the corresponding input
                out = inputsToSend[ix]
                print(f"[CLIENT] Sending: {out}")
                # DEBUG: sent input"
                wfile.write(out + "\n")
                wfile.flush()
                ix += 1
                time.sleep(0.2)  # Small delay to avoid flooding

        # print anything else server says (should limit this?)
        for _ in range(10):
            server_line = rfile.readline()
            if not server_line:
                break
            print(f"[SERVER] {server_line.strip()}")

if __name__ == "__main__":
    main()
