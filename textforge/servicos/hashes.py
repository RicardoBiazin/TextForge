"""Hash de texto e de arquivo (requisito 25).

Duas funcoes, e a distincao entre elas importa mais do que parece:

  `de_texto`    o hash dos BYTES do texto na codificacao escolhida. Serve para
                conferir uma senha, um token, um trecho.
  `de_arquivo`  o hash do ARQUIVO NO DISCO, byte a byte, como qualquer outra
                ferramenta calcularia.

Elas nao dao o mesmo resultado, e isso NAO e' defeito: o arquivo tem BOM, tem CRLF e
tem a codificacao original; o texto em memoria tem "\\n" e nao tem BOM. Quem quer
comparar com o `certutil -hashfile` do Windows ou com um `.sha256` publicado quer o
do ARQUIVO. Por isso a janela usa o do arquivo quando nao ha' selecao, e a caixa de
resultado diz qual dos dois foi calculado.

`de_arquivo` le' em blocos e nunca carrega o arquivo inteiro na memoria -- e' o que
permite calcular o SHA-256 de um log de 1 GB sem o programa inchar.
"""

from __future__ import annotations

import hashlib
import os
import pathlib

# Nome exibido -> nome do hashlib. Ordem de utilidade: SHA-256 e' o padrao de fato
# hoje; MD5 e SHA-1 continuam aqui porque muito sistema legado ainda os publica.
ALGORITMOS: dict[str, str] = {
    "MD5": "md5",
    "SHA-1": "sha1",
    "SHA-256": "sha256",
    "SHA-512": "sha512",
}

POR_COMANDO = {
    "hash.md5": "MD5",
    "hash.sha1": "SHA-1",
    "hash.sha256": "SHA-256",
    "hash.sha512": "SHA-512",
}

# 1 MB por leitura. Grande o bastante para o custo por byte ser o do hash, pequeno
# o bastante para o cancelamento responder rapido.
BLOCO = 1024 * 1024


def _novo(algoritmo: str):
    nome = ALGORITMOS.get(algoritmo)
    if nome is None:
        raise ValueError(f"algoritmo desconhecido: {algoritmo!r}")
    return hashlib.new(nome)


def de_texto(texto: str, algoritmo: str, codec: str = "utf-8") -> str:
    """Hash dos bytes do texto. `errors="strict"` de proposito.

    Se o texto tem um caractere que nao existe na codificacao, substituir por "?" e
    seguir produziria um hash de um texto DIFERENTE do que esta' na tela -- um
    numero com cara de correto que nao confere com nada. Melhor levantar.
    """
    h = _novo(algoritmo)
    h.update(texto.encode(codec))
    return h.hexdigest()


def de_arquivo(caminho: str | os.PathLike[str], algoritmo: str,
               progresso=None, cancelar=None) -> str:
    """Hash do arquivo, em blocos.

    `progresso(lidos, total)` e `cancelar() -> bool` sao opcionais e existem para a
    `Tarefa`: um SHA-512 de 1 GB leva segundos, e travar a interface durante isso
    seria inaceitavel num editor.

    Devolve "" se foi cancelado.
    """
    alvo = pathlib.Path(caminho)
    total = alvo.stat().st_size
    h = _novo(algoritmo)
    lidos = 0
    with open(alvo, "rb") as f:
        while True:
            if cancelar is not None and cancelar():
                return ""
            bloco = f.read(BLOCO)
            if not bloco:
                break
            h.update(bloco)
            lidos += len(bloco)
            if progresso is not None:
                progresso(lidos, total)
    return h.hexdigest()


def formatar(valor: str, agrupado: bool = False) -> str:
    """O digest em minusculas; `agrupado` insere um espaco a cada 8 caracteres.

    O agrupamento existe para conferencia VISUAL: comparar dois SHA-512 de 128
    caracteres a olho, sem separador, e' como o erro passa despercebido.
    """
    valor = valor.lower()
    if not agrupado:
        return valor
    return " ".join(valor[i:i + 8] for i in range(0, len(valor), 8))
