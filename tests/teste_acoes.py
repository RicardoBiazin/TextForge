"""Registro de comandos: atalhos, rotulos, menus e a Command Palette.

    .venv\\Scripts\\python.exe tests\\teste_acoes.py

A verificacao que mais vale aqui e' a de atalho duplicado. Dois comandos no mesmo
atalho fazem o Qt escolher um deles de forma imprevisivel, e o outro simplesmente
para de funcionar -- sem erro, sem aviso, sem nada no log. E' o tipo de defeito
que so' aparece quando o usuario reclama que "esse atalho parou".

A primeira metade nao precisa de Qt: `acoes.py` e' dado puro, de proposito.
"""

from __future__ import annotations

import sys

from ajudantes import checa, checa_igual, preparar_qt, resumir, secao

from textforge.interface import acoes
from textforge.interface.acoes import REGISTRO

# ---------------------------------------------------------------------------
secao("1 - atalhos")

conflitos = acoes.conflitos_de_atalho()
if conflitos:
    detalhe = "; ".join(f"{a} usado por {', '.join(ids)}"
                        for a, ids in sorted(conflitos.items()))
    checa(False, f"nenhum atalho duplicado -- ENCONTRADOS: {detalhe}")
else:
    checa(True, "nenhum atalho duplicado no registro inteiro")

# Os atalhos tradicionais do requisito 3 tem de existir e estar onde se espera.
ESPERADOS = {
    "Ctrl+N": "arquivo.novo",
    "Ctrl+O": "arquivo.abrir",
    "Ctrl+S": "arquivo.salvar",
    "Ctrl+Shift+S": "arquivo.salvar_como",
    "Ctrl+F": "buscar.localizar",
    "Ctrl+H": "buscar.substituir",
    "Ctrl+G": "ir.linha",
    "Ctrl+Z": "editar.desfazer",
    "Ctrl+Y": "editar.refazer",
    "Ctrl+A": "editar.selecionar_tudo",
    "Ctrl+C": "editar.copiar",
    "Ctrl+V": "editar.colar",
    "Ctrl+X": "editar.recortar",
    "Ctrl+/": "editar.comentar",
    "Ctrl+Shift+P": "ferramentas.paleta",
    "Ctrl+P": "ferramentas.abertura_rapida",
}
por_atalho = {c.atalho: c.id for c in REGISTRO.comandos if c.atalho}
for atalho, id_esperado in ESPERADOS.items():
    checa_igual(por_atalho.get(atalho), id_esperado,
                f"{atalho} pertence a {id_esperado}")

# Ctrl+Alt+letra e' proibido: num teclado ABNT2, Ctrl+Alt E' o AltGr, e o atalho
# roubaria os caracteres da terceira camada do teclado do usuario.
com_altgr = [c.id for c in REGISTRO.comandos
             for a in (c.atalho, *c.atalhos_extra)
             if a.startswith("Ctrl+Alt+") and len(a) == len("Ctrl+Alt+") + 1]
checa_igual(com_altgr, [],
            "nenhum atalho Ctrl+Alt+letra (seria AltGr no teclado ABNT2)")

# ---------------------------------------------------------------------------
secao("2 - integridade do registro")

checa(len(REGISTRO.comandos) > 80,
      f"o registro tem {len(REGISTRO.comandos)} comandos declarados")

sem_rotulo = [c.id for c in REGISTRO.comandos if not c.rotulo.strip()]
checa_igual(sem_rotulo, [], "todo comando tem rotulo")

ids = REGISTRO.ids()
checa_igual(len(ids), len(set(ids)), "nenhum id de comando repetido")

fora_do_menu = [c.id for c in REGISTRO.comandos
                if c.grupo not in acoes.ORDEM_DOS_MENUS]
checa_igual(fora_do_menu, [], "todo comando cai num menu existente")

mal_formados = [c.id for c in REGISTRO.comandos
                if "." not in c.id or c.id != c.id.lower()]
