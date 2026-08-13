"""Temas: cores da janela, do editor e do realce de sintaxe.

Vale aqui a mesma regra do `tema.py` do 2pc_1Kit: **nenhum widget e nenhum
provedor de linguagem guarda cor literal. Pede por NOME.** E' o que permite
trocar de tema com o programa aberto, e o que permite o usuario customizar as
cores do realce editando um JSON (requisito 28) em vez de recompilar.

Duas familias de nomes, e a diferenca importa:

  * CAMINHOS -- "editor.fundo", "janela.destaque". Sao as cores da interface.
    `tema.cor("editor.fundo")` devolve um QColor.
  * PAPEIS -- "comentario", "palavra_chave", "texto_literal". Sao os nomes que os
    provedores de linguagem citam. `tema.formato("comentario")` devolve um
    QTextCharFormat pronto, com cache.

Um tema do usuario em %APPDATA%\\TextForge\\temas\\<nome>.json faz MERGE sobre o
tema embutido do mesmo `tipo`. Ou seja, um tema do usuario pode declarar tres
papeis e herdar o resto -- ninguem precisa copiar 40 cores para mudar a cor dos
comentarios.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtGui import QColor, QFont, QPalette, QTextCharFormat

from textforge import configuracao, log_interno, recursos

log = log_interno.obter(__name__)

# Papel usado quando um provedor cita um nome que o tema nao declara. Um plugin
# que invente o papel "minha_coisa" pinta como texto normal, em vez de o
# realcador estourar no meio do paintEvent.
PAPEL_PADRAO = "texto"

EMBUTIDOS = ("escuro", "claro")


@dataclass
class Tema:
    nome: str
    tipo: str                                  # "claro" | "escuro"
    janela: dict[str, str] = field(default_factory=dict)
    editor: dict[str, str] = field(default_factory=dict)
    papeis: dict[str, dict[str, Any]] = field(default_factory=dict)
    _cache_de_formato: dict[str, QTextCharFormat] = field(default_factory=dict,
                                                          repr=False)
    _cache_de_cor: dict[str, QColor] = field(default_factory=dict, repr=False)

    # -- cores da interface -------------------------------------------------

    def cor(self, caminho: str) -> QColor:
        """Cor por caminho, ex.: cor("editor.linha_atual")."""
        emcache = self._cache_de_cor.get(caminho)
        if emcache is not None:
            return emcache

        secao, _, chave = caminho.partition(".")
        origem = {"janela": self.janela, "editor": self.editor}.get(secao, {})
        texto = origem.get(chave)
        if texto is None:
            log.warning("cor ausente no tema %r: %s", self.nome, caminho)
            texto = self.editor.get("texto") or "#000000"
        valor = QColor(texto)
        if not valor.isValid():
            log.warning("cor invalida no tema %r em %s: %r", self.nome,
                        caminho, texto)
            valor = QColor("#000000")
        self._cache_de_cor[caminho] = valor
        return valor

    @property
    def escuro(self) -> bool:
        return self.tipo == "escuro"

    # -- papeis de realce ---------------------------------------------------

    def formato(self, papel: str) -> QTextCharFormat:
        """QTextCharFormat de um papel. Com cache: e' chamado por token pintado."""
        emcache = self._cache_de_formato.get(papel)
        if emcache is not None:
            return emcache

        regras = self.papeis.get(papel)
        if regras is None:
            if papel != PAPEL_PADRAO:
                log.warning("papel ausente no tema %r: %s (pintando como texto)",
                            self.nome, papel)
            regras = self.papeis.get(PAPEL_PADRAO, {"cor": "#000000"})

        formato = QTextCharFormat()
        cor = QColor(regras.get("cor", ""))
        if cor.isValid():
            formato.setForeground(cor)
        fundo = QColor(regras.get("fundo", ""))
        if fundo.isValid():
            formato.setBackground(fundo)
        if regras.get("negrito"):
            formato.setFontWeight(QFont.Weight.Bold)
        if regras.get("italico"):
            formato.setFontItalic(True)
        if regras.get("sublinhado"):
            formato.setUnderlineStyle(
                QTextCharFormat.UnderlineStyle.SingleUnderline)
        if regras.get("ondulado"):
            # O sublinhado ondulado do corretor ortografico: e' o unico que o Qt
            # desenha de forma visivelmente diferente do sublinhado comum, e por
            # isso e' o que usamos para erro de sintaxe.
            formato.setUnderlineStyle(
                QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
            if cor.isValid():
                formato.setUnderlineColor(cor)
        self._cache_de_formato[papel] = formato
        return formato

    def tem_papel(self, papel: str) -> bool:
        return papel in self.papeis

    def papeis_declarados(self) -> set[str]:
        return set(self.papeis)

    # -- aparencia da janela ------------------------------------------------

    def qpalette(self) -> QPalette:
        """QPalette para a janela seguir o tema.

        Sem isto, no tema escuro os widgets padrao do Qt (menus, dialogos,
        campos) continuariam claros e a janela ficaria com metade em cada cor.
        """
        p = QPalette()
        fundo = self.cor("janela.fundo")
        texto = self.cor("janela.texto")
        campo = self.cor("janela.campo_fundo")
        destaque = self.cor("janela.destaque")

        for grupo in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            p.setColor(grupo, QPalette.ColorRole.Window, fundo)
            p.setColor(grupo, QPalette.ColorRole.WindowText, texto)
            p.setColor(grupo, QPalette.ColorRole.Base, campo)
            p.setColor(grupo, QPalette.ColorRole.AlternateBase, fundo)
            p.setColor(grupo, QPalette.ColorRole.Text, texto)
            p.setColor(grupo, QPalette.ColorRole.Button, fundo)
            p.setColor(grupo, QPalette.ColorRole.ButtonText, texto)
            p.setColor(grupo, QPalette.ColorRole.ToolTipBase, campo)
            p.setColor(grupo, QPalette.ColorRole.ToolTipText, texto)
            p.setColor(grupo, QPalette.ColorRole.Highlight, destaque)
            p.setColor(grupo, QPalette.ColorRole.HighlightedText,
                       self.cor("janela.texto_do_destaque"))
            p.setColor(grupo, QPalette.ColorRole.PlaceholderText,
                       self.cor("janela.texto_apagado"))
            p.setColor(grupo, QPalette.ColorRole.Link, destaque)

        apagado = self.cor("janela.texto_apagado")
        for papel in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                      QPalette.ColorRole.ButtonText):
            p.setColor(QPalette.ColorGroup.Disabled, papel, apagado)
        return p


