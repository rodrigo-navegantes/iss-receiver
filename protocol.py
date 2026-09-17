"""Codifica e decodifica NRZI, HDLC, FCS e quadros AX.25.

No sentido da recepção, o fluxo principal é:

    niveis NRZI
        -> bits HDLC
        -> localizacao das flags
        -> remocao do bit stuffing
        -> bytes do quadro
        -> verificacao do FCS
        -> campos AX.25

Ademais, as funcões de codificação são usadas para gerar o pacote de teste.
"""

import numpy as np
FLAG = np.array([0, 1, 1, 1, 1, 1, 1, 0], dtype=np.uint8)

def encode_address(callsign, last=False, ssid=0, repeated=False):
    """Monta os sete bytes de um endereco AX.25."""

    # Primeiros seis bits são dedicados para o callsign
    callsign = callsign.upper().ljust(6)

    # Cada caractere ASCII é deslocado um bit para a esquerda.
    address = bytearray(
        ord(character) << 1
        for character in callsign
    )

    # 0x60 coloca em 0 em C/H e R nos dois bits E 
    # O bit 0 vale 1 apenas no ultimo endereco
    ssid_byte = 0x60 | (ssid << 1) | int(last)

    # Em um endereco de repeater, coloca em 1 em C/H
    if repeated: ssid_byte |= 0x80

    address.append(ssid_byte)

    # bytes() deixa o endereço imútavel 
    return bytes(address)

def bytes_to_bits(data):
    """Converte bytes para bits na ordem LSB-first"""

    bits = [
        
        # Pega o bit que está na posição bit_position para um determinado byte
        (byte >> bit_position) & 1
        
        # O primeiro for percorre cada byte.
        for byte in data
        
        # O segundo percorre as posicoes 0 ate 7, com o bit menos significativo antes.
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

    # Considerei o nível original como zero
    level = 0
    levels = [level]

    for bit in bits:
        if bit == 0:
            # XOR com 1 inverte o valor atual 
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

    # Cria uma janela deslizante de oito bits para cada posicao possivel.
    # windows[0] = bits[0:8]
    # windows[1] = bits[1:9]
    # windows[2] = bits[2:10]
    # ...
    windows = np.lib.stride_tricks.sliding_window_view(bits, len(FLAG))

    matches = np.all(windows == FLAG, axis=1)

    # flatnonzero devolve os indices onde matches é verdadeiro.
    return np.flatnonzero(matches).tolist()


def remove_bit_stuffing(bits):
    """Remove os zeros inseridos pelo bit stuffing."""

    output = []
    ones = 0

    for bit in bits:
        bit = int(bit)

        # Depois 5 uns, esperariamos um zero
        if ones == 5:

            # 6 bits 1 significam que o quadro não é válido
            if bit != 0:
                return None

            ones = 0
            continue # esse zero não é adicionado no output

        output.append(bit)

        ones = ones + 1 if bit == 1 else 0

    return np.array(output, dtype=np.uint8)


def bits_to_bytes(bits):
    """Agrupa bits LSB-first em bytes."""

    data = []

    for start in range(0, len(bits), 8):
        byte = 0

        for bit_position, bit in enumerate(bits[start : start + 8]):

            # Desloca o bit para sua posicao dentro do byte.
            # OR acrescenta esse bit sem apagar os anteriores.
            byte |= int(bit) << bit_position

        data.append(byte)

    return bytes(data)


def hdlc_frames(levels):
    """Extrai quadros em bytes localizados entre as flags"""

    bits = nrzi_decode(levels)
    flags = find_flags(bits)

    frames = []

    for start_flag, end_flag in zip(flags, flags[1:]):

        # Soma len(FLAG) para pular os oito bits da flag inicial.
        stuffed = bits[start_flag + len(FLAG) : end_flag]

        # Flags consecutivas nao possuem dados entre elas.
        if len(stuffed) == 0: continue

        # Retira os zeros adicionados pelo transmissor.
        frame_bits = remove_bit_stuffing(stuffed)

        # None informa que a regra de bit stuffing foi violada.
        if frame_bits is None:
            continue

        if len(frame_bits) >= 16 and len(frame_bits) % 8 == 0:
            frames.append(bits_to_bytes(frame_bits))

    return frames

def crc16_x25(data):
    """Calcula o CRC-16/X-25 usado como FCS pelo AX.25."""

    # O valor inicial definido para este CRC é 0xFFFF (16 bits consecutivos de 1)
    crc = 0xFFFF

    for byte in data:

        # O novo byte é combinado com a parte baixa do registrador.
        crc ^= byte

        # Cada byte possui oito bits.
        for _ in range(8):

            # Verifica o bit menos significativo antes do deslocamento.
            if crc & 1:
                # 0x8408 e a forma refletida do polinomio usado pelo CRC-16/X-25.
                crc = (crc >> 1) ^ 0x8408
            else:
                # Quando o bit vale zero, ocorre apenas o deslocamento.
                crc >>= 1

    # O padrão exige uma inversao final dos 16 bits.
    return crc ^ 0xFFFF


def valid_fcs(frame):
    """Confere os dois bytes de FCS localizados no final do quadro."""

    if len(frame) < 3:
        return False

    # Os dois ultimos bytes foram transmitidos em ordem little-endian.
    received = int.from_bytes(frame[-2:], "little")

    # Calcula o CRC usando todos os bytes anteriores ao FCS.
    calculated = crc16_x25(frame[:-2])

    return received == calculated


def decode_address(address, repeater=False):
    """Converte os sete bytes de um endereco AX.25 em texto."""

    # ">> 1" restaura os valores ASCII originais.
    callsign = "".join(
        chr(byte >> 1)
        for byte in address[:6]
    ).rstrip()

    # O SSID ocupa quatro bits do setimo byte.
    ssid = (address[6] >> 1) & 0x0F

    # SSID zero normalmente nao é escrito.
    if ssid: callsign += f"-{ssid}"

    # Em digipeaters, o bit mais alto é chamado de H bit. O asterisco indica que esse repetidor ja retransmitiu o pacote.
    if repeater and address[6] & 0x80:
        callsign += "*"

    return callsign


def parse_ax25(frame):
    """Separa os campos de um quadro AX.25 UI."""

    # Retira o FCS
    data = frame[:-2]
    raw_addresses = []
    position = 0

    # Cada endereco ocupa exatamente sete bytes.
    while position + 7 <= len(data):
        address = data[position : position + 7]
        raw_addresses.append(address)
        position += 7

        # O bit 0 do setimo byte vale 1 no ultimo endereco
        if address[6] & 1: 
            break

    # Um quadro precisa ter pelo menos destino e origem. Depois dos enderecos tambem devem existir controle e PID.
    if len(raw_addresses) < 2 or position + 2 > len(data):
        raise ValueError("Quadro AX.25 incompleto")

    # Os dois primeiros enderecos sao destino e origem. A partir do terceiro, os enderecos pertencem a repeaters.
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