checa_igual(mal_formados, [],
            "todo id segue o padrao 'grupo.acao' em minusculas")

# Um alternavel sem chave de config e' legitimo (estado do documento); o
# contrario nao: chave de config num comando nao alternavel seria um item que
# le' a preferencia e nunca mostra o estado dela.
erradas = [c.id for c in REGISTRO.comandos
           if c.chave_de_config and not c.alternavel]
checa_igual(erradas, [], "chave_de_config so' existe em comando alternavel")

from textforge import configuracao       # noqa: E402
padrao = configuracao.padrao()
chaves_invalidas = [c.chave_de_config for c in REGISTRO.alternaveis()
                    if c.chave_de_config and c.chave_de_config not in padrao]
checa_igual(chaves_invalidas, [],
            "toda chave_de_config existe mesmo no config padrao")

# ---------------------------------------------------------------------------
secao("3 - todos os menus do requisito 2 existem e tem conteudo")

for menu in ("Arquivo", "Editar", "Pesquisar", "Exibir", "Formatar",
             "Ferramentas", "Linguagem", "Ajuda"):
    quantos = len(REGISTRO.do_grupo(menu))
    checa(quantos > 0, f"menu {menu} tem {quantos} comandos")

checa_igual(list(acoes.ORDEM_DOS_MENUS)[:3], ["Arquivo", "Editar", "Pesquisar"],
            "a ordem dos menus comeca como o requisito 2 pede")

# ---------------------------------------------------------------------------
secao("4 - cobertura dos requisitos, por comando")

def existe(id_: str) -> bool:
    return REGISTRO.por_id(id_) is not None

REQUISITOS = [
    ("22 - manipulacao de linhas", [
        "linha.duplicar", "linha.excluir", "linha.ordenar",
        "linha.ordenar_sem_caixa", "linha.remover_duplicadas",
        "linha.remover_vazias", "linha.inverter", "linha.trim_inicio",
        "linha.trim_fim", "linha.prefixar", "linha.sufixar",
        "linha.mover_acima", "linha.mover_abaixo"]),
    ("23 - conversoes", [
        "conv.base64_codificar", "conv.base64_decodificar",
        "conv.url_codificar", "conv.url_decodificar",
        "conv.html_codificar", "conv.html_decodificar",
        "conv.json_escapar", "conv.json_desescapar"]),
    ("24 - hash", ["hash.md5", "hash.sha1", "hash.sha256", "hash.sha512"]),
    ("40 - conversao de caixa", [
        "caixa.maiusculas", "caixa.minusculas", "caixa.titulo",
        "caixa.camel", "caixa.pascal", "caixa.snake"]),
    ("5 - fim de linha", ["eol.crlf", "eol.lf", "eol.cr"]),
    ("25/26/10/17 - propriedades, tail, diff, hex", [
        "arquivo.propriedades", "ferramentas.acompanhar",
        "ferramentas.comparar", "ferramentas.hexadecimal"]),
]
for requisito, esperados in REQUISITOS:
    faltando = [i for i in esperados if not existe(i)]
    checa_igual(faltando, [], f"requisito {requisito} coberto")

# ---------------------------------------------------------------------------
secao("5 - Command Palette")

palette = acoes.para_palette()
checa(len(palette) > 80, f"a palette lista {len(palette)} comandos")
checa(all(not c.fora_da_palette for c in palette),
      "nenhum comando marcado 'fora_da_palette' aparece na lista")
checa(REGISTRO.por_id("ferramentas.paleta") not in palette,
      "a propria palette nao aparece dentro dela")

c = REGISTRO.por_id("formatar.documento")
checa_igual(c.caminho_na_palette, "Formatar > Formatar documento",
            "o caminho na palette inclui o menu")
c = REGISTRO.por_id("conv.base64_codificar")
checa_igual(c.caminho_na_palette, "Ferramentas > Conversoes > Base64: codificar",
            "o caminho na palette inclui o submenu")
