"""Le um WAV AFSK e procura pacotes AX.25."""

import sys

import numpy as np
from scipy.io import wavfile

from dsp import AUDIO_SAMPLE_RATE, afsk_levels
from protocol import hdlc_frames, parse_ax25, valid_fcs


def read_audio(filename):
    """Le um WAV mono de 48 kHz e normaliza as amostras."""

    sample_rate, audio = wavfile.read(filename)

    if sample_rate != AUDIO_SAMPLE_RATE:
        raise ValueError(
            f"O WAV possui {sample_rate} Hz; o receptor espera "
            f"{AUDIO_SAMPLE_RATE} Hz."
        )

    # Se o arquivo for estereo, transforma os dois canais em um canal mono.
    if audio.ndim == 2:
        audio = audio.mean(axis=1)

    audio = audio.astype(np.float32)

    # Normalização das amostras
    peak = np.max(np.abs(audio)) if len(audio) else 0
    if peak > 0:
        audio /= peak

    return audio


def decode_audio(audio):
    """Retorna os quadros com FCS valido e o total de candidatos HDLC."""

    decoded_frames = set()
    candidate_frames = 0

    for levels in afsk_levels(audio):

        for frame in hdlc_frames(levels):
            candidate_frames += 1

            if valid_fcs(frame):
                decoded_frames.add(frame)

    return decoded_frames, candidate_frames


def print_frame(frame):
    """Mostra os campos principais de um quadro AX.25."""

    packet = parse_ax25(frame)
    route = " -> ".join(
        [packet["source"], *packet["digipeaters"], packet["destination"]]
    )

    print(f"\nRota: {route}")
    print(f"Controle: 0x{packet['control']:02X}")
    print(f"PID: 0x{packet['pid']:02X}")
    print("Informacao:", packet["information"].decode("latin-1"))


def main():
    """Executa o receptor para o WAV informado na linha de comando."""

    audio = read_audio(sys.argv[1])
    decoded_frames, candidate_frames = decode_audio(audio)

    for frame in decoded_frames:
        print_frame(frame)

    print(f"\nCandidatos HDLC encontrados: {candidate_frames}")
    print(f"Pacotes com FCS valido: {len(decoded_frames)}")


if __name__ == "__main__":
    main()
