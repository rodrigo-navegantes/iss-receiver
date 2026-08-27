"""Decodificacao NRZI, HDLC, FCS e AX.25."""

import numpy as np


FLAG = np.array([0, 1, 1, 1, 1, 1, 1, 0], dtype=np.uint8)


def nrzi_decode(levels):
    """Nivel igual = bit 1; mudanca de nivel = bit 0."""
    return (levels[1:] == levels[:-1]).astype(np.uint8)


def find_flags(bits):
    positions = []
    for i in range(len(bits) - len(FLAG) + 1):
        if np.array_equal(bits[i : i + len(FLAG)], FLAG):
            positions.append(i)
    return positions


def remove_bit_stuffing(bits):
    output = []
    ones = 0
    i = 0

    while i < len(bits):
        bit = int(bits[i])
        output.append(bit)
        i += 1

        if bit == 1:
            ones += 1
            if ones == 5:
                i += 1  # Ignora o zero inserido pelo transmissor.
                ones = 0
        else:
            ones = 0

    return np.array(output, dtype=np.uint8)


def bits_to_bytes(bits):
    data = bytearray()
    for i in range(0, len(bits), 8):
        byte = sum(
            int(bit) << position
            for position, bit in enumerate(bits[i : i + 8])
        )
        data.append(byte)
    return bytes(data)


def hdlc_frames(levels):
    bits = nrzi_decode(levels)
    flags = find_flags(bits)
    frames = []

    for start_flag, end_flag in zip(flags, flags[1:]):
        start = start_flag + len(FLAG)
        stuffed_bits = bits[start:end_flag]

        if len(stuffed_bits) == 0:
            continue

        frame_bits = remove_bit_stuffing(stuffed_bits)
        if len(frame_bits) >= 16 and len(frame_bits) % 8 == 0:
            frames.append(bits_to_bytes(frame_bits))

    return frames


def crc16_x25(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


def add_fcs(data):
    """Usado apenas para montar quadros nos testes."""
    return data + crc16_x25(data).to_bytes(2, "little")


def valid_fcs(frame):
    received_fcs = int.from_bytes(frame[-2:], "little")
    return crc16_x25(frame[:-2]) == received_fcs


def decode_address(address):
    callsign = "".join(chr(byte >> 1) for byte in address[:6]).rstrip()
    ssid = (address[6] >> 1) & 0x0F
    return f"{callsign}-{ssid}" if ssid else callsign


def parse_ax25(frame):
    """Interpreta um quadro UI AX.25 usado por APRS."""
    data = frame[:-2]  # Retira o FCS.
    addresses = []
    position = 0

    while True:
        address = data[position : position + 7]
        addresses.append(decode_address(address))
        position += 7
        if address[6] & 1:
            break

    return {
        "destination": addresses[0],
        "source": addresses[1],
        "digipeaters": addresses[2:],
        "control": data[position],
        "pid": data[position + 1],
        "information": data[position + 2 :],
    }
