# auto_client.py
import subprocess
import sys
import time

# The sequence of inputs you want to send (each followed by Enter)
inputs = [
    "P2",
    "a1", "h",
    "b1", "h",
    "c1", "h",
    "d1", "h",
    "e1", "h"
]

# Start the client.py process
proc = subprocess.Popen(
    [sys.executable, "client.py"],
    stdin=subprocess.PIPE,
    stdout=sys.stdout,
    stderr=sys.stderr,
    bufsize=1,
    universal_newlines=True
)

# Send the scripted inputs
for line in inputs:
    print(f"[auto] Sending: {line}")
    proc.stdin.write(line + "\n")
    proc.stdin.flush()
    time.sleep(0.2)  # Small delay to mimic human typing and allow server responses

# Now let the user take over
print("[auto] Automated input complete. You now have manual control. Type your moves below:")

# Attach your stdin to the process
try:
    while proc.poll() is None:
        user_input = input()
        proc.stdin.write(user_input + "\n")
        proc.stdin.flush()
except KeyboardInterrupt:
    print("Exiting...")
    proc.terminate()