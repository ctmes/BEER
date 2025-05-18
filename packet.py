import struct
import zlib

# Packet Type Constants
USER_INPUT      = 1  # Player move, ship placement, or chat from client
SYSTEM_MESSAGE  = 2  # System messages from server (welcome, errors, etc)
CHAT_MESSAGE    = 3  # Chat messages between players/spectators
BOARD_UPDATE    = 4  # Board/grid updates (e.g., after a move)
GAME_STATE      = 5  # Game start, end, or status updates
ERROR           = 6  # Error or invalid packet notification
ACK             = 7  # Acknowledgement (optional, for reliability)

def pack_packet(sequence, packet_type, payload_bytes):
    payload_len = len(payload_bytes)
    header = struct.pack('!HBH', sequence, packet_type, payload_len)
    body = header + payload_bytes
    checksum = sum(body) % 256
    packet = body + struct.pack('!B', checksum)
    return packet

def unpack_packet(packet_bytes):
    if len(packet_bytes) < 6:
        raise ValueError("Packet too short")
    header = packet_bytes[:5]
    seq, pkt_type, payload_len = struct.unpack('!HBH', header)
    payload = packet_bytes[5:-1]
    checksum_recv = packet_bytes[-1]
    body = packet_bytes[:-1]
    checksum_calc = sum(body) % 256
    if checksum_recv != checksum_calc:
        raise ValueError("Checksum mismatch")
    return seq, pkt_type, payload

if __name__ == "__main__":
    #matching type 
    seq = 1
    pkt_type = USER_INPUT
    payload = b"Hello, world!"
    packet = pack_packet(seq, pkt_type, payload)
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

    # Simulate sending 5 packets with incrementing sequence numbers
    packets = []
    for seq in range(1, 6):
        pkt = pack_packet(seq, USER_INPUT, f"Message {seq}".encode())
        packets.append(pkt)

    # Simulate out-of-order delivery by shuffling the packets
    import random
    shuffled_packets = packets[:]
    random.shuffle(shuffled_packets)
    print("Packet receive order (sequence numbers):", [unpack_packet(p)[0] for p in shuffled_packets])

    # Simulate receiver expecting packets in order
    expected_seq = 1
    for p in shuffled_packets:
        try:
            seq, pkt_type, payload = unpack_packet(p)
            if seq == expected_seq:
                print(f"Received expected packet {seq}: {payload.decode()}")
                expected_seq += 1
            else:
                print(f"Out-of-sequence packet! Expected {expected_seq}, got {seq}. Discarding.")
        except ValueError as e:
            print("Corrupted packet detected:", e)


# Packet Structure:
# sequence number
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