import struct
import zlib

# Packet Structure (rough sketch, maybe update this later):
# seq_num number
# packet type
# game-specific fields
# checksum

#Recommended Packet Types
#   Type Code	 Name	Purpose/When Used
#1	USER_INPUT	        Player move, ship placement, or chat from client
#2	SYSTEM_MESSAGE	    System messages from server (welcome, errors, etc)
#3	CHAT_MESSAGE	    Chat messages between players/spectators
#4	BOARD_UPDATE	    Board/grid updates (e.g., after a move)
#5	GAME_STATE	        Game start, end, or status updates
#6	ERROR	            Error or invalid packet notification
#7	ACK	Acknowledgement (optional, for reliability)

#"byte sum" or "additive checksum" instead of CRC32 from library

# Packet Type Constants
USER_INPUT      = 1  # Player move, ship placement, or chat from client
SYSTEM_MESSAGE  = 2  # System messages from server (welcome, errors, etc)
CHAT_MESSAGE    = 3  # Chat messages between players/spectators
BOARD_UPDATE    = 4  # Board/grid updates (e.g., after a move)
GAME_STATE      = 5  # Game start, end, or status updates
ERROR           = 6  # Error or invalid packet notification
ACK             = 7  # Acknowledgement (optional, for reliability)

def pack_packet(seq_num, pktType, payload_bytes):
    payload_len = len(payload_bytes)
    header      = struct.pack('!HBH', seq_num, pktType, payload_len)
    body        = header + payload_bytes
    checksum    = sum(body) % 256
    packet      = body + struct.pack('!B', checksum)
    return packet

# might want to split this into smaller functions later
def unpack_packet(packet_bytes):
    if len(packet_bytes) < 6:
        raise ValueError("Packet too short")
    header                     = packet_bytes[:5]
    seq, pkt_type, payload_len = struct.unpack('!HBH', header)
    payload                    = packet_bytes[5:-1]
    recv_sum              = packet_bytes[-1]
    body                       = packet_bytes[:-1]
    calc_sum              = sum(body) % 256
    if recv_sum          != calc_sum:
        raise ValueError("Checksum mismatch")
    return seq, pkt_type, payload


def recv_full(conn, n):
    """Helper to receive exactly n bytes from the socket."""
    data = b''
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed")
        data += chunk
    return data

def receive_packet(conn):
    # 1. Grab the first 5 bytes (header stuff)
    header = recv_full(conn, 5)
    seq, pkt_type, payload_len = struct.unpack('!HBH', header)
    # 2. Read payload
    payload = recv_full(conn, payload_len)
    # 3. Read checksum (1 byte)
    checksum = recv_full(conn, 1)
    # 4. Stitch it all back together and unpack it
    packet_bytes = header + payload + checksum
    try:
        seq, pkt_type, payload = unpack_packet(packet_bytes)
        return seq, pkt_type, payload
    except ValueError as e:
        print("Corrupted packet received:", e)
        # TODO: maybe alert client? or log this more clearly?
        return None


# TESTS!!!!!!!1!!!!!
if __name__ == "__main__":
    #matching type
    seq = 1
    pkt_type = USER_INPUT
    payload = b"Hello, world!"
    packet = pack_packet(seq, pkt_type, payload)
    print("[debug] test packet created")
    print("Packed:", packet)
    seq2, pkt_type2, payload2 = unpack_packet(packet)
    print("Unpacked:", seq2, pkt_type2, payload2)

    # Simulate a mismatched communication: wrong packet type expected
    expected_type = SYSTEM_MESSAGE
    if pkt_type2 == expected_type:
        print("Received expected SYSTEM_MESSAGE.")
    else:
        print(f"Packet type mismatch! Expected {expected_type}, got {pkt_type2}.")

    # Simulate a corrupted packet (checksum mismatch)
    corrupted_packet = bytearray(packet)
    corrupted_packet[10] ^= 0xFF  # Flip a byte in the payload
    try:
        unpack_packet(corrupted_packet)
    except ValueError as e:
        print("Checksum error detected as expected:", e)

    # Simulate sending 5 packets with incrementing seq_num numbers
    packets = []
    for seq_num in range(1, 6):
        pkt = pack_packet(seq_num, USER_INPUT, f"Message {seq_num}".encode())
        packets.append(pkt)

    # Simulate out-of-order delivery by shuffling the packets
    import random
    shuffled_packets = packets[:]
    random.shuffle(shuffled_packets)
    print("Packet receive order (seq_num numbers):", [unpack_packet(thing)[0] for p in shuffled_packets])

    # Simulate receiver expecting packets in order
    expected_seq = 1
    for thing in shuffled_packets:
        try:
            seq, pkt_type, payload = unpack_packet(thing)
            if seq == expected_seq:
                print(f"Received expected packet {seq}: {payload.decode()}")
                expected_seq += 1
            else:
                print(f"Out-of-seq_num packet! Expected {expected_seq}, got {seq}. Discarding.")
        except ValueError as e:
            print("Corrupted packet detected:", e)


