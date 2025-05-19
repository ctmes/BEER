import random
import struct
import sys
import os

from packet import pack_packet, unpack_packet, USER_INPUT, SYSTEM_MESSAGE


def inject_random_byte_error(packet_bytes, num_errors=1):
    """ Randomly injects some errors (random bit flips) into the packet except checksum.
    If there are too few bytes, it just returns the packet unaltered.
    """
    if len(packet_bytes) < 6: # check valid packet
        return packet_bytes

    injectable_area = packet_bytes[:-1]
    corrupted_packet = bytearray(packet_bytes)

    # Inject errors
    for _ in range(num_errors):
        if not injectable_area:  # just in case...
            break
        error_index = random.randrange(len(injectable_area))

        # Random bit flip
        bit_to_flip = 1 << random.randrange(8)
        corrupted_packet[error_index] ^= bit_to_flip  # XOR to flip

    return bytes(corrupted_packet)


def run_simulation(num_packets, error_probability_byte):
    """ Run the simulation, flipping bits and testing checksum detection. """
    print(f"--- Starting Checksum Simulation ---")
    print(f"Simulating {num_packets} packets...")
    print(f"Byte error chance: {error_probability_byte * 100:.2f}%")
    print("-" * 35)

    total_packets_sent = 0
    errors_injected_count = 0
    errors_detected_count = 0
    undetected_errors_count = 0  # true neg

    seq_num = 1

    for i in range(num_packets):
        total_packets_sent += 1
        payload_data = f"Test message {i + 1}".encode()
        packet_type = USER_INPUT  # Or SYSTEM_MESSAGE, but let’s keep it simple
        original_packet = pack_packet(seq_num, packet_type, payload_data)
        corrupted_packet = bytearray(original_packet)  # Copy of original
        error_was_injected_in_this_packet = False

        # Try to randomly flip some bits in the packet (except checksum)
        for byte_index in range(len(corrupted_packet) - 1):  # No checksum
            if random.random() < error_probability_byte:
                bit_to_flip = 1 << random.randrange(8)  # Pick a random bit
                corrupted_packet[byte_index] ^= bit_to_flip
                error_was_injected_in_this_packet = True

        # If we injected errors, use the corrupted packet
        if error_was_injected_in_this_packet:
            errors_injected_count += 1
            corrupted_packet_bytes = bytes(corrupted_packet)
        else:
            corrupted_packet_bytes = original_packet

        try:
            seq, pkt_type, payload = unpack_packet(corrupted_packet_bytes)
            if error_was_injected_in_this_packet:
                undetected_errors_count += 1
        except ValueError as e:
            if "Checksum mismatch" in str(e):
                errors_detected_count += 1

            else:
                pass
            # just inc ase ^^


    print("-" * 35)
    print(f"Total packets simulated: {total_packets_sent}")
    print(f"Packets with errors injected: {errors_injected_count}")
    print(f"Errors detected by checksum: {errors_detected_count}")
    print(f"Undetected errors (oops): {undetected_errors_count}")
    print("-" * 35)

    if errors_injected_count > 0:
        detection_rate = (errors_detected_count / errors_injected_count) * 100
        print(f"Detection rate: {detection_rate:.2f}%")
    else:
        print("No errors were injected at all.")

    if total_packets_sent > 0:
        undetected_percentage = (undetected_errors_count / total_packets_sent) * 100
        print(f"Undetected errors in {undetected_percentage:.4f}% of packets.")


if __name__ == "__main__":
    # 10,000 packets and a 1% chance of error
    run_simulation(num_packets=10000, error_probability_byte=0.01)
