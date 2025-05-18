import socket
import time

HOST = '127.0.0.1'
PORT = 5001

# The sequence of ship placement inputs to send after each prompt
placement_inputs = [
    "a",    # 1st ship coordinate (will likely be invalid, but as requested)
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

        # Send username first
        wfile.write("P2\n")
        wfile.flush()
        print("[CLIENT] Sent username: P2")

        input_idx = 0
        while input_idx < len(placement_inputs):
            server_line = rfile.readline()
            if not server_line:
                break
            print(f"[SERVER] {server_line.strip()}")
            # Wait for the prompt for coordinate or orientation
            if "[SYSTEM] Enter start coordinate" in server_line or "[SYSTEM] Enter orientation" in server_line:
                # Send the corresponding input
                to_send = placement_inputs[input_idx]
                print(f"[CLIENT] Sending: {to_send}")
                wfile.write(to_send + "\n")
                wfile.flush()
                input_idx += 1
                time.sleep(0.2)  # Small delay to avoid flooding

        # Optionally, print further server output
        for _ in range(10):
            server_line = rfile.readline()
            if not server_line:
                break
            print(f"[SERVER] {server_line.strip()}")

if __name__ == "__main__":
    main()