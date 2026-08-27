"""Testes do fluxo Python sem depender de uma passagem da ISS."""

from __future__ import annotations

import unittest

import numpy as np

from dsp import demodulate_afsk_candidates
from protocol import (
    HDLC_FLAG,
    append_fcs,
    decode_hdlc_frames,
    parse_ax25,
    validate_fcs,
)


def encode_address(callsign: str, ssid: int, last: bool) -> bytes:
    padded = callsign.upper().ljust(6)
    encoded = bytearray(ord(character) << 1 for character in padded)
    encoded.append(0x60 | ((ssid & 0x0F) << 1) | int(last))
    return bytes(encoded)


def bytes_to_lsb_bits(data: bytes) -> np.ndarray:
    return np.asarray(
        [(byte >> bit_index) & 1 for byte in data for bit_index in range(8)],
        dtype=np.uint8,
    )


def stuff_bits(bits: np.ndarray) -> np.ndarray:
    output: list[int] = []
    ones = 0
    for bit in bits:
        output.append(int(bit))
        if bit:
            ones += 1
            if ones == 5:
                output.append(0)
                ones = 0
        else:
            ones = 0
    return np.asarray(output, dtype=np.uint8)


def nrzi_encode(bits: np.ndarray, initial_level: int = 0) -> np.ndarray:
    level = initial_level
    levels: list[int] = []
    for bit in bits:
        if bit == 0:
            level ^= 1
        levels.append(level)
    return np.asarray(levels, dtype=np.uint8)


def synthetic_iq(frame: bytes, sample_rate: int = 240_000) -> np.ndarray:
    frame_bits = stuff_bits(bytes_to_lsb_bits(frame))
    preamble = np.tile(HDLC_FLAG, 12)
    postamble = np.tile(HDLC_FLAG, 4)
    line_bits = np.concatenate((preamble, frame_bits, postamble))
    levels = nrzi_encode(line_bits)

    afsk_rate = 48_000
    samples_per_symbol = afsk_rate // 1_200
    frequencies = np.where(levels == 1, 1_200.0, 2_200.0)
    frequencies = np.repeat(frequencies, samples_per_symbol)
    phase = 2 * np.pi * np.cumsum(frequencies) / afsk_rate
    audio = 0.65 * np.sin(phase)

    audio_240k = np.repeat(audio, sample_rate // afsk_rate)
    deviation_hz = 4_500.0
    rf_phase = 2 * np.pi * np.cumsum(audio_240k * deviation_hz) / sample_rate
    return np.exp(1j * rf_phase).astype(np.complex64)


def make_ui_frame() -> bytes:
    body = b"".join(
        (
            encode_address("APRS", 0, last=False),
            encode_address("TEST", 1, last=True),
            b"\x03\xF0Hello ISS",
        )
    )
    return append_fcs(body)


class ReceiverTests(unittest.TestCase):
    def test_fcs_and_ax25_parser(self) -> None:
        frame = make_ui_frame()
        self.assertTrue(validate_fcs(frame))
        packet = parse_ax25(frame)
        self.assertEqual(packet.destination, "APRS")
        self.assertEqual(packet.source, "TEST-1")
        self.assertEqual(packet.information, b"Hello ISS")

    def test_complete_dsp_and_protocol_flow(self) -> None:
        expected = make_ui_frame()
        iq = synthetic_iq(expected)
        recovered: set[bytes] = set()
        for _phase, levels, _confidence in demodulate_afsk_candidates(iq):
            recovered.update(decode_hdlc_frames(levels))
        self.assertIn(expected, recovered)


if __name__ == "__main__":
    unittest.main()
