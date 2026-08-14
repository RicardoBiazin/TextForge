"""Monta QAction, menus, barra de ferramentas e menu de contexto do registro.

Este e' o unico lugar do programa que sabe transformar um `Comando` (dado puro,
declarado em `acoes.py`) num `QAction` do Qt. Menus, barra de ferramentas, menu
de contexto do editor e a Command Palette saem todos daqui, da mesma lista.

Comando sem tratador aparece DESABILITADO. E' o que permite declarar o conjunto
completo desde o inicio sem enganar o usuario com item que nao faz nada.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu, QMenuBar, QToolBar, QWidget

from textforge import log_interno
from textforge.interface import acoes
from textforge.interface.acoes import REGISTRO, Comando

log = log_interno.obter(__name__)

Tratador = Callable[[], None]


class Vinculos:
    """Liga ids de comando a funcoes, e produz os QAction correspondentes."""

    def __init__(self, janela: QWidget) -> None:
        self._janela = janela
        self._tratadores: dict[str, Tratador] = {}
        self._qacoes: dict[str, QAction] = {}
        # Grupo -> QMenu da barra. GUARDAR ESTA REFERENCIA E' OBRIGATORIO, e nao
        # comodidade: no PySide6, `QAction.menu()` devolve um QMenu cujo tempo de
        # vida fica atrelado ao wrapper Python do QAction. Quando esse wrapper e'
        # coletado -- o que acontece assim que a funcao que iterou
        # `menuBar().actions()` retorna --, o shiboken DESTROI O OBJETO C++ do
        # menu, e a barra fica com um ponteiro pendurado. O sintoma e' um
        # "Internal C++ object (QMenu) already deleted" ao abrir o menu, e o
        # problema por baixo e' uso de memoria liberada.
        #
        # Mantendo aqui a referencia criada por `addMenu`, o wrapper vive enquanto
        # a janela viver, e ninguem precisa buscar o menu pela barra.
        self._menus: dict[str, QMenu] = {}
        self._conflitos_avisados = False

    # -- registro de tratadores --------------------------------------------

    def ligar(self, id_: str, tratador: Tratador) -> None:
        if REGISTRO.por_id(id_) is None:
            # Ligar um id que nao existe e' erro de programacao, e silenciar
            # isso significaria um comando que nunca aparece e ninguem nota.
            raise KeyError(f"id de comando inexistente: {id_}")
        self._tratadores[id_] = tratador
        qacao = self._qacoes.get(id_)
        if qacao is not None:
            qacao.setEnabled(True)

    def ligar_muitos(self, mapa: dict[str, Tratador]) -> None:
        for id_, tratador in mapa.items():
            self.ligar(id_, tratador)

    def tem_tratador(self, id_: str) -> bool:
        return id_ in self._tratadores

    def qacao(self, id_: str) -> QAction | None:
        return self._qacoes.get(id_)

    def acionar(self, id_: str) -> bool:
        """Executa um comando por id. E' o caminho da Command Palette."""
        tratador = self._tratadores.get(id_)
        if tratador is None:
            return False
        tratador()
        return True

    # -- construcao --------------------------------------------------------

    def _criar(self, comando: Comando) -> QAction:
        existente = self._qacoes.get(comando.id)
        if existente is not None:
            return existente

        qacao = QAction(comando.rotulo, self._janela)
        qacao.setObjectName(comando.id)
        if comando.atalho:
            sequencias = [QKeySequence(comando.atalho)]
            sequencias += [QKeySequence(a) for a in comando.atalhos_extra]
            qacao.setShortcuts(sequencias)
        if comando.dica:
            qacao.setToolTip(comando.dica)
            qacao.setStatusTip(comando.dica)
        if comando.alternavel:
            qacao.setCheckable(True)

        tratador = self._tratadores.get(comando.id)
        if tratador is None:
            qacao.setEnabled(False)
        else:
            qacao.triggered.connect(lambda _=False, t=tratador: t())

        self._qacoes[comando.id] = qacao
        return qacao

    def construir_barra_de_menu(self, barra: QMenuBar) -> None:
        if not self._conflitos_avisados:
            self._conflitos_avisados = True
            conflitos = acoes.conflitos_de_atalho()
            if conflitos:
                # Nao e' fatal em producao, mas e' um bug: o Qt escolhe um dos
                # comandos de forma imprevisivel e o outro nunca funciona.
                # O `teste_acoes.py` transforma isto em falha de teste.
                log.error("ATALHOS EM CONFLITO: %r", conflitos)

        barra.clear()
        self._menus.clear()
        for grupo in acoes.ORDEM_DOS_MENUS:
            comandos = REGISTRO.do_grupo(grupo)
            if not comandos:
                continue
            menu = barra.addMenu("&" + grupo if "&" not in grupo else grupo)
            self._menus[grupo] = menu
            self._preencher(menu, comandos)

    def menu(self, grupo: str) -> QMenu | None:
        """O QMenu de um grupo da barra ("Arquivo", "Linguagem"...).

        Use SEMPRE isto para chegar num menu da barra. Procurar em
        `menuBar().actions()` e chamar `acao.menu()` destroi o menu -- ver o
        comentario de `self._menus` no construtor.
        """
        return self._menus.get(grupo)

    def _preencher(self, menu: QMenu, comandos: list[Comando]) -> None:
        submenus: dict[str, QMenu] = {}
        for comando in comandos:
            alvo = menu
            if comando.submenu:
                sub = submenus.get(comando.submenu)
                if sub is None:
                    sub = menu.addMenu(comando.submenu)
                    submenus[comando.submenu] = sub
                alvo = sub
            if comando.separador_antes and alvo is menu:
                menu.addSeparator()
            alvo.addAction(self._criar(comando))

    def construir_barra_de_ferramentas(self, barra: QToolBar) -> None:
        barra.clear()
        grupo_anterior = ""
        for comando in REGISTRO.comandos:
            if not comando.na_barra:
                continue
            if grupo_anterior and comando.grupo != grupo_anterior:
                barra.addSeparator()
            grupo_anterior = comando.grupo
            barra.addAction(self._criar(comando))

    def menu_de_contexto(self, parent: QWidget) -> QMenu:
        """Menu de contexto do editor (requisito 20).

        Monta na hora, e nao uma vez, para os itens refletirem o estado atual
        (ha' selecao? ha' o que desfazer?) sem precisar de bookkeeping.
        """
        menu = QMenu(parent)
        grupo_anterior = ""
        submenus: dict[str, QMenu] = {}
        for comando in REGISTRO.comandos:
            if not comando.no_contexto:
                continue
            if grupo_anterior and comando.submenu != grupo_anterior:
                menu.addSeparator()
            grupo_anterior = comando.submenu
            alvo = menu
            if comando.submenu:
                sub = submenus.get(comando.submenu)
                if sub is None:
                    sub = menu.addMenu(comando.submenu)
                    submenus[comando.submenu] = sub
                alvo = sub
            alvo.addAction(self._criar(comando))
        return menu

    def registrar_atalhos_sem_menu(self) -> None:
        """Cria os QAction dos comandos que tem atalho mas nao aparecem em menu.

        Um QAction so' responde ao atalho se estiver anexado a um widget vivo. Os
        comandos que so' existem para a Command Palette precisam disto, senao o
        atalho deles simplesmente nao funciona -- falha silenciosa classica.
        """
        for comando in REGISTRO.comandos:
            if comando.atalho and comando.id not in self._qacoes:
                self._janela.addAction(self._criar(comando))

    def sincronizar_alternaveis(self, cfg: dict) -> None:
        """Marca os itens alternaveis conforme a configuracao."""
        for comando in REGISTRO.alternaveis():
            if not comando.chave_de_config:
                continue
            qacao = self._qacoes.get(comando.id)
            if qacao is None:
                continue
            valor = bool(cfg.get(comando.chave_de_config, False))
            # "Usar TAB de verdade" e' o inverso da chave 'usar_espacos'.
            if comando.id == "tab.usar_tab":
                valor = not valor
            qacao.setChecked(valor)

    def comandos_disponiveis(self) -> list[Comando]:
        """O que a Command Palette deve listar: declarado E com tratador."""
        return [c for c in acoes.para_palette() if c.id in self._tratadores]
