"""Gera um pacote AX.25 em audio AFSK de 1200 baud.

Fluxo executado neste arquivo:

    mensagem
        -> quadro AX.25 com FCS
        -> bits HDLC com flags e bit stuffing
        -> niveis NRZI
        -> tons AFSK de 1200 e 2200 Hz
        -> amostras de audio
        -> arquivo WAV
"""

# A biblioteca wave escreve arquivos WAV sem exigir outra dependencia.
import wave

# Path facilita a criacao dos arquivos na mesma pasta deste script.
from pathlib import Path

# NumPy e usado para representar bits, frequencias e amostras de audio.
import numpy as np

# Constantes usadas tanto pelo transmissor de teste quanto pelo receptor.
from dsp import (
    AUDIO_SAMPLE_RATE,  # Taxa do audio: 48.000 amostras por segundo.
    BAUD,  # Taxa da transmissao: 1.200 bits por segundo.
    MARK_FREQUENCY,  # Frequencia mark: 1.200 Hz.
    SAMPLES_PER_BIT,  # Quantidade de amostras usada para representar um bit.
    SPACE_FREQUENCY,  # Frequencia space: 2.200 Hz.
)

# Funcoes da camada de protocolo usadas para montar o quadro AX.25.
from protocol import (
    FLAG,  # Padrao 01111110, correspondente ao byte 0x7E.
    add_bit_stuffing,  # Impede que os dados sejam confundidos com uma flag.
    bytes_to_bits,  # Converte os bytes para bits na ordem usada pelo HDLC.
    crc16_x25,  # Calcula o FCS usado para detectar erros no quadro.
    encode_address,  # Codifica um indicativo no formato de endereco AX.25.
    nrzi_encode,  # Converte os bits em mudancas ou permanencias de nivel.
)


# Identificador usado como origem do pacote de teste.
# Ele deve ser substituido pelo indicativo autorizado antes de uma transmissao real.
SOURCE = "PDQSAT"

# APRS e usado como destino porque o quadro possui o formato de um pacote APRS simples.
DESTINATION = "APRS"

# O prefixo b indica que a mensagem ja esta representada como bytes.
MESSAGE = b"TESTE PDQSAT - AFSK 1200"


def make_frame():
    """Monta os bytes do quadro AX.25 e acrescenta o FCS."""

    # O b"" representa uma sequencia de bytes inicialmente vazia.
    # join junta todos os campos abaixo sem inserir separadores entre eles.
    data = b"".join(
        [
            # O primeiro endereco de um quadro AX.25 e o destino.
            # last permanece False porque ainda existe o endereco de origem.
            encode_address(DESTINATION),

            # O segundo endereco e a origem.
            # last=True coloca o bit que indica o fim da lista de enderecos.
            encode_address(SOURCE, last=True),

            # 0x03 identifica um quadro UI, que nao exige conexao previa.
            # 0xF0 informa que os dados nao usam outro protocolo de camada superior.
            bytes([0x03, 0xF0]),

            # Campo de informacao transportado pelo quadro.
            MESSAGE,
        ]
    )

    # O FCS e calculado sobre todos os campos montados acima.
    fcs = crc16_x25(data)

    # AX.25 envia primeiro o byte menos significativo do FCS.
    # Por isso sao usados dois bytes na ordem little-endian.
    fcs_bytes = fcs.to_bytes(2, "little")

    # O quadro completo e formado pelos dados seguidos dos dois bytes de FCS.
    return data + fcs_bytes


