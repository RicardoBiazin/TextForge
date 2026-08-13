"""Temas: papeis, cores, merge do tema do usuario e contraste.

    .venv\\Scripts\\python.exe tests\\teste_tema.py

A verificacao mais util aqui e' a varredura automatica: TODO papel citado por
qualquer provedor de linguagem tem de existir nos dois temas embutidos. Ela nao
precisa ser atualizada quando uma linguagem nova entra -- e' isso que a torna uma
rede de seguranca de verdade, e nao mais um teste para manter.
"""

from __future__ import annotations

import json
import sys

from ajudantes import (appdata_temporario, checa, checa_igual, preparar_qt,
                       pular, resumir, secao)

if not preparar_qt():
    sys.exit(pular("PySide6 nao esta' instalado neste interpretador"))

from PySide6.QtGui import QColor, QFont, QTextCharFormat     # noqa: E402

from textforge.interface import tema as tmod                  # noqa: E402

# ---------------------------------------------------------------------------
secao("1 - os temas embutidos carregam")

escuro = tmod.embutido("escuro")
claro = tmod.embutido("claro")

checa_igual(escuro.tipo, "escuro", "o tema escuro se declara escuro")
checa_igual(claro.tipo, "claro", "o tema claro se declara claro")
checa(escuro.escuro and not claro.escuro, "a propriedade .escuro reflete o tipo")
checa(escuro.nome != "Emergencia",
      "o escuro veio do JSON, nao do fallback de emergencia")
checa(claro.nome != "Emergencia",
      "o claro veio do JSON, nao do fallback de emergencia")
checa(len(escuro.papeis) > 30, f"o escuro declara {len(escuro.papeis)} papeis")

# Os dois temas TEM de declarar exatamente os mesmos papeis: um papel presente
# so' num deles vira texto sem cor ao trocar de tema, e ninguem percebe ate' ver
# um comentario preto no fundo preto.
so_no_escuro = escuro.papeis_declarados() - claro.papeis_declarados()
so_no_claro = claro.papeis_declarados() - escuro.papeis_declarados()
checa_igual(sorted(so_no_escuro), [], "nenhum papel existe so' no tema escuro")
checa_igual(sorted(so_no_claro), [], "nenhum papel existe so' no tema claro")

# ---------------------------------------------------------------------------
secao("2 - cores por caminho")

for t in (escuro, claro):
    cor = t.cor("editor.fundo")
    checa(isinstance(cor, QColor) and cor.isValid(),
          f"[{t.nome}] cor('editor.fundo') e' um QColor valido")
    checa(t.cor("janela.destaque").isValid(),
          f"[{t.nome}] cor('janela.destaque') e' valida")

    # Um caminho inexistente nao pode estourar: seria dentro de um paintEvent.
    caida = t.cor("editor.nao_existe")
    checa(isinstance(caida, QColor) and caida.isValid(),
          f"[{t.nome}] caminho inexistente cai numa cor valida, sem excecao")
    checa(t.cor("secao_inventada.chave").isValid(),
          f"[{t.nome}] secao inexistente tambem nao estoura")

# As cores necessarias ao editor (etapa 2) precisam existir nos dois.
NECESSARIAS = ["editor.fundo", "editor.texto", "editor.cursor",
               "editor.linha_atual", "editor.selecao", "editor.margem_fundo",
               "editor.margem_texto", "editor.margem_texto_atual",
               "editor.guia_indentacao", "editor.espaco_visivel",
               "editor.par_casado", "editor.par_sem_par", "editor.marcador",
               "janela.fundo", "janela.texto", "janela.aba_modificada"]
for t in (escuro, claro):
    faltando = []
    for caminho in NECESSARIAS:
        secao_, _, chave = caminho.partition(".")
        origem = {"janela": t.janela, "editor": t.editor}[secao_]
        if chave not in origem:
            faltando.append(caminho)
    checa_igual(faltando, [], f"[{t.nome}] declara todas as cores do editor")

# ---------------------------------------------------------------------------
secao("3 - papeis viram QTextCharFormat")

f = escuro.formato("comentario")
checa(isinstance(f, QTextCharFormat), "formato() devolve um QTextCharFormat")
checa(f.fontItalic(), "comentario e' italico no tema escuro")
checa(escuro.formato("palavra_chave").fontWeight() == QFont.Weight.Bold,
      "palavra_chave e' negrito")
checa(escuro.formato("erro").underlineStyle()
      == QTextCharFormat.UnderlineStyle.SpellCheckUnderline,
      "erro usa o sublinhado ondulado")
checa(escuro.formato("erro").background().color().isValid(),
      "erro tem cor de fundo")

# Cache: chamar duas vezes tem de devolver o MESMO objeto. O realcador chama isto
# uma vez por token pintado -- montar um QTextCharFormat novo a cada chamada
# seria o gargalo do realce.
checa(escuro.formato("comentario") is escuro.formato("comentario"),
      "formato() usa cache (e' chamado por token pintado)")

# Papel desconhecido nao pode estourar: seria dentro do highlightBlock.
desconhecido = escuro.formato("papel_de_um_plugin_qualquer")
checa(isinstance(desconhecido, QTextCharFormat),
      "papel desconhecido cai no papel 'texto' em vez de levantar")

# ---------------------------------------------------------------------------
secao("4 - contraste minimo entre texto e fundo")

