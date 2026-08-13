"""Registro unico de comandos.

Todo comando do TextForge e' declarado UMA vez aqui. Dessa lista sao *gerados*:

    barra de menu, barra de ferramentas, menu de contexto do editor,
    atalhos de teclado e a Command Palette (Ctrl+Shift+P).

Sem isto, cada comando novo teria de ser cadastrado em cinco lugares, e a palette
ficaria permanentemente desatualizada em relacao aos menus -- e' o destino de
quase todo editor que ganha uma palette depois dos menus.

Este modulo NAO importa Qt de proposito. Ele e' dado puro, o que permite
verificar em teste que nao ha' atalho duplicado, que todo comando tem rotulo e
que todo comando cai num menu existente, sem subir uma QApplication. Quem
transforma isso em QAction e QMenu e' o `interface/menus.py`.

Comandos sem tratador ligado aparecem DESABILITADOS no menu e nao aparecem na
palette. E' o que permite declarar o conjunto inteiro desde o inicio: o usuario
ve o que o programa vai ter, sem clicar em nada que finja funcionar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# -- menus da barra, na ordem em que aparecem (requisito 2) -----------------
ARQUIVO = "Arquivo"
EDITAR = "Editar"
PESQUISAR = "Pesquisar"
EXIBIR = "Exibir"
FORMATAR = "Formatar"
FERRAMENTAS = "Ferramentas"
LINGUAGEM = "Linguagem"
AJUDA = "Ajuda"

ORDEM_DOS_MENUS = (ARQUIVO, EDITAR, PESQUISAR, EXIBIR, FORMATAR, FERRAMENTAS,
                   LINGUAGEM, AJUDA)


@dataclass(frozen=True)
class Comando:
    """Um comando declarado. Dado puro: nada aqui sabe o que e' um QAction."""

    id: str                       # "arquivo.abrir" -- estavel, usado em config
    rotulo: str                   # "Abrir..."
    grupo: str                    # um dos menus acima
    atalho: str = ""              # "Ctrl+O"; vazio = sem atalho
    atalhos_extra: tuple[str, ...] = ()   # alternativas (F3 e Ctrl+G, p.ex.)
    dica: str = ""                # tooltip e descricao na palette
    submenu: str = ""             # agrupa dentro do menu ("Conversoes")
    separador_antes: bool = False
    na_barra: bool = False        # tambem na barra de ferramentas
    no_contexto: bool = False     # tambem no menu de contexto do editor
    alternavel: bool = False      # checkable (Word Wrap, Minimapa...)
    # Chave do config que este comando alterna. E' o que deixa o menu refletir a
    # configuracao sem codigo extra por item. Nem todo alternavel tem uma: o
    # "Acompanhar alteracoes" e' estado do DOCUMENTO aberto, nao preferencia.
    chave_de_config: str = ""
    # Fora da palette: comandos que so' fazem sentido pelo menu (ex.: Sair) ou
    # que sao gerados dinamicamente (a lista de recentes).
    fora_da_palette: bool = False

    def __post_init__(self) -> None:
        if not self.id or not self.rotulo:
            raise ValueError(f"comando sem id ou rotulo: {self!r}")
        if self.grupo not in ORDEM_DOS_MENUS:
            raise ValueError(f"comando {self.id} em menu inexistente: {self.grupo}")
        # A recíproca sim e' obrigatoria: uma chave de config so' faz sentido em
        # comando alternavel, e o contrario seria um item de menu que le' a
        # configuracao mas nunca mostra o estado dela.
        if self.chave_de_config and not self.alternavel:
            raise ValueError(f"comando {self.id} tem chave_de_config "
                             "mas nao e' alternavel")

    @property
    def rotulo_limpo(self) -> str:
        """Rotulo sem '&' e sem '...', para a palette e para a busca."""
        return self.rotulo.replace("&", "").removesuffix("...")

    @property
    def caminho_na_palette(self) -> str:
        """'Formatar > XML > Formatar documento' -- contexto na lista plana."""
        partes = [self.grupo]
        if self.submenu:
            partes.append(self.submenu)
        partes.append(self.rotulo_limpo)
        return " > ".join(partes)


@dataclass
class Registro:
    """Os comandos, na ordem de declaracao."""

    comandos: list[Comando] = field(default_factory=list)
    _por_id: dict[str, Comando] = field(default_factory=dict)

    def registrar(self, comando: Comando) -> Comando:
        if comando.id in self._por_id:
            raise ValueError(f"comando duplicado: {comando.id}")
        self.comandos.append(comando)
        self._por_id[comando.id] = comando
        return comando

    def por_id(self, id_: str) -> Comando | None:
        return self._por_id.get(id_)

    def do_grupo(self, grupo: str) -> list[Comando]:
        return [c for c in self.comandos if c.grupo == grupo]

    def alternaveis(self) -> list[Comando]:
        return [c for c in self.comandos if c.alternavel]

    def ids(self) -> list[str]:
        return [c.id for c in self.comandos]


