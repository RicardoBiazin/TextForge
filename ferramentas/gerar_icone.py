"""Gera `textforge/recursos/icone.ico` e `splash.png` sem nenhuma dependencia.

    .venv\\Scripts\\python.exe ferramentas\\gerar_icone.py

Sem Pillow de proposito. O `.ico` e o `.png` sao VERSIONADOS (ver a nota no
.gitignore) justamente para o build funcionar numa maquina que nao tenha Pillow --
e um gerador que exigisse Pillow anularia isso. As duas coisas que ele precisa
saber sao simples: um `.ico` e' um cabecalho mais um DIB de 32 bits, e um `.png` e'
uma sequencia de chunks com os dados em zlib.

O desenho: fundo ardosia com um vinco quente na esquerda (a forja), tres linhas de
texto claras e uma barra curta destacada. Precisa funcionar a 16 px -- por isso
formas cheias e contraste alto, e nada de detalhe fino que vira sujeira nessa
escala.
"""

from __future__ import annotations

import pathlib
import struct
import sys
import zlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Paleta: as mesmas cores do tema escuro, para o icone nao destoar da janela.
FUNDO = (0x1E, 0x1F, 0x22)
BRASA = (0xD1, 0x9A, 0x66)
TEXTO = (0xD6, 0xD8, 0xDC)
DESTAQUE = (0x61, 0xAF, 0xEF)

TAMANHOS = (16, 24, 32, 48, 64, 128, 256)


def desenhar(n: int) -> list[list[tuple[int, int, int, int]]]:
    """Devolve a imagem como linhas de (R, G, B, A), de cima para baixo."""
    px = [[(0, 0, 0, 0)] * n for _ in range(n)]
    raio = max(1, n // 6)

    def dentro(x: int, y: int) -> bool:
        """Retangulo com cantos arredondados."""
        for cx, cy in ((raio, raio), (n - 1 - raio, raio),
                       (raio, n - 1 - raio), (n - 1 - raio, n - 1 - raio)):
            fora_x = (x < raio and cx == raio) or (x > n - 1 - raio and cx > raio)
            fora_y = (y < raio and cy == raio) or (y > n - 1 - raio and cy > raio)
            if fora_x and fora_y:
                return (x - cx) ** 2 + (y - cy) ** 2 <= raio * raio
        return True

    for y in range(n):
        for x in range(n):
            if dentro(x, y):
                px[y][x] = (*FUNDO, 255)

    def barra(topo: float, altura: float, esquerda: float, direita: float,
              cor: tuple[int, int, int]) -> None:
        y0, y1 = int(topo * n), max(int(topo * n) + 1, int((topo + altura) * n))
        x0, x1 = int(esquerda * n), max(int(esquerda * n) + 1, int(direita * n))
        for y in range(max(0, y0), min(n, y1)):
            for x in range(max(0, x0), min(n, x1)):
                if px[y][x][3]:
                    px[y][x] = (*cor, 255)

    # O vinco quente da esquerda: e' o que da' identidade ao icone a 16 px.
    barra(0.16, 0.68, 0.13, 0.22, BRASA)
    # Tres "linhas de texto", a do meio mais curta.
    barra(0.26, 0.09, 0.30, 0.84, TEXTO)
    barra(0.45, 0.09, 0.30, 0.66, TEXTO)
    barra(0.64, 0.09, 0.30, 0.78, DESTAQUE)
    return px


# ---------------------------------------------------------------------------
# PNG
# ---------------------------------------------------------------------------


def _chunk(tipo: bytes, dados: bytes) -> bytes:
    return (struct.pack(">I", len(dados)) + tipo + dados
            + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))


def png(px: list[list[tuple[int, int, int, int]]]) -> bytes:
    altura, largura = len(px), len(px[0])
    bruto = bytearray()
    for linha in px:
        bruto.append(0)                 # filtro 0 (None) por linha
        for r, g, b, a in linha:
            bruto += bytes((r, g, b, a))
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", largura, altura,
                                          8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(bytes(bruto), 9))
            + _chunk(b"IEND", b""))


# ---------------------------------------------------------------------------
# ICO
# ---------------------------------------------------------------------------


def _dib(px: list[list[tuple[int, int, int, int]]]) -> bytes:
    """BITMAPINFOHEADER + pixels BGRA + mascara AND.

    Duas armadilhas do formato, e as duas fazem o icone sumir se erradas:
    a altura no cabecalho e' o DOBRO (imagem + mascara), e as linhas vao de BAIXO
    para cima.
    """
    altura, largura = len(px), len(px[0])
    cabecalho = struct.pack("<IiiHHIIiiII", 40, largura, altura * 2, 1, 32, 0,
                            0, 0, 0, 0, 0)
    corpo = bytearray()
    for linha in reversed(px):
        for r, g, b, a in linha:
            corpo += bytes((b, g, r, a))
    # Mascara AND: zerada (o canal alfa ja' resolve), mas o padding para multiplo
    # de 4 bytes por linha e' obrigatorio.
    bytes_por_linha = ((largura + 31) // 32) * 4
    return bytes(cabecalho) + bytes(corpo) + b"\x00" * (bytes_por_linha * altura)


# A partir deste tamanho a entrada vai como PNG, e nao como DIB cru. Um 256x256
# em BGRA sao 256 KB; comprimido, ~1 KB. O Windows aceita entrada PNG desde o
# Vista, e sem isso o .ico passaria de 370 KB -- absurdo para um icone.
TAMANHO_PARA_PNG = 64


def ico(imagens: list[list[list[tuple[int, int, int, int]]]]) -> bytes:
    entradas = bytearray()
    dados = bytearray()
    deslocamento = 6 + 16 * len(imagens)
    for px in imagens:
        n = len(px)
        bruto = png(px) if n >= TAMANHO_PARA_PNG else _dib(px)
        # 256 e' gravado como 0: o campo de largura/altura tem UM byte so'.
        entradas += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32,
                                len(bruto), deslocamento)
        dados += bruto
        deslocamento += len(bruto)
    return struct.pack("<HHH", 0, 1, len(imagens)) + bytes(entradas) + bytes(dados)


def main() -> int:
    destino_ico = RAIZ / "textforge" / "recursos" / "icone.ico"
    destino_ico.parent.mkdir(parents=True, exist_ok=True)
    destino_ico.write_bytes(ico([desenhar(n) for n in TAMANHOS]))
    print(f"{destino_ico}  ({destino_ico.stat().st_size} bytes, "
          f"{len(TAMANHOS)} tamanhos)")

    # Splash do modo um-arquivo: retangulo largo com o icone a' esquerda.
    largura, altura = 420, 140
    marca = desenhar(96)
    tela = [[(*FUNDO, 255)] * largura for _ in range(altura)]
    ox, oy = 28, (altura - 96) // 2
    for y, linha in enumerate(marca):
        for x, cor in enumerate(linha):
            if cor[3]:
                tela[oy + y][ox + x] = cor
    # Barra de "carregando" a' direita do simbolo.
    for y in range(altura // 2 - 3, altura // 2 + 3):
        for x in range(150, 380):
            tela[y][x] = (*BRASA, 255) if x < 260 else (0x33, 0x36, 0x3B, 255)
    destino_png = RAIZ / "splash.png"
    destino_png.write_bytes(png(tela))
    print(f"{destino_png}  ({destino_png.stat().st_size} bytes, "
          f"{largura}x{altura})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
