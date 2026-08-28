"""Le um arquivo IQ do GNU Radio e procura pacotes AX.25 da ISS."""

import sys
import numpy as np
#from dsp      import 
#from protocol import 

iq             = np.fromfile(sys.argv[1], dtype=np.complex64)
decoded_frames = set() #evitar que o mesmo frame seja mostrado duas vezes

for levels in afsk_levels(iq):
    for frame in hdlc_frames(levels):
        if frame in decoded_frames or not valid_fcs(frame): continue

        decoded_frames.add(frame)
        packet = ax25(frame)

    # Imprimir informações dos frames

print(f"\nPacotes com FCS valido: {len(decoded_frames)}")