def make_packet_audio():
    """Transforma um quadro AX.25 em amostras de audio AFSK."""

    # Neste ponto frame ainda e apenas uma sequencia de bytes.
    frame = make_frame()

    # Cada FLAG possui oito bits.
    # As 60 flags formam o preambulo usado para abrir o transmissor e sincronizar
    # o receptor. A 1.200 baud, esse preambulo dura aproximadamente 0,4 segundo.
    bits = list(FLAG) * 60

    # Cada byte do quadro e convertido para oito bits em ordem LSB-first.
    frame_bits = bytes_to_bits(frame)

    # Se surgirem cinco bits 1 consecutivos dentro do quadro, um bit 0 e inserido.
    # Isso evita que o conteudo seja confundido com a flag 01111110.
    stuffed_bits = add_bit_stuffing(frame_bits)

    # Os bits protegidos por bit stuffing sao colocados depois do preambulo.
    bits.extend(stuffed_bits)

    # Dez flags encerram o pacote e fornecem uma pequena margem ao receptor.
    bits.extend(list(FLAG) * 10)

    # A codificacao NRZI usa mudanca de nivel para representar bit 0 e
    # permanencia no mesmo nivel para representar bit 1.
    levels = nrzi_encode(bits)

    # Cada nivel NRZI e associado a uma das duas frequencias AFSK:
    # nivel 1 -> mark  -> 1200 Hz
    # nivel 0 -> space -> 2200 Hz
    frequency_per_bit = np.where(
        levels == 1,
        MARK_FREQUENCY,
        SPACE_FREQUENCY,
    )

    # A taxa do audio e 48 kHz e a taxa de bits e 1.200 baud.
    # Portanto, cada bit precisa ocupar 48000 / 1200 = 40 amostras.
    # A frequencia escolhida para cada bit e repetida nessas 40 amostras.
    frequency_per_sample = np.repeat(frequency_per_bit, SAMPLES_PER_BIT)

    # Para gerar uma senoide precisamos conhecer a fase de cada amostra.
    # O termo abaixo calcula quanto a fase avanca em cada instante.
    phase_step = 2 * np.pi * frequency_per_sample / AUDIO_SAMPLE_RATE

    # A soma acumulada mantem a fase continua quando ocorre uma troca de tom.
    # Sem isso poderiam aparecer saltos artificiais entre 1200 e 2200 Hz.
    phase = np.cumsum(phase_step)

    # O cosseno transforma a fase em uma forma de onda entre -1 e 1.
    # O fator 0.35 reduz o volume para diminuir o risco de saturar o microfone.
    audio = 0.35 * np.cos(phase)

    # O resultado ainda e um vetor NumPy, nao um arquivo WAV.
    return audio


def save_wav(path, audio):
    """Salva as amostras como WAV mono, PCM de 16 bits e 48 kHz."""

    # Garante que nenhuma amostra ultrapasse o intervalo permitido.
    limited_audio = np.clip(audio, -1, 1)

    # PCM de 16 bits usa valores inteiros aproximadamente entre -32768 e 32767.
    # O tipo <i2 significa inteiro com sinal, little-endian e dois bytes.
    samples = (limited_audio * 32767).astype("<i2")

    # "wb" significa abrir o arquivo para escrita em formato binario.
    with wave.open(str(path), "wb") as wav:
        # Um canal significa que o arquivo e mono.
        wav.setnchannels(1)

        # Duas bytes por amostra correspondem a 16 bits.
        wav.setsampwidth(2)

        # Informa ao arquivo que existem 48.000 amostras por segundo.
        wav.setframerate(AUDIO_SAMPLE_RATE)

        # WAV armazena bytes, por isso o vetor NumPy precisa ser convertido.
        wav.writeframes(samples.tobytes())


def main():
    """Monta a gravacao completa e cria os arquivos de teste."""

    # __file__ e o caminho deste script.
    # parent seleciona a pasta em que ele esta salvo.
    folder = Path(__file__).parent

    # Um segundo de silencio possui 48.000 amostras iguais a zero.
    # Esse tempo permite pressionar o PTT antes do primeiro pacote.
    silence = np.zeros(AUDIO_SAMPLE_RATE, dtype=np.float64)

    # A pausa entre pacotes dura meio segundo.
    pause = np.zeros(AUDIO_SAMPLE_RATE // 2, dtype=np.float64)

    # O mesmo pacote AFSK sera transmitido tres vezes.
    packet = make_packet_audio()

    # A repeticao aumenta a chance de pelo menos uma copia chegar corretamente.
    packets = [packet, pause, packet, pause, packet]

    # np.concatenate junta todos os vetores em um unico audio continuo:
    # silencio -> pacote -> pausa -> pacote -> pausa -> pacote -> silencio.
    audio = np.concatenate([silence, *packets, silence])

    # Caminho do arquivo que pode ser reproduzido perto do microfone do Baofeng.
    wav_path = folder / "afsk_ax25_test.wav"

    # Escreve o WAV mono de 48 kHz e 16 bits.
    save_wav(wav_path, audio)

    # Tambem e criada uma versao float32 sem cabecalho.
    # Ela pode ser usada em testes numericos ou em um File Source do GNU Radio.
    float_path = folder / "afsk_ax25_test.f32"
    audio.astype(np.float32).tofile(float_path)

    # Mensagem apresentada quando os dois arquivos forem criados.
    print("Gerados: afsk_ax25_test.wav e afsk_ax25_test.f32")


# Esta condicao executa main somente quando o arquivo e iniciado diretamente.
# Assim, importar uma funcao deste modulo nao gera arquivos automaticamente.
if __name__ == "__main__":
    main()