# ---------------------------------------------------------------------------


def _mesclar(base: dict, novo: dict) -> dict:
    """Merge de um nivel. Um tema do usuario pode declarar so' o que muda."""
    saida = dict(base)
    for chave, valor in novo.items():
        if isinstance(saida.get(chave), dict) and isinstance(valor, dict):
            saida[chave] = {**saida[chave], **valor}
        else:
            saida[chave] = valor
    return saida


def _ler_json(caminho) -> dict | None:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("tema ilegivel em %s: %s", caminho, exc)
        return None
    return dados if isinstance(dados, dict) else None


def _de_dados(dados: dict) -> Tema:
    return Tema(nome=str(dados.get("nome", "?")),
                tipo=str(dados.get("tipo", "escuro")),
                janela=dict(dados.get("janela", {})),
                editor=dict(dados.get("editor", {})),
                papeis=dict(dados.get("papeis", {})))


def embutido(nome: str) -> Tema:
    dados = _ler_json(recursos.caminho("temas", f"{nome}.json"))
    if dados is None:
        # Ultimo recurso: um tema minimo em codigo. Sem isto, um recursos/
        # faltando no .exe deixaria o programa sem nenhuma cor para desenhar.
        log.error("tema embutido %r ausente; usando cores de emergencia", nome)
        claro = nome != "escuro"
        return Tema(nome="Emergencia",
                    tipo="claro" if claro else "escuro",
                    janela={"fundo": "#ffffff" if claro else "#1e1e1e",
                            "texto": "#000000" if claro else "#d4d4d4",
                            "texto_apagado": "#808080",
                            "campo_fundo": "#ffffff" if claro else "#252526",
                            "destaque": "#0a66c2",
                            "texto_do_destaque": "#ffffff"},
                    editor={"fundo": "#ffffff" if claro else "#1e1e1e",
                            "texto": "#000000" if claro else "#d4d4d4"},
                    papeis={"texto": {"cor": "#000000" if claro else "#d4d4d4"}})
    return _de_dados(dados)


def disponiveis() -> list[str]:
    """Temas embutidos mais os do usuario, sem repetir."""
    nomes = list(EMBUTIDOS)
    for arquivo in sorted(configuracao.pasta_de_temas().glob("*.json")):
        if arquivo.stem not in nomes:
            nomes.append(arquivo.stem)
    return nomes


def carregar(nome: str) -> Tema:
    """Carrega um tema por nome, com merge sobre o embutido do mesmo tipo.

    Procura primeiro em %APPDATA%\\TextForge\\temas. Um tema do usuario que
    declare `"tipo": "claro"` e tres papeis herda o resto do tema claro embutido.
    """
    do_usuario = configuracao.pasta_de_temas() / f"{nome}.json"
    if do_usuario.is_file():
        dados = _ler_json(do_usuario)
        if dados is not None:
            base = embutido("claro" if dados.get("tipo") == "claro" else "escuro")
            mesclado = _mesclar(
                {"nome": base.nome, "tipo": base.tipo, "janela": base.janela,
                 "editor": base.editor, "papeis": base.papeis}, dados)
            tema = _de_dados(mesclado)
            log.info("tema do usuario carregado: %s (%s)", nome, do_usuario)
            return tema
        log.warning("tema do usuario %r ilegivel; usando o embutido", nome)

    if nome in EMBUTIDOS:
        return embutido(nome)
    log.warning("tema %r nao encontrado; usando o escuro", nome)
    return embutido("escuro")


def windows_esta_escuro() -> bool:
    """True se o Windows esta' no modo escuro para aplicativos.

    Le' `AppsUseLightTheme` em HKCU. Zero = escuro. Fora do Windows, ou sem a
    chave (Windows anterior ao 10), devolve False -- claro e' o padrao seguro.
    """
    try:
        import winreg
        chave = (r"Software\Microsoft\Windows\CurrentVersion\Themes"
                 r"\Personalize")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave) as k:
            valor, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return int(valor) == 0
    except (ImportError, OSError, ValueError, TypeError):
        return False


def resolver(preferencia: str) -> Tema:
    """Traduz a configuracao 'tema' num tema concreto.

    "sistema" segue o Windows; qualquer outro nome manda.
    """
    if preferencia == "sistema":
        return embutido("escuro" if windows_esta_escuro() else "claro")
    return carregar(preferencia)