REGISTRO = Registro()


def _c(*args, **kwargs) -> Comando:
    """Atalho de declaracao: registra e devolve."""
    return REGISTRO.registrar(Comando(*args, **kwargs))


# ===========================================================================
# Arquivo
# ===========================================================================
_c("arquivo.novo", "&Novo", ARQUIVO, "Ctrl+N", na_barra=True,
   dica="Cria um documento vazio numa aba nova")
_c("arquivo.abrir", "&Abrir...", ARQUIVO, "Ctrl+O", na_barra=True,
   dica="Abre um ou mais arquivos")
_c("arquivo.abrir_pasta", "Abrir &pasta...", ARQUIVO,
   dica="Mostra uma pasta no painel Arquivos")
_c("arquivo.reabrir_como", "&Reabrir como", ARQUIVO, submenu="Reabrir como",
   dica="Reabre o arquivo atual com outra codificacao, ou em hexadecimal")
_c("arquivo.salvar", "&Salvar", ARQUIVO, "Ctrl+S", na_barra=True,
   separador_antes=True, dica="Grava o arquivo preservando codificacao e fim de linha")
_c("arquivo.salvar_como", "Salvar &como...", ARQUIVO, "Ctrl+Shift+S",
   dica="Grava com outro nome")
# Sequencia de duas teclas, ao estilo do VS Code, e nao Ctrl+Alt+S: num teclado
# ABNT2, Ctrl+Alt E' o AltGr, e o atalho roubaria a terceira camada da tecla.
_c("arquivo.salvar_todos", "Salvar &todos", ARQUIVO, "Ctrl+K, Ctrl+S",
   dica="Grava todas as abas modificadas")
_c("arquivo.recarregar", "Rec&arregar do disco", ARQUIVO, "F5",
   dica="Descarta as alteracoes e le' o arquivo de novo")
_c("arquivo.fechar", "&Fechar aba", ARQUIVO, "Ctrl+W", separador_antes=True,
   dica="Fecha a aba atual")
_c("arquivo.fechar_todas", "Fechar todas as abas", ARQUIVO, "Ctrl+Shift+W")
_c("arquivo.propriedades", "&Propriedades...", ARQUIVO, separador_antes=True,
   dica="Tamanho, linhas, caracteres, codificacao, datas (requisito 25)")
_c("arquivo.abrir_local", "Abrir local do arquivo", ARQUIVO,
   dica="Mostra o arquivo no Explorer do Windows")
_c("arquivo.sair", "Sai&r", ARQUIVO, "Alt+F4", separador_antes=True,
   fora_da_palette=True)

# ===========================================================================
# Editar
# ===========================================================================
_c("editar.desfazer", "&Desfazer", EDITAR, "Ctrl+Z", na_barra=True,
   no_contexto=True)
_c("editar.refazer", "&Refazer", EDITAR, "Ctrl+Y", atalhos_extra=("Ctrl+Shift+Z",),
   na_barra=True, no_contexto=True)
_c("editar.recortar", "Re&cortar", EDITAR, "Ctrl+X", separador_antes=True,
   no_contexto=True)
_c("editar.copiar", "C&opiar", EDITAR, "Ctrl+C", no_contexto=True)
_c("editar.colar", "Co&lar", EDITAR, "Ctrl+V", no_contexto=True)
_c("editar.excluir", "&Excluir", EDITAR, "Del", no_contexto=True)
_c("editar.selecionar_tudo", "Selecionar &tudo", EDITAR, "Ctrl+A",
   no_contexto=True)
_c("editar.copiar_linha", "Copiar linha", EDITAR, "Ctrl+Shift+C",
   separador_antes=True, dica="Copia a linha inteira sem precisar selecionar")

# -- linhas (requisito 22) --------------------------------------------------
LINHAS = "Linhas"
_c("linha.duplicar", "Duplicar linha", EDITAR, "Ctrl+D", submenu=LINHAS,
   no_contexto=True)
_c("linha.excluir", "Excluir linha", EDITAR, "Ctrl+Shift+K", submenu=LINHAS,
   no_contexto=True)
_c("linha.mover_acima", "Mover linha para cima", EDITAR, "Alt+Up",
   submenu=LINHAS, no_contexto=True)