c = REGISTRO.por_id("arquivo.abrir")
checa_igual(c.rotulo_limpo, "Abrir",
            "rotulo_limpo tira o '&' e as reticencias")

# ---------------------------------------------------------------------------
secao("6 - construcao dos QAction (precisa de Qt)")

if not preparar_qt():
    print("PULADO: PySide6 ausente; a parte de Qt nao foi verificada")
    sys.exit(resumir())

from PySide6.QtWidgets import QMainWindow, QToolBar         # noqa: E402

from textforge.interface.menus import Vinculos              # noqa: E402

janela = QMainWindow()
v = Vinculos(janela)

chamados: list[str] = []
v.ligar("arquivo.novo", lambda: chamados.append("novo"))
v.ligar("arquivo.salvar", lambda: chamados.append("salvar"))

v.construir_barra_de_menu(janela.menuBar())
titulos = [a.text().replace("&", "") for a in janela.menuBar().actions()]
checa_igual(titulos, list(acoes.ORDEM_DOS_MENUS),
            "a barra de menu tem os 8 menus, na ordem do requisito 2")

qa_novo = v.qacao("arquivo.novo")
checa(qa_novo is not None and qa_novo.isEnabled(),
      "comando COM tratador fica habilitado")
qa_sem = v.qacao("linha.ordenar")
checa(qa_sem is not None and not qa_sem.isEnabled(),
      "comando SEM tratador fica desabilitado (nao finge funcionar)")

qa_novo.trigger()
checa_igual(chamados, ["novo"], "acionar o QAction chama o tratador")

checa(v.acionar("arquivo.salvar"), "acionar() por id funciona (caminho da palette)")
checa_igual(chamados, ["novo", "salvar"], "e chamou o tratador certo")
checa(not v.acionar("linha.ordenar"),
      "acionar() de comando sem tratador devolve False, sem estourar")

try:
    v.ligar("id.que.nao.existe", lambda: None)
    checa(False, "ligar() um id inexistente deveria levantar KeyError")
except KeyError:
    checa(True, "ligar() um id inexistente levanta KeyError (erro de programacao)")

disponiveis = v.comandos_disponiveis()
checa_igual(sorted(c.id for c in disponiveis),
            ["arquivo.novo", "arquivo.salvar"],
            "a palette lista apenas os comandos com tratador ligado")

# Atalho de comando alternavel
qa_wrap = v.qacao("exibir.quebra_de_linha")
checa(qa_wrap is not None and qa_wrap.isCheckable(),
      "comando alternavel vira QAction checkable")

v.sincronizar_alternaveis({"quebra_de_linha": True, "usar_espacos": True,
                           "mostrar_minimapa": False})
checa(qa_wrap.isChecked(), "sincronizar_alternaveis marca conforme o config")
checa(not v.qacao("tab.usar_tab").isChecked(),
      "'Usar TAB de verdade' e' o inverso de 'usar_espacos'")

barra = QToolBar()
v.construir_barra_de_ferramentas(barra)
checa(len(barra.actions()) > 3,
      f"a barra de ferramentas recebeu {len(barra.actions())} itens")

menu_ctx = v.menu_de_contexto(janela)
rotulos = [a.text().replace("&", "") for a in menu_ctx.actions() if a.text()]
for esperado in ("Desfazer", "Recortar", "Copiar", "Colar", "Selecionar tudo"):
    checa(any(esperado in r for r in rotulos),
          f"menu de contexto tem '{esperado}' (requisito 20)")

# Atalho sem menu tem de existir como QAction, senao nao dispara.
v.registrar_atalhos_sem_menu()
com_atalho = [c for c in REGISTRO.comandos if c.atalho]
sem_qacao = [c.id for c in com_atalho if v.qacao(c.id) is None]
checa_igual(sem_qacao, [],
            "todo comando com atalho tem QAction (senao o atalho nao funciona)")

sys.exit(resumir())
