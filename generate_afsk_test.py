"""Gera um pacote AX.25 em AFSK 1200 baud, grava pelo GNU Radio e decodifica com o main.py.

Uso: python3 generate_afsk_test.py "MENSAGEM"
"""

import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

from dsp import AUDIO_SAMPLE_RATE, MARK_FREQUENCY, SAMPLES_PER_BIT, SPACE_FREQUENCY
from protocol import FLAG, add_bit_stuffing, bytes_to_bits, crc16_x25, encode_address, nrzi_encode


# Troque pelo indicativo autorizado antes de uma transmissao real.
SOURCE = "PDQSAT"
DESTINATION = "APRS"
MESSAGE = b"OLA JOAO"


def make_frame(message=MESSAGE):
    """Monta o quadro AX.25 UI e acrescenta o FCS."""

    data = b"".join(
        [
            encode_address(DESTINATION),
            encode_address(SOURCE, last=True),
            bytes([0x03, 0xF0]),  # quadro UI, sem protocolo de camada 3
            message,
        ]
    )

    fcs = crc16_x25(data)
    return data + fcs.to_bytes(2, "little")


def make_packet_audio(message=MESSAGE):
    """Transforma o quadro em audio AFSK: preambulo, quadro com bit stuffing e flags finais."""

    frame = make_frame(message)

    bits = list(FLAG) * 60
    bits.extend(add_bit_stuffing(bytes_to_bits(frame)))
    bits.extend(list(FLAG) * 10)

    # O primeiro nivel devolvido pelo nrzi_encode e so a referencia, nao um bit.
    levels = nrzi_encode(bits)[1:]

    frequency_per_bit = np.where(levels == 1, MARK_FREQUENCY, SPACE_FREQUENCY)
    frequency_per_sample = np.repeat(frequency_per_bit, SAMPLES_PER_BIT)

    # Fase acumulada: sem saltos nas trocas de tom.
    phase = np.cumsum(2 * np.pi * frequency_per_sample / AUDIO_SAMPLE_RATE)

    return 0.35 * np.cos(phase)


def save_wav(path, audio):
    """Salva como WAV mono, PCM de 16 bits e 48 kHz."""

    samples = (np.clip(audio, -1, 1) * 32767).astype("<i2")

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(AUDIO_SAMPLE_RATE)
        wav.writeframes(samples.tobytes())


def main():
    os.chdir(Path(__file__).parent)

    # Latin-1 e a mesma codificacao que o main.py usa para mostrar a mensagem.
    message = sys.argv[1].encode("latin-1") if len(sys.argv) > 1 else MESSAGE

    silence = np.zeros(AUDIO_SAMPLE_RATE)
    pause = np.zeros(AUDIO_SAMPLE_RATE // 2)
    packet = make_packet_audio(message)

    audio = np.concatenate([silence, packet, pause, packet, pause, packet, silence])
    save_wav("afsk_ax25_test.wav", audio)
    print("Gerado: afsk_ax25_test.wav")

    # Compila uma copia do sinal.grc que grava em baofeng_rx.wav nesta pasta e sem o Audio
    # Sink (o som recebido voltaria para o microfone do Baofeng). No GRC nada muda.
    rx_wav = Path("baofeng_rx.wav").resolve()
    rx_wav.unlink(missing_ok=True)
    output = tempfile.mkdtemp()
    grc = Path("sinal.grc").read_text()
    grc = re.sub(r"(  id: audio_sink\n(?:  .*\n)*?    state: )enabled", r"\1disabled", grc)
    grc = re.sub(r"(  id: blocks_wavfile_sink\n(?:  .*\n)*?    file: ).*", lambda m: m.group(1) + str(rx_wav), grc)
    Path(output, "sinal.grc").write_text(grc)
    subprocess.run(["grcc", "-o", output, f"{output}/sinal.grc"], check=True, stdout=subprocess.DEVNULL)

    # Inicia a gravacao (o GNU Radio e o do python3 do sistema).
    flowgraph = next(Path(output).glob("*.py"))
    radio = subprocess.Popen(["/usr/bin/python3", str(flowgraph)])

    time.sleep(2)
    for n in (3, 2, 1):
        print(f"Segure o PTT: {n}")
        time.sleep(1)
    subprocess.run(["paplay", "afsk_ax25_test.wav"])
    time.sleep(2)

    # Mesmo efeito de um Ctrl+C: o GNU Radio para e fecha o WAV.
    radio.send_signal(signal.SIGINT)
    radio.wait()

    subprocess.run([sys.executable, "main.py", str(rx_wav)])


if __name__ == "__main__":
    main()