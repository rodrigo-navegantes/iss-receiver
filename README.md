# Fluxo Python do receptor da ISS

```text
  GNU Radio File Sink: IQ complex64 a 240 ksps
                    |
                    v
             decode_iss.py
                    |
                    v
       separa por diferenca de fase FM
                    |
                    v
       reamostragem 240 kHz -> 48 kHz
                    |
                    v
 filtro passa-faixa de 800 a 2600 Hz
                    |
                    v
 detector AFSK: energia em 1200/2200 Hz
                    |
                    v
               NRZI -> bits
                    |
                    v
       flags HDLC -> bit unstuffing
                    |
                    v
          bytes AX.25 -> validar FCS
                    |
                    v
    origem, destino, repetidores e payload
```

## Executar

Depois de gravar o arquivo no GNU Radio:

```bash
python3 decode_iss.py nome_do_arquivo.c64 --sample-rate 240000
```

Para verificar o receptor com um pacote sintético:

```bash
python3 -m unittest -v test_receiver.py
```

O programa devolve apenas quadros cujo FCS AX.25 esteja correto.
