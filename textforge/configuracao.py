"""Carga e gravacao do config.json.

O config fica em %APPDATA%\\TextForge\\config.json, e nao ao lado do .exe: assim
sobrevive a troca do executavel e nao esbarra em permissao de Program Files.
Se houver um config.json ao lado do .exe, ele GANHA -- e' a forma de levar a
mesma configuracao pronta num pendrive, e e' o modo "portatil".

Regra deste modulo: `padrao()` e' a fonte unica de verdade das chaves. Nenhum
outro modulo inventa chave por conta propria; quem precisa de uma opcao nova
acrescenta aqui, com comentario dizendo o porque do valor padrao.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Any

from textforge import APP_ARQUIVO


def pasta_do_executavel() -> pathlib.Path:
    """Pasta onde o programa esta' instalado.

    Com PyInstaller, `sys.executable` e' o .exe; rodando do fonte, e' a pasta do
    pacote. Note que NAO e' sys._MEIPASS: no modo um-arquivo o _MEIPASS e' a
    pasta temporaria de descompactacao, que morre a cada execucao e onde um
    config.json portatil seria inutil.
    """
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).parent
    return pathlib.Path(__file__).resolve().parent.parent


def pasta_de_dados() -> pathlib.Path:
    """%APPDATA%\\TextForge, criada se preciso."""
    base = os.environ.get("APPDATA") or str(pathlib.Path.home())
    destino = pathlib.Path(base) / APP_ARQUIVO
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def caminho_config() -> pathlib.Path:
    ao_lado = pasta_do_executavel() / "config.json"
    if ao_lado.is_file():
        return ao_lado
    return pasta_de_dados() / "config.json"


def pasta_de_recuperacao() -> pathlib.Path:
    destino = pasta_de_dados() / "recuperacao"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def pasta_de_temas() -> pathlib.Path:
    """Temas do usuario. Tem prioridade sobre os embutidos em recursos/temas."""
    destino = pasta_de_dados() / "temas"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def pasta_de_linguagens() -> pathlib.Path:
    """Provedores de linguagem declarativos (.json) escritos pelo usuario.

    E' a via de extensao que NAO executa codigo de terceiros -- ao contrario da
    pasta de plugins, que so' funciona se explicitamente habilitada.
    """
    destino = pasta_de_dados() / "linguagens"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def caminho_log() -> pathlib.Path:
    return pasta_de_dados() / "textforge.log"


def caminho_erro() -> pathlib.Path:
    return pasta_de_dados() / "erro.log"


def caminho_sessao() -> pathlib.Path:
    return pasta_de_dados() / "sessao.json"


def padrao() -> dict[str, Any]:
    """Configuracao de primeira execucao.

    Os valores conservadores sao deliberados: este e' um editor de arquivos
    TECNICOS, onde uma alteracao automatica indesejada custa mais do que a
    comodidade que ela traria. Por isso autosave desligado, aparar espaco no fim
    desligado, e formatacao sempre manual.
    """
    return {
        # -- aparencia -----------------------------------------------------
        # "sistema" segue o tema do Windows; "claro" e "escuro" mandam nele.
        "tema": "sistema",
        "fonte": "Consolas",
        "fonte_tamanho": 11,
        # Multiplicador da altura da linha. 1.0 = metrica natural da fonte.
        "fonte_espacamento": 1.15,
        "mostrar_barra_de_ferramentas": True,
        "mostrar_minimapa": False,
        "mostrar_espacos": False,
        "mostrar_fim_de_linha": False,
        "mostrar_guias_de_indentacao": True,
        "coluna_limite": 0,          # 0 = nao desenhar a regua vertical
        "realcar_linha_atual": True,

        # -- edicao --------------------------------------------------------
        "tabulacao": 4,              # 2, 4 ou 8
        "usar_espacos": True,        # False = gravar TAB de verdade
        # Detectar a indentacao DO ARQUIVO ao abrir e usar a dele em vez desta.
        # Ligado por padrao: mexer na indentacao de um arquivo alheio e' a forma
        # mais facil de poluir um diff.
        "detectar_indentacao": True,
        "quebra_de_linha": False,    # word wrap
        "autocomplete": True,
        "fechar_pares": True,        # digitar ( insere )
        # Aparar espaco no fim das linhas ao salvar. DESLIGADO: arquivo .dat de
        # largura fixa e arquivo de dados posicionais dependem desse espaco.
        "aparar_espaco_final": False,

        # -- arquivos ------------------------------------------------------
        "codificacao_padrao": "utf-8",
        "codificacao_preferida_legado": "cp1252",   # fallback do detector
        "fim_de_linha_padrao": "crlf",              # crlf | lf | cr
        "restaurar_sessao": True,
        # "nao" | "ao_perder_foco" | "intervalo"
        "autosave": "nao",
        "autosave_intervalo_s": 300,
        # Copia de recuperacao (nao e' salvar no arquivo do usuario).
        "recuperacao_intervalo_s": 30,
        "recentes_maximo": 20,
        "recentes": [],
        # Pastas onde a copia de recuperacao NAO deve ser gravada, porque o
        # conteudo e' sensivel. A pasta de recuperacao fica em texto claro.
        "recuperacao_pastas_excluidas": [],

        # -- limites (ver 'Gargalo real' no plano) --------------------------
        # Acima disto o arquivo abre no visor de arquivo grande, somente leitura.
        "limite_texto_mb": 20,
        # Uma unica linha maior que isto tambem manda para o visor: o
        # QTextLayout e' quadratico dentro de um bloco, e um JS minificado de
        # 4 MB numa linha congela a interface.
        "limite_linha_caracteres": 20000,
        # Acima disto o realce de sintaxe e' desligado (com aviso na tela).
        "limite_realce_mb": 8,
        # Blocos maiores que isto nao sao realcados, mesmo em arquivo pequeno.
        "limite_realce_por_linha": 10000,
        "limite_xml_mb": 64,
        # Confirmar antes de copiar uma selecao gigante para a area de
        # transferencia: copiar 500 MB pode derrubar a sessao do Windows.
        "limite_copia_mb": 64,

        # -- janela (preenchido ao fechar) ----------------------------------
        "geometria": "",
        "estado_da_janela": "",

        # -- plugins --------------------------------------------------------
        # Desligado por padrao, e nao e' negociavel: um plugin e' codigo Python
        # com o mesmo poder do programa. Ligar exibe um aviso explicito.
        "plugins": {"ativos": False, "autorizados": {}},
    }


def carregar(caminho: pathlib.Path | None = None) -> dict[str, Any]:
    """Le o config.json sobre os valores padrao.

    Config corrompido nao impede o programa de abrir: segue com o padrao. Um
    editor que nao abre porque o proprio config quebrou e' pior que um editor
    com as preferencias zeradas.
    """
    cfg = padrao()
    alvo = caminho if caminho is not None else caminho_config()
    if alvo.is_file():
        try:
            lido = json.loads(alvo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg
        if isinstance(lido, dict):
            # Merge raso, com um nivel de merge para os dicionarios conhecidos:
            # um config antigo sem a chave "plugins.autorizados" nao deve
            # apagar o valor padrao dela.
            for chave, valor in lido.items():
                if (chave in cfg and isinstance(cfg[chave], dict)
                        and isinstance(valor, dict)):
                    cfg[chave] = {**cfg[chave], **valor}
                else:
                    cfg[chave] = valor
    return cfg


def salvar(cfg: dict[str, Any], caminho: pathlib.Path | None = None) -> pathlib.Path:
    alvo = caminho if caminho is not None else caminho_config()
    alvo.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(cfg, indent=2, ensure_ascii=False, sort_keys=True)
    # Gravacao em duas etapas tambem aqui: um desligamento no meio da escrita
    # deixaria o usuario sem preferencias na proxima abertura.
    temporario = alvo.with_name(alvo.name + ".novo")
    temporario.write_text(texto + "\n", encoding="utf-8")
    os.replace(temporario, alvo)
    return alvo


def registrar_recente(cfg: dict[str, Any], caminho: str | os.PathLike[str]) -> None:
    """Move `caminho` para o topo da lista de recentes, sem duplicar."""
    texto = str(pathlib.Path(caminho))
    recentes: list[str] = [r for r in cfg.get("recentes", [])
                           if r.lower() != texto.lower()]
    recentes.insert(0, texto)
    limite = max(1, int(cfg.get("recentes_maximo", 20)))
    cfg["recentes"] = recentes[:limite]
