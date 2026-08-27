"""Le um arquivo IQ do GNU Radio e procura pacotes AX.25 da ISS."""

import sys
import numpy as np
from dsp      import afsk_levels
from protocol import hdlc_frames, parse_ax25, valid_fcs

iq             = np.fromfile(sys.argv[1], dtype=np.complex64)
decoded_frames = set()

for levels in afsk_levels(iq):
    for frame in hdlc_frames(levels):
        if frame in decoded_frames or not valid_fcs(frame): continue

        decoded_frames.add(frame)
        packet = parse_ax25(frame)
        route = " -> ".join(
            [packet["source"], *packet["digipeaters"], packet["destination"]]
        )

        print(f"\nRota: {route}")
        print(f"Controle: 0x{packet['control']:02X}")
        print(f"PID: 0x{packet['pid']:02X}")
        print("Informacao:", packet["information"].decode("latin-1"))

print(f"\nPacotes com FCS valido: {len(decoded_frames)}")