_c("linha.mover_abaixo", "Mover linha para baixo", EDITAR, "Alt+Down",
   submenu=LINHAS, no_contexto=True)
_c("linha.ordenar", "Ordenar linhas", EDITAR, submenu=LINHAS)
_c("linha.ordenar_sem_caixa", "Ordenar ignorando maiusculas", EDITAR,
   submenu=LINHAS)
_c("linha.inverter", "Inverter a ordem das linhas", EDITAR, submenu=LINHAS)
_c("linha.remover_duplicadas", "Remover linhas duplicadas", EDITAR,
   submenu=LINHAS)
_c("linha.remover_vazias", "Remover linhas vazias", EDITAR, submenu=LINHAS)
_c("linha.trim_inicio", "Aparar espaco no inicio das linhas", EDITAR,
   submenu=LINHAS)
_c("linha.trim_fim", "Aparar espaco no fim das linhas", EDITAR, submenu=LINHAS)
_c("linha.prefixar", "Inserir texto no inicio de cada linha...", EDITAR,
   submenu=LINHAS)
_c("linha.sufixar", "Inserir texto no fim de cada linha...", EDITAR,
   submenu=LINHAS)

# -- caixa (requisito 40) ---------------------------------------------------
CAIXA = "Converter caixa"
_c("caixa.maiusculas", "MAIUSCULAS", EDITAR, "Ctrl+Shift+U", submenu=CAIXA,
   no_contexto=True)
_c("caixa.minusculas", "minusculas", EDITAR, "Ctrl+Shift+L", submenu=CAIXA,
   no_contexto=True)
_c("caixa.titulo", "Cada Palavra Em Maiuscula", EDITAR, submenu=CAIXA)
_c("caixa.camel", "camelCase", EDITAR, submenu=CAIXA)
_c("caixa.pascal", "PascalCase", EDITAR, submenu=CAIXA)
_c("caixa.snake", "snake_case", EDITAR, submenu=CAIXA)

_c("editar.comentar", "Comentar / descomentar", EDITAR, "Ctrl+/",
   separador_antes=True, no_contexto=True,
   dica="Usa o comentario da linguagem do arquivo (requisito 21)")

# -- indentacao -------------------------------------------------------------
INDENTACAO = "Indentacao"
_c("indentar.aumentar", "Aumentar indentacao", EDITAR, "Tab",
   submenu=INDENTACAO, fora_da_palette=True)
_c("indentar.diminuir", "Diminuir indentacao", EDITAR, "Shift+Tab",
   submenu=INDENTACAO, fora_da_palette=True)
_c("indentar.tab_para_espacos", "Converter TAB em espacos", EDITAR,
   submenu=INDENTACAO)
_c("indentar.espacos_para_tab", "Converter espacos em TAB", EDITAR,
   submenu=INDENTACAO)

# ===========================================================================
# Pesquisar
# ===========================================================================
_c("buscar.localizar", "&Localizar...", PESQUISAR, "Ctrl+F", na_barra=True)
_c("buscar.proximo", "Localizar &proximo", PESQUISAR, "F3")
_c("buscar.anterior", "Localizar &anterior", PESQUISAR, "Shift+F3")
_c("buscar.substituir", "&Substituir...", PESQUISAR, "Ctrl+H")
_c("buscar.em_arquivos", "Pesquisar em ar&quivos...", PESQUISAR, "Ctrl+Shift+F",
   separador_antes=True, dica="Pesquisa numa pasta, com filtros de extensao")
_c("buscar.contar", "Contar ocorrencias da selecao", PESQUISAR,
   separador_antes=True)
_c("buscar.selecionar_ocorrencias", "Selecionar todas as ocorrencias",
   PESQUISAR, "Ctrl+Shift+A")
_c("ir.linha", "Ir para &linha...", PESQUISAR, "Ctrl+G", separador_antes=True)
_c("ir.par", "Ir para o par correspondente", PESQUISAR, "Ctrl+]",
   dica="Salta entre ( ), [ ], { } e entre tags XML/HTML")

# -- marcadores (requisito 40) ----------------------------------------------
MARCADORES = "Marcadores"
_c("marca.alternar", "Alternar marcador", PESQUISAR, "Ctrl+F2",
   submenu=MARCADORES)
_c("marca.proximo", "Proximo marcador", PESQUISAR, "F2", submenu=MARCADORES)
_c("marca.anterior", "Marcador anterior", PESQUISAR, "Shift+F2",
   submenu=MARCADORES)
_c("marca.limpar", "Remover todos os marcadores", PESQUISAR,
   submenu=MARCADORES)

