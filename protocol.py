"""Codifica e decodifica NRZI, HDLC, FCS e quadros AX.25."""

import numpy as np
FLAG = np.array([0, 1, 1, 1, 1, 1, 1, 0], dtype=np.uint8)

def encode_address(callsign, last=False, ssid=0, repeated=False):
    """Monta os sete bytes de um endereco AX.25."""

    callsign = callsign.upper().ljust(6)

    # Cada caractere e deslocado um bit para a esquerda.
    address = bytearray(
        ord(character) << 1
        for character in callsign
    )

    # O bit 0 vale 1 apenas no ultimo endereco.
    ssid_byte = 0x60 | (ssid << 1) | int(last)

    if repeated: ssid_byte |= 0x80

    address.append(ssid_byte)

    return bytes(address)

def bytes_to_bits(data):
    """Converte bytes para bits na ordem LSB-first"""

    bits = [
        (byte >> bit_position) & 1
        for byte in data
        for bit_position in range(8)
    ]

    return np.array(bits, dtype=np.uint8)


def add_bit_stuffing(bits):
    """Insere um zero depois de cinco bits 1 consecutivos."""

    stuffed = []
    ones = 0

    for bit in bits:
        bit = int(bit)

        stuffed.append(bit)

        ones = ones + 1 if bit else 0

        if ones == 5:
            stuffed.append(0)
            ones = 0

    return np.array(stuffed, dtype=np.uint8)


def nrzi_encode(bits):
    """Codifica bit 0 como transicao e bit 1 como permanencia de nivel."""

    level = 0
    levels = [level]

    for bit in bits:
        if bit == 0:
            level ^= 1

        levels.append(level)

    return np.array(levels, dtype=np.uint8)


def nrzi_decode(levels):
    """Converte niveis NRZI novamente em bits"""

    same_level = levels[1:] == levels[:-1]

    return same_level.astype(np.uint8)


def find_flags(bits):
    """Encontra os indices em que aparece a flag"""

    bits = np.asarray(bits, dtype=np.uint8)

    if len(bits) < len(FLAG): return []

    # Janelas de oito bits: windows[i] = bits[i:i+8]
    windows = np.lib.stride_tricks.sliding_window_view(bits, len(FLAG))

    matches = np.all(windows == FLAG, axis=1)

    return np.flatnonzero(matches).tolist()


def remove_bit_stuffing(bits):
    """Remove os zeros inseridos pelo bit stuffing."""

    output = []
    ones = 0

    for bit in bits:
        bit = int(bit)

        if ones == 5:

            # Seis bits 1 seguidos: quadro invalido.
            if bit != 0:
                return None

            ones = 0
            continue

        output.append(bit)

        ones = ones + 1 if bit == 1 else 0

    return np.array(output, dtype=np.uint8)


def bits_to_bytes(bits):
    """Agrupa bits LSB-first em bytes."""

    data = []

    for start in range(0, len(bits), 8):
        byte = 0

        for bit_position, bit in enumerate(bits[start : start + 8]):
            byte |= int(bit) << bit_position

        data.append(byte)

    return bytes(data)


def hdlc_frames(levels):
    """Extrai quadros em bytes localizados entre as flags"""

    bits = nrzi_decode(levels)
    flags = find_flags(bits)

    frames = []

    for start_flag, end_flag in zip(flags, flags[1:]):

        stuffed = bits[start_flag + len(FLAG) : end_flag]

        if len(stuffed) == 0: continue

        frame_bits = remove_bit_stuffing(stuffed)

        if frame_bits is None:
            continue

        if len(frame_bits) >= 16 and len(frame_bits) % 8 == 0:
            frames.append(bits_to_bytes(frame_bits))

    return frames

def crc16_x25(data):
    """Calcula o CRC-16/X-25 usado como FCS pelo AX.25."""

    crc = 0xFFFF

    for byte in data:
        crc ^= byte

        for _ in range(8):
            if crc & 1:
                # 0x8408: polinomio do CRC-16/X-25 na forma refletida.
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1

    return crc ^ 0xFFFF


def valid_fcs(frame):
    """Confere os dois bytes de FCS localizados no final do quadro."""

    if len(frame) < 3:
        return False

    received = int.from_bytes(frame[-2:], "little")

    calculated = crc16_x25(frame[:-2])

    return received == calculated


def decode_address(address, repeater=False):
    """Converte os sete bytes de um endereco AX.25 em texto."""

    callsign = "".join(
        chr(byte >> 1)
        for byte in address[:6]
    ).rstrip()

    ssid = (address[6] >> 1) & 0x0F

    if ssid: callsign += f"-{ssid}"

    # Asterisco: o digipeater ja retransmitiu o pacote.
    if repeater and address[6] & 0x80:
        callsign += "*"

    return callsign


def parse_ax25(frame):
    """Separa os campos de um quadro AX.25 UI."""

    data = frame[:-2]
    raw_addresses = []
    position = 0

    while position + 7 <= len(data):
        address = data[position : position + 7]
        raw_addresses.append(address)
        position += 7

        if address[6] & 1:
            break

    if len(raw_addresses) < 2 or position + 2 > len(data):
        raise ValueError("Quadro AX.25 incompleto")

    addresses = [
        decode_address(address, repeater=index >= 2)
        for index, address in enumerate(raw_addresses)
    ]

    return {
        "destination": addresses[0],
        "source": addresses[1],
        "digipeaters": addresses[2:],
        "control": data[position],
        "pid": data[position + 1],
        "information": data[position + 2 :],
    }