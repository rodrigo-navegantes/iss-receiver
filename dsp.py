"""Detecta os tons AFSK usados pelo AX.25.

Fluxo deste modulo:

    audio a 48 kHz
        -> remocao do nivel DC
        -> filtro passa-faixa
        -> energia dos tons de 1200 e 2200 Hz
        -> comparacao entre as energias
        -> amostragem a 1200 baud
        -> niveis NRZI
"""

import numpy as np
from scipy import signal


AUDIO_SAMPLE_RATE = 48_000
BAUD = 1_200
MARK_FREQUENCY = 1_200 # 1
SPACE_FREQUENCY = 2_200 # 0
SAMPLES_PER_BIT = AUDIO_SAMPLE_RATE // BAUD


def prepare_audio(audio):
    """Remove o nivel DC e preserva a faixa dos tons AFSK."""

    # Garante que a entrada seja um vetor NumPy de f32
    audio = np.asarray(audio, dtype=np.float32)

    # Nao existe nada para filtrar em um vetor vazio.
    if len(audio) == 0: return audio

    # Remove o erro DC
    audio = audio - np.mean(audio)

    # Descarta vetores curtos demais
    if len(audio) < SAMPLES_PER_BIT: return audio

    # Aplicamos um filtro passa-faixa de na faixa de 500 a 3000 Hz que inclui os tons de 1200 e 2200 Hz.
    bandpass = signal.butter(
        4,
        [500, 3_000],
        btype="bandpass",
        fs=AUDIO_SAMPLE_RATE,
        output="sos",
    )

    # O mesmo filtro e aplicado para frente e para tras.
    # Dessa forma, o atraso de fase introduzido na ida e compensado na volta.
    return signal.sosfiltfilt(bandpass, audio)


def correlation_energy(audio, frequency):
    """Mede continuamente a energia de uma frequencia durante um bit."""

    sample = np.arange(len(audio))

    # Oscilador complexo na frequencia que queremos detectar.
    oscillator = np.exp(
        -2j * np.pi * frequency * sample / AUDIO_SAMPLE_RATE
    )

    # Multiplicar pelo oscilador desloca o tom procurado para perto de 0 Hz.
    mixed_audio = audio * oscillator

    # CHATGpt pediu para adicionar isto. Não sei por que...
    # Aplicamos um filtro digital para somar as ultimas 40 amostras
    correlation = signal.lfilter(
        np.ones(SAMPLES_PER_BIT),
        [1],
        mixed_audio,
    )

    return np.abs(correlation) ** 2


def tone_energies(audio):
    """Calcula as energias dos tons mark e space."""

    prepared_audio = prepare_audio(audio)

    mark = correlation_energy(prepared_audio, MARK_FREQUENCY)
    space = correlation_energy(prepared_audio, SPACE_FREQUENCY)

    return mark, space


def sample_levels(discriminator, phase):
    """Amostra uma hipotese de fase do relogio de 1200 baud"""

    # Comeca em phase e seleciona uma amostra a cada 40 valores.
    symbol_samples = discriminator[phase::SAMPLES_PER_BIT]

    # Resultado positivo significa mark; negativo significa space.
    return (symbol_samples >= 0).astype(np.uint8)


def afsk_levels(audio):
    """Gera hipoteses de niveis NRZI para o audio recebido"""

    mark, space = tone_energies(audio)

    # Aqui estou testando esta tres compensacoes simples para diferencas entre os dois tons.
    for space_gain in (1.0, 0.7, 1.4):

        # Novamente, valor positivo favorece mark; valor negativo favorece space.
        # O 1e-12 evita divisao por zero durante o silencio.
        discriminator = (mark - space_gain * space) / (
            mark + space_gain * space + 1e-12
        )

        # Existem 40 fases possiveis porque cada bit ocupa 40 amostras.
        for phase in range(SAMPLES_PER_BIT):
            yield sample_levels(discriminator, phase)
