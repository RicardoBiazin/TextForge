"""Configuracao: padroes, round-trip, config corrompido, portatil, recursos.

    .venv\\Scripts\\python.exe tests\\teste_configuracao.py

Nao toca no %APPDATA% de verdade: `appdata_temporario()` redireciona a variavel
de ambiente para uma pasta descartavel.
"""

from __future__ import annotations

import json
import pathlib
import sys

from ajudantes import (appdata_temporario, checa, checa_igual, pasta_temporaria,
                       resumir, secao)

from textforge import configuracao, recursos

# ---------------------------------------------------------------------------
secao("1 - padrao() e a fonte unica das chaves")

p = configuracao.padrao()
checa(isinstance(p, dict) and len(p) > 20, "padrao() devolve um dicionario cheio")

# Todas as opcoes que a tela de Configuracoes do requisito 30 tem de oferecer.
EXIGIDAS = [
    "tema", "fonte", "fonte_tamanho", "tabulacao", "usar_espacos",
    "quebra_de_linha", "autocomplete", "mostrar_minimapa", "mostrar_espacos",
    "mostrar_fim_de_linha", "restaurar_sessao", "autosave",
    "recuperacao_intervalo_s", "codificacao_padrao", "fim_de_linha_padrao",
]
ausentes = [c for c in EXIGIDAS if c not in p]
checa_igual(ausentes, [], "padrao() cobre todas as opcoes do requisito 30")

checa_igual(p["autosave"], "nao",
            "autosave vem DESLIGADO (nao alterar arquivo tecnico sem pedido)")
checa_igual(p["aparar_espaco_final"], False,
            "aparar espaco no fim vem desligado (.dat de largura fixa)")
checa_igual(p["plugins"]["ativos"], False, "plugins vem desligados")
checa(p["limite_linha_caracteres"] > 0 and p["limite_texto_mb"] > 0,
      "limites de arquivo grande tem valor positivo")
checa_igual(p["fim_de_linha_padrao"], "crlf", "EOL padrao e' CRLF no Windows")

# padrao() nao pode devolver o MESMO objeto duas vezes, senao um modulo que
# altera o dicionario contamina o proximo carregar().
a, b = configuracao.padrao(), configuracao.padrao()
a["tema"] = "mexido"
checa_igual(b["tema"], "sistema", "padrao() devolve um objeto novo a cada chamada")

# ---------------------------------------------------------------------------
secao("2 - round-trip de salvar/carregar")

with pasta_temporaria() as pasta:
    alvo = pasta / "config.json"
    cfg = configuracao.padrao()
    cfg["tema"] = "escuro"
    cfg["tabulacao"] = 2
    cfg["fonte"] = "Cascadia Mono"
    cfg["recentes"] = [r"C:\x\a.txt", r"C:\x\b com espaco.xml"]
    configuracao.salvar(cfg, alvo)
    checa(alvo.is_file(), "salvar() cria o arquivo")

    de_volta = configuracao.carregar(alvo)
    checa_igual(de_volta["tema"], "escuro", "tema sobrevive ao round-trip")
    checa_igual(de_volta["tabulacao"], 2, "tabulacao sobrevive ao round-trip")
    checa_igual(de_volta["recentes"], cfg["recentes"],
                "lista de recentes com espaco no caminho sobrevive")

    bruto = alvo.read_text(encoding="utf-8")
    checa("\\u" not in bruto, "grava sem escapar acentos (ensure_ascii=False)")
    checa(not (pasta / "config.json.novo").exists(),
          "nao deixa o temporario da gravacao para tras")

# ---------------------------------------------------------------------------
secao("3 - config corrompido nao impede o programa de abrir")

with pasta_temporaria() as pasta:
    ruim = pasta / "config.json"
    ruim.write_text("{isso nao e json,,,", encoding="utf-8")
    cfg = configuracao.carregar(ruim)
    checa_igual(cfg["tema"], "sistema", "JSON invalido cai no padrao, sem excecao")

    lista = pasta / "lista.json"
    lista.write_text('["nao", "e", "objeto"]', encoding="utf-8")
    cfg = configuracao.carregar(lista)
    checa_igual(cfg["tabulacao"], 4, "JSON valido mas do tipo errado cai no padrao")

    vazio = pasta / "vazio.json"
    vazio.write_bytes(b"")
    checa_igual(configuracao.carregar(vazio)["tema"], "sistema",
                "arquivo vazio cai no padrao")

# ---------------------------------------------------------------------------
secao("4 - chave nova nao apaga o resto (merge)")