# ===========================================================================
# Exibir
# ===========================================================================
_c("exibir.quebra_de_linha", "&Quebra automatica de linha", EXIBIR, "Alt+Z",
   alternavel=True, chave_de_config="quebra_de_linha")
_c("exibir.espacos", "Mostrar &espacos e TAB", EXIBIR, alternavel=True,
   chave_de_config="mostrar_espacos")
_c("exibir.fim_de_linha", "Mostrar &CR/LF", EXIBIR, alternavel=True,
   chave_de_config="mostrar_fim_de_linha")
_c("exibir.guias", "Mostrar guias de indentacao", EXIBIR, alternavel=True,
   chave_de_config="mostrar_guias_de_indentacao")
_c("exibir.linha_atual", "Realcar a linha atual", EXIBIR, alternavel=True,
   chave_de_config="realcar_linha_atual")
_c("exibir.minimapa", "&Minimapa", EXIBIR, alternavel=True,
   chave_de_config="mostrar_minimapa", separador_antes=True)
_c("exibir.barra_de_ferramentas", "Barra de &ferramentas", EXIBIR,
   alternavel=True, chave_de_config="mostrar_barra_de_ferramentas")
_c("exibir.painel_arquivos", "Painel &Arquivos", EXIBIR, "Ctrl+Shift+E")
_c("exibir.painel_estrutura", "Painel &Estrutura", EXIBIR, "Ctrl+Shift+O")
_c("exibir.painel_problemas", "Painel &Problemas", EXIBIR, "Ctrl+Shift+M")
_c("exibir.aumentar_zoom", "Aumentar &zoom", EXIBIR, "Ctrl+=",
   atalhos_extra=("Ctrl++",), separador_antes=True)
_c("exibir.diminuir_zoom", "Diminuir zoom", EXIBIR, "Ctrl+-")
_c("exibir.zoom_normal", "Zoom normal", EXIBIR, "Ctrl+0")
_c("exibir.tela_cheia", "Tela cheia", EXIBIR, "F11", separador_antes=True)

# -- dobras (requisito 12) --------------------------------------------------
DOBRAS = "Recolher"
_c("dobra.alternar", "Recolher / expandir", EXIBIR, "Ctrl+Shift+[",
   submenu=DOBRAS)
_c("dobra.tudo", "Recolher tudo", EXIBIR, "Ctrl+K Ctrl+0", submenu=DOBRAS)
_c("dobra.nada", "Expandir tudo", EXIBIR, "Ctrl+K Ctrl+J", submenu=DOBRAS)

# ===========================================================================
# Formatar
# ===========================================================================
# Shift+Alt+F, e nao Ctrl+Shift+F (que e' "pesquisar em arquivos" no Notepad++ e
# no VS Code) nem Ctrl+Alt+F: num teclado ABNT2, Ctrl+Alt E' o AltGr, e qualquer
# atalho Ctrl+Alt+letra briga com os caracteres da terceira camada.
_c("formatar.documento", "&Formatar documento", FORMATAR, "Shift+Alt+F",
   na_barra=True,
   dica="Formata o arquivo inteiro segundo a linguagem detectada")
_c("formatar.selecao", "Formatar &selecao", FORMATAR, no_contexto=True)
_c("formatar.compactar", "&Compactar (minificar)", FORMATAR)
_c("formatar.validar", "&Validar", FORMATAR, "Ctrl+Shift+V",
   separador_antes=True,
   dica="Verifica a sintaxe e mostra linha, coluna e motivo do erro")
# F8, como o "proximo problema" do VS Code. Ctrl+Shift+E fica com o painel
# Arquivos, que e' o uso consagrado dele.
_c("formatar.ir_para_erro", "Ir para o erro", FORMATAR, "F8")
_c("formatar.ordenar_chaves", "Formatar ordenando as chaves", FORMATAR,
   separador_antes=True, dica="Somente JSON: ordena as propriedades")

# -- fim de linha e codificacao ---------------------------------------------
FIM_DE_LINHA = "Fim de linha"
_c("eol.crlf", "Windows (CRLF)", FORMATAR, submenu=FIM_DE_LINHA)
_c("eol.lf", "Unix (LF)", FORMATAR, submenu=FIM_DE_LINHA)
_c("eol.cr", "Mac classico (CR)", FORMATAR, submenu=FIM_DE_LINHA)

CODIFICACAO = "Codificacao"
_c("codificacao.escolher", "Converter para...", FORMATAR, submenu=CODIFICACAO,
   dica="Avisa antes de converter, listando os caracteres que seriam perdidos")