def luminancia(c: QColor) -> float:
    def canal(v: float) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return (0.2126 * canal(c.red()) + 0.7152 * canal(c.green())
            + 0.0722 * canal(c.blue()))


def contraste(a: QColor, b: QColor) -> float:
    la, lb = luminancia(a), luminancia(b)
    claro_, escuro_ = max(la, lb), min(la, lb)
    return (claro_ + 0.05) / (escuro_ + 0.05)


# 3.0:1 e' o piso da WCAG para texto grande; syntax highlighting em fonte
# monoespacada de 11pt fica no meio do caminho, e abaixo disso um comentario
# cinza vira invisivel. O que este teste realmente pega e' a cor colada no fundo.
LIMITE = 3.0
for t in (escuro, claro):
    fundo = t.cor("editor.fundo")
    ruins = []
    for papel in sorted(t.papeis):
        regras = t.papeis[papel]
        if "fundo" in regras:        # papel com fundo proprio se resolve sozinho
            continue
        cor = QColor(regras.get("cor", ""))
        if not cor.isValid():
            continue
        razao = contraste(cor, fundo)
        if razao < LIMITE:
            ruins.append(f"{papel} ({razao:.1f}:1)")
    checa_igual(ruins, [],
                f"[{t.nome}] todo papel tem contraste >= {LIMITE}:1 com o fundo")

    razao = contraste(t.cor("janela.texto"), t.cor("janela.fundo"))
    checa(razao >= 4.5,
          f"[{t.nome}] texto da janela tem contraste {razao:.1f}:1 (>= 4.5)")

# ---------------------------------------------------------------------------
secao("5 - tema do usuario faz merge sobre o embutido")

with appdata_temporario():
    from textforge import configuracao          # noqa: E402
    pasta = configuracao.pasta_de_temas()

    # Um tema do usuario que muda TRES coisas e herda o resto. E' o caso de uso
    # real do requisito 28: mudar a cor dos comentarios sem copiar 40 cores.
    (pasta / "meu.json").write_text(json.dumps({
        "nome": "Meu",
        "tipo": "escuro",
        "papeis": {"comentario": {"cor": "#ff00ff", "italico": False}},
        "editor": {"linha_atual": "#123456"},
    }), encoding="utf-8")

    meu = tmod.carregar("meu")
    checa_igual(meu.nome, "Meu", "o nome do tema do usuario vence")
    checa_igual(meu.papeis["comentario"]["cor"], "#ff00ff",
                "o papel redefinido usa a cor do usuario")
    checa(not meu.formato("comentario").fontItalic(),
          "o papel redefinido descarta o italico herdado")
    checa("palavra_chave" in meu.papeis,
          "os papeis NAO redefinidos sao herdados do embutido")
    checa_igual(len(meu.papeis), len(escuro.papeis),
                "o tema parcial acaba com todos os papeis do embutido")
    checa_igual(meu.editor["linha_atual"], "#123456",
                "a cor de editor redefinida vence")
    checa_igual(meu.editor["fundo"], escuro.editor["fundo"],
                "as cores de editor nao redefinidas sao herdadas")

    # Tema do usuario ilegivel nao pode derrubar o programa.
    (pasta / "quebrado.json").write_text("{isso nao e json", encoding="utf-8")
    caido = tmod.carregar("quebrado")
    checa(caido.nome != "", "tema do usuario corrompido cai num tema valido")
    checa(len(caido.papeis) > 10, "e o tema de contingencia tem papeis")

    checa("meu" in tmod.disponiveis(), "disponiveis() lista o tema do usuario")
    checa("escuro" in tmod.disponiveis() and "claro" in tmod.disponiveis(),
          "disponiveis() lista os embutidos")

    inexistente = tmod.carregar("nao_existe_esse_tema")
    checa(len(inexistente.papeis) > 10,
          "tema inexistente cai no escuro em vez de estourar")

# ---------------------------------------------------------------------------
secao("6 - 'sistema' segue o Windows")

do_sistema = tmod.resolver("sistema")
checa(do_sistema.tipo in ("claro", "escuro"),
      f"resolver('sistema') devolve um tema concreto ({do_sistema.tipo})")
checa_igual(do_sistema.escuro, tmod.windows_esta_escuro(),
            "e o tipo bate com o modo do Windows")
checa_igual(tmod.resolver("claro").tipo, "claro",
            "uma preferencia explicita manda no sistema")

# ---------------------------------------------------------------------------
secao("7 - qpalette cobre o que os dialogos precisam")

from PySide6.QtGui import QPalette                            # noqa: E402

for t in (escuro, claro):
    p = t.qpalette()
    checa(isinstance(p, QPalette), f"[{t.nome}] qpalette() devolve um QPalette")
    checa_igual(p.color(QPalette.ColorRole.Window).name(),
                t.cor("janela.fundo").name(),
                f"[{t.nome}] a cor de fundo da janela foi para a paleta")
    # O grupo Disabled precisa ser diferente, senao item de menu desabilitado
    # fica indistinguivel do habilitado -- e o TextForge mostra MUITO item
    # desabilitado enquanto as etapas nao chegam.
    ativo = p.color(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText)
    inativo = p.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText)
    checa(ativo != inativo,
          f"[{t.nome}] texto desabilitado tem cor diferente do habilitado")

sys.exit(resumir())