with pasta_temporaria() as pasta:
    parcial = pasta / "config.json"
    # Um config gravado por uma versao antiga: tem 'tema', nao tem 'plugins'.
    parcial.write_text(json.dumps({"tema": "claro"}), encoding="utf-8")
    cfg = configuracao.carregar(parcial)
    checa_igual(cfg["tema"], "claro", "valor gravado vence o padrao")
    checa_igual(cfg["autosave"], "nao", "chave ausente no arquivo usa o padrao")
    checa("autorizados" in cfg["plugins"],
          "dicionario parcial no arquivo recebe merge com o padrao")

    # E o inverso: um sub-dicionario incompleto nao pode apagar irmaos.
    parcial.write_text(json.dumps({"plugins": {"ativos": True}}),
                       encoding="utf-8")
    cfg = configuracao.carregar(parcial)
    checa(cfg["plugins"]["ativos"] is True and "autorizados" in cfg["plugins"],
          "merge de um nivel preserva as chaves irmas do sub-dicionario")

# ---------------------------------------------------------------------------
secao("5 - pastas de dados em %APPDATA%")

with appdata_temporario() as base:
    dados = configuracao.pasta_de_dados()
    checa(dados.is_dir(), "pasta_de_dados() cria a pasta")
    checa_igual(dados.parent, base, "pasta_de_dados() fica dentro de %APPDATA%")
    checa_igual(dados.name, "TextForge", "a pasta se chama TextForge")

    for nome, funcao in (("recuperacao", configuracao.pasta_de_recuperacao),
                         ("temas", configuracao.pasta_de_temas),
                         ("linguagens", configuracao.pasta_de_linguagens)):
        p = funcao()
        checa(p.is_dir() and p.name == nome, f"pasta '{nome}' criada sob demanda")

    checa_igual(configuracao.caminho_log().name, "textforge.log",
                "caminho do log dentro da pasta de dados")
    checa_igual(configuracao.caminho_sessao().parent, dados,
                "sessao.json fica na pasta de dados")

# ---------------------------------------------------------------------------
secao("6 - config ao lado do executavel ganha (modo portatil)")

with appdata_temporario():
    padrao_esperado = configuracao.pasta_de_dados() / "config.json"
    checa_igual(configuracao.caminho_config(), padrao_esperado,
                "sem config portatil, usa o de %APPDATA%")

    ao_lado = configuracao.pasta_do_executavel() / "config.json"
    criado_aqui = False
    try:
        if not ao_lado.exists():
            ao_lado.write_text("{}", encoding="utf-8")
            criado_aqui = True
        checa_igual(configuracao.caminho_config(), ao_lado,
                    "config.json ao lado do executavel tem prioridade")
    finally:
        if criado_aqui:
            ao_lado.unlink(missing_ok=True)

# ---------------------------------------------------------------------------
secao("7 - recursos com e sem PyInstaller")

esperado_do_fonte = pathlib.Path(configuracao.__file__).resolve().parent.parent
checa_igual(recursos.raiz(), esperado_do_fonte,
            "rodando do fonte, a raiz de recursos e' a pasta do projeto")

alvo = recursos.caminho("temas", "escuro.json")
checa(alvo.parts[-3:] == ("recursos", "temas", "escuro.json"),
      "caminho() monta textforge/recursos/<sub>/<arquivo>")

# Simula o .exe no modo um-arquivo, onde os datas moram em sys._MEIPASS.
sys._MEIPASS = r"C:\Temp\_MEI12345"          # type: ignore[attr-defined]
try:
    checa_igual(recursos.raiz(), pathlib.Path(r"C:\Temp\_MEI12345"),
                "com sys._MEIPASS, a raiz de recursos passa a ser ele")
    checa_igual(recursos.listar("nao_existe"), [],
                "listar() de subpasta ausente devolve lista vazia, sem estourar")
finally:
    del sys._MEIPASS                          # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
secao("8 - lista de recentes")

cfg = configuracao.padrao()
cfg["recentes_maximo"] = 3
for caminho in (r"C:\a.txt", r"C:\b.txt", r"C:\c.txt", r"C:\d.txt"):
    configuracao.registrar_recente(cfg, caminho)
checa_igual(len(cfg["recentes"]), 3, "respeita o limite de recentes")
checa(cfg["recentes"][0].endswith("d.txt"), "o mais recente fica no topo")
checa(all("a.txt" not in r for r in cfg["recentes"]),
      "o mais antigo sai da lista")

configuracao.registrar_recente(cfg, r"C:\b.txt")
checa_igual(len([r for r in cfg["recentes"] if r.endswith("b.txt")]), 1,
            "reabrir um recente nao duplica a entrada")
checa(cfg["recentes"][0].endswith("b.txt"), "reabrir promove ao topo")

# No Windows o mesmo arquivo pode vir com caixa diferente do Explorer.
configuracao.registrar_recente(cfg, r"C:\B.TXT")
checa_igual(len([r for r in cfg["recentes"] if r.lower().endswith("b.txt")]), 1,
            "caixa diferente no caminho nao cria entrada duplicada")

sys.exit(resumir())
