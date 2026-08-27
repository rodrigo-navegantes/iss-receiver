"""Demodulacao FM e AFSK1200 do sinal da ISS."""

import numpy as np
from scipy import signal


IQ_RATE = 240_000
AUDIO_RATE = 48_000
BAUD = 1_200
SAMPLES_PER_BIT = AUDIO_RATE // BAUD


def afsk_levels(iq):
    """Recebe IQ complex64 e gera candidatos de niveis AFSK."""

    # Demodulacao FM por diferenca de fase.
    fm = np.angle(iq[1:] * np.conj(iq[:-1]))
    fm -= np.mean(fm)

    # 240 kHz -> 48 kHz.
    audio = signal.resample_poly(fm, 1, 5)

    # Mantem os tons AFSK de 1200 e 2200 Hz.
    sos = signal.butter(
        4,
        [800, 2600],
        btype="bandpass",
        fs=AUDIO_RATE,
        output="sos",
    )
    audio = signal.sosfilt(sos, audio)

    # Mede a energia existente em cada tom durante o tempo de um bit.
    n = np.arange(len(audio))
    window = np.ones(SAMPLES_PER_BIT)

    mark = audio * np.exp(-2j * np.pi * 1200 * n / AUDIO_RATE)
    space = audio * np.exp(-2j * np.pi * 2200 * n / AUDIO_RATE)

    mark_energy = np.abs(signal.lfilter(window, [1], mark)) ** 2
    space_energy = np.abs(signal.lfilter(window, [1], space)) ** 2
    tone_difference = mark_energy - space_energy

    # Nao sabemos onde o primeiro bit comeca, entao testamos as 40 fases.
    first_sample = SAMPLES_PER_BIT - 1
    for phase in range(SAMPLES_PER_BIT):
        samples = tone_difference[first_sample + phase :: SAMPLES_PER_BIT]
        yield (samples >= 0).astype(np.uint8)