TABULACAO = "Tabulacao"
_c("tab.2", "2 espacos", FORMATAR, submenu=TABULACAO)
_c("tab.4", "4 espacos", FORMATAR, submenu=TABULACAO)
_c("tab.8", "8 espacos", FORMATAR, submenu=TABULACAO)
_c("tab.usar_tab", "Usar TAB de verdade", FORMATAR, submenu=TABULACAO,
   alternavel=True, chave_de_config="usar_espacos")

# ===========================================================================
# Ferramentas
# ===========================================================================
_c("ferramentas.comparar", "&Comparar arquivos...", FERRAMENTAS,
   dica="Abre dois arquivos lado a lado com as diferencas destacadas")
_c("ferramentas.hexadecimal", "Ver em &hexadecimal", FERRAMENTAS,
   dica="Offset, bytes e ASCII. Somente leitura")
_c("ferramentas.acompanhar", "&Acompanhar alteracoes (tail)", FERRAMENTAS,
   alternavel=True, chave_de_config="",
   dica="Mostra automaticamente as linhas novas de um .log")
_c("ferramentas.tabela_csv", "Modo &tabela (CSV)", FERRAMENTAS,
   dica="Alterna entre o texto e a grade")

CONVERSOES = "Conversoes"
_c("conv.base64_codificar", "Base64: codificar", FERRAMENTAS, submenu=CONVERSOES)
_c("conv.base64_decodificar", "Base64: decodificar", FERRAMENTAS,
   submenu=CONVERSOES)
_c("conv.url_codificar", "URL: codificar", FERRAMENTAS, submenu=CONVERSOES)
_c("conv.url_decodificar", "URL: decodificar", FERRAMENTAS, submenu=CONVERSOES)
_c("conv.html_codificar", "HTML: codificar", FERRAMENTAS, submenu=CONVERSOES)
_c("conv.html_decodificar", "HTML: decodificar", FERRAMENTAS, submenu=CONVERSOES)
_c("conv.json_escapar", "JSON: escapar", FERRAMENTAS, submenu=CONVERSOES)
_c("conv.json_desescapar", "JSON: desescapar", FERRAMENTAS, submenu=CONVERSOES)

HASHES = "Hash"
_c("hash.md5", "MD5", FERRAMENTAS, submenu=HASHES)
_c("hash.sha1", "SHA-1", FERRAMENTAS, submenu=HASHES)
_c("hash.sha256", "SHA-256", FERRAMENTAS, submenu=HASHES)
_c("hash.sha512", "SHA-512", FERRAMENTAS, submenu=HASHES)

_c("ferramentas.paleta", "&Paleta de comandos", FERRAMENTAS, "Ctrl+Shift+P",
   separador_antes=True, fora_da_palette=True)
_c("ferramentas.abertura_rapida", "Abertura &rapida", FERRAMENTAS, "Ctrl+P",
   dica="Procura um arquivo por nome nos recentes e na pasta aberta")
_c("ferramentas.configuracoes", "Confi&guracoes...", FERRAMENTAS, "Ctrl+,",
   separador_antes=True)

# ===========================================================================
# Linguagem  (os itens de linguagem em si sao gerados do registro de
# provedores; aqui ficam so' os comandos fixos)
# ===========================================================================
_c("linguagem.detectar", "&Detectar automaticamente", LINGUAGEM,
   dica="Volta a decidir a linguagem pela extensao e pelo conteudo")
_c("linguagem.texto", "Texto sem formatacao", LINGUAGEM)

# ===========================================================================
# Ajuda
# ===========================================================================
_c("ajuda.atalhos", "Lista de &atalhos", AJUDA, "F1")
_c("ajuda.abrir_log", "Abrir o &log de diagnostico", AJUDA,
   dica="Abre %APPDATA%\\TextForge\\textforge.log numa aba")
_c("ajuda.sobre", "&Sobre o TextForge", AJUDA, separador_antes=True)


# ---------------------------------------------------------------------------


def conflitos_de_atalho() -> dict[str, list[str]]:
    """Atalhos usados por mais de um comando.

    Vazio e' o unico resultado aceitavel -- dois comandos no mesmo atalho fazem o
    Qt escolher um deles de forma imprevisivel, e o outro simplesmente nao
    funciona sem nenhum aviso. O teste falha se este dicionario nao estiver vazio.
    """
    usados: dict[str, list[str]] = {}
    for c in REGISTRO.comandos:
        for atalho in (c.atalho, *c.atalhos_extra):
            if atalho:
                usados.setdefault(atalho, []).append(c.id)
    return {a: ids for a, ids in usados.items() if len(ids) > 1}


def para_palette() -> list[Comando]:
    return [c for c in REGISTRO.comandos if not c.fora_da_palette]
