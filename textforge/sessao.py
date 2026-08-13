"""Sessao (requisito 17) e recuperacao apos encerramento inesperado (16).

Duas coisas diferentes, guardadas em lugares diferentes:

  SESSAO       quais arquivos estavam abertos, o cursor, a rolagem e a aba ativa.
               Fica em %APPDATA%\\TextForge\\sessao.json. So' referencia caminhos;
               nao guarda conteudo.

  RECUPERACAO  uma copia do conteudo dos documentos MODIFICADOS, para o caso de o
               programa ser encerrado sem salvar. Fica em
               %APPDATA%\\TextForge\\recuperacao\\.

Duas decisoes de projeto que valem explicacao:

1. A recuperacao grava BYTES JA CODIFICADOS mais um manifesto com codec, BOM e fim
   de linha -- e nao o `str`. Recuperar um arquivo cp1252 e grava-lo em UTF-8
   porque "texto e' texto" e' justamente a corrupcao que o requisito 38 proibe, e
   seria uma corrupcao introduzida pelo mecanismo de seguranca.

2. Sessao morta e' detectada pelo TESTE DE RENAME da trava, e nao por PID. Um PID
   pode ter sido reciclado por outro processo qualquer, e "o PID 4312 existe" nao
   quer dizer "o TextForge esta' rodando". Se conseguimos renomear o arquivo de
   trava, ninguem o tem aberto -- e no Windows isso e' conclusivo, porque um
   arquivo aberto sem compartilhamento nao pode ser renomeado.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from textforge import VERSAO, configuracao, log_interno

log = log_interno.obter(__name__)

NOME_DA_TRAVA = "sessao.lock"
SUFIXO_DE_CONTEUDO = ".conteudo"
SUFIXO_DE_MANIFESTO = ".json"


# ---------------------------------------------------------------------------
# Sessao
# ---------------------------------------------------------------------------


@dataclass
class EstadoDeAba:
    caminho: str = ""
    cursor: int = 0                # posicao em caracteres
    rolagem: int = 0               # primeiro bloco visivel
    codec: str = ""                # se o usuario trocou na mao
    fim_de_linha: str = ""
    view: str = "texto"            # "texto" | "tabela" | "hex"


@dataclass
class Sessao:
    versao: str = VERSAO
    abas: list[EstadoDeAba] = field(default_factory=list)
    ativa: int = 0

    def para_json(self) -> dict[str, Any]:
        return {"versao": self.versao, "ativa": self.ativa,
                "abas": [asdict(a) for a in self.abas]}

    @classmethod
    def de_json(cls, dados: dict[str, Any]) -> "Sessao":
        abas: list[EstadoDeAba] = []
        for bruto in dados.get("abas", []):
            if not isinstance(bruto, dict) or not bruto.get("caminho"):
                continue
            # Filtra chaves desconhecidas: um sessao.json de versao futura nao
            # pode impedir esta versao de abrir.
            conhecidas = {c: bruto[c] for c in EstadoDeAba.__dataclass_fields__
                          if c in bruto}
            abas.append(EstadoDeAba(**conhecidas))
        return cls(versao=str(dados.get("versao", "")), abas=abas,
                   ativa=max(0, int(dados.get("ativa", 0) or 0)))


def salvar_sessao(sessao: Sessao,
                  caminho: pathlib.Path | None = None) -> pathlib.Path:
    alvo = caminho or configuracao.caminho_sessao()
    alvo.parent.mkdir(parents=True, exist_ok=True)
    temporario = alvo.with_name(alvo.name + ".novo")
    temporario.write_text(
        json.dumps(sessao.para_json(), indent=2, ensure_ascii=False),
        encoding="utf-8")
    os.replace(temporario, alvo)
    return alvo


def carregar_sessao(caminho: pathlib.Path | None = None) -> Sessao:
    """Le' a sessao. Sessao ilegivel devolve uma sessao vazia, sem estourar."""
    alvo = caminho or configuracao.caminho_sessao()
    if not alvo.is_file():
        return Sessao(abas=[])
    try:
        dados = json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("sessao ilegivel em %s (%s); ignorando", alvo, exc)
        return Sessao(abas=[])
    if not isinstance(dados, dict):
        return Sessao(abas=[])
    return Sessao.de_json(dados)


def abas_existentes(sessao: Sessao) -> list[EstadoDeAba]:
    """Descarta as abas cujo arquivo nao esta' mais no disco.

    Silenciosamente: o usuario apagou ou moveu o arquivo desde a ultima sessao, e
    abrir um dialogo de erro por arquivo ao iniciar o programa seria pior do que
    simplesmente nao restaurar a aba.
    """
    vivas = []
    for aba in sessao.abas:
        if pathlib.Path(aba.caminho).is_file():
            vivas.append(aba)
        else:
            log.info("aba da sessao ignorada, arquivo ausente: %s", aba.caminho)
    return vivas


# ---------------------------------------------------------------------------
# Trava: a sessao anterior morreu?
# ---------------------------------------------------------------------------


class Trava:
    """Marca que ha' um TextForge rodando, e detecta encerramento inesperado.

    A deteccao e' pelo TESTE DE RENAME, nao por PID: um PID pode ter sido
    reciclado, e "o PID existe" nao significa "o TextForge esta' rodando". Se o
    arquivo de trava pode ser renomeado, ninguem o mantem aberto.
    """

    def __init__(self, caminho: pathlib.Path | None = None) -> None:
        self.caminho = caminho or (configuracao.pasta_de_dados() / NOME_DA_TRAVA)
        self._arquivo = None

    def sessao_anterior_morreu(self) -> bool:
        """True se existe trava de uma sessao que nao foi encerrada direito."""
        if not self.caminho.exists():
            return False
        sonda = self.caminho.with_name(self.caminho.name + ".sonda")
        try:
            os.replace(self.caminho, sonda)
        except OSError:
            # Nao conseguiu renomear: outra instancia esta' com o arquivo aberto.
            return False
        try:
            os.replace(sonda, self.caminho)
        except OSError:
            pass
        return True

    def adquirir(self) -> bool:
        """Cria a trava e a mantem aberta enquanto o programa roda."""
        try:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            # Manter o handle ABERTO e' o que faz o teste de rename funcionar do
            # outro lado. Fechar depois de escrever tornaria a trava inutil.
            self._arquivo = open(self.caminho, "w", encoding="utf-8")
            self._arquivo.write(json.dumps({
                "pid": os.getpid(), "versao": VERSAO, "desde": time.time()}))
            self._arquivo.flush()
            return True
        except OSError as exc:
            log.warning("nao foi possivel criar a trava de sessao: %s", exc)
            self._arquivo = None
            return False

    def liberar(self) -> None:
        if self._arquivo is not None:
            try:
                self._arquivo.close()
            except OSError:
                pass
            self._arquivo = None
        try:
            self.caminho.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Recuperacao
# ---------------------------------------------------------------------------


@dataclass
class Recuperavel:
    identificador: str
    caminho_original: str          # "" quando era um documento sem titulo
    nome: str
    codec: str
    bom_hex: str
    fim_de_linha: str
    quando: float
    bytes_do_conteudo: bytes = b""

    @property
    def bom(self) -> bytes:
        return bytes.fromhex(self.bom_hex) if self.bom_hex else b""

    @property
    def quando_texto(self) -> str:
        return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(self.quando))


def _pasta() -> pathlib.Path:
    return configuracao.pasta_de_recuperacao()


def _identificador(documento) -> str:
    """Identificador estavel por documento, para nao acumular copias.

    Derivado do caminho quando existe; um uuid quando o documento nao tem
    arquivo. Sem isso, cada intervalo de autosave criaria um arquivo novo e a
    pasta de recuperacao cresceria sem fim.
    """
    if documento.caminho is not None:
        import hashlib
        return hashlib.sha256(
            str(documento.caminho).lower().encode("utf-8")).hexdigest()[:16]
    if not getattr(documento, "_id_recuperacao", ""):
        documento._id_recuperacao = uuid.uuid4().hex[:16]
    return documento._id_recuperacao


def gravar_copia(documento) -> pathlib.Path | None:
    """Grava a copia de recuperacao de UM documento modificado.

    Grava os BYTES que iriam para o arquivo (codificados com o codec e o fim de
    linha do documento) mais um manifesto. Guardar o `str` faria a recuperacao
    devolver o arquivo em UTF-8 mesmo que ele fosse cp1252 -- corrupcao
    introduzida pelo proprio mecanismo de seguranca.
    """
    if not documento.modificado or documento.binario:
        return None
    ident = _identificador(documento)
    pasta = _pasta()
    try:
        conteudo = documento.bytes_para_salvar(substituir=True)
    except (UnicodeEncodeError, LookupError) as exc:
        log.warning("nao foi possivel preparar a copia de recuperacao de %s: %s",
                    documento.nome, exc)
        return None

    manifesto = {
        "identificador": ident,
        "caminho_original": str(documento.caminho or ""),
        "nome": documento.nome,
        "codec": documento.codec,
        "bom_hex": documento.bom.hex(),
        "fim_de_linha": documento.fim_de_linha,
        "quando": time.time(),
        "versao": VERSAO,
    }
    try:
        (pasta / (ident + SUFIXO_DE_CONTEUDO)).write_bytes(conteudo)
        (pasta / (ident + SUFIXO_DE_MANIFESTO)).write_text(
            json.dumps(manifesto, indent=2, ensure_ascii=False),
            encoding="utf-8")
    except OSError as exc:
        log.warning("falha ao gravar copia de recuperacao de %s: %s",
                    documento.nome, exc)
        return None
    return pasta / (ident + SUFIXO_DE_CONTEUDO)


def esquecer_copia(documento) -> None:
    """Apaga a copia de recuperacao -- chamado depois de salvar de verdade."""
    ident = _identificador(documento)
    pasta = _pasta()
    for sufixo in (SUFIXO_DE_CONTEUDO, SUFIXO_DE_MANIFESTO):
        try:
            (pasta / (ident + sufixo)).unlink(missing_ok=True)
        except OSError:
            pass


def listar_recuperaveis() -> list[Recuperavel]:
    """O que sobrou de uma sessao que nao foi encerrada direito."""
    achados: list[Recuperavel] = []
    pasta = _pasta()
    for manifesto in sorted(pasta.glob("*" + SUFIXO_DE_MANIFESTO)):
        try:
            dados = json.loads(manifesto.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("manifesto de recuperacao ilegivel: %s", manifesto)
            continue
        conteudo = manifesto.with_suffix("").with_name(
            manifesto.stem + SUFIXO_DE_CONTEUDO)
        if not conteudo.is_file():
            continue
        try:
            bytes_do_conteudo = conteudo.read_bytes()
        except OSError:
            continue
        achados.append(Recuperavel(
            identificador=str(dados.get("identificador", manifesto.stem)),
            caminho_original=str(dados.get("caminho_original", "")),
            nome=str(dados.get("nome", "?")),
            codec=str(dados.get("codec", "utf-8")),
            bom_hex=str(dados.get("bom_hex", "")),
            fim_de_linha=str(dados.get("fim_de_linha", "\r\n")),
            quando=float(dados.get("quando", 0.0) or 0.0),
            bytes_do_conteudo=bytes_do_conteudo))
    return achados


def limpar_recuperacao() -> int:
    """Apaga tudo. Devolve quantos arquivos foram removidos.

    E' o botao "limpar recuperacao agora" das configuracoes: a pasta guarda
    copias em TEXTO CLARO de arquivos possivelmente sensiveis, e o usuario tem de
    poder apaga-las sem procurar a pasta no Explorer.
    """
    removidos = 0
    for arquivo in _pasta().glob("*"):
        try:
            arquivo.unlink()
            removidos += 1
        except OSError:
            pass
    return removidos


def pasta_permitida(caminho: pathlib.Path | None, cfg: dict) -> bool:
    """A copia de recuperacao pode ser gravada para este arquivo?

    Atende a' lista de pastas excluidas das configuracoes: um arquivo com dado
    sensivel nao deve ganhar uma copia em texto claro em %APPDATA%.
    """
    if caminho is None:
        return True
    excluidas = cfg.get("recuperacao_pastas_excluidas") or []
    if not excluidas:
        return True
    try:
        alvo = str(caminho.resolve()).lower()
    except OSError:
        alvo = str(caminho).lower()
    for pasta in excluidas:
        if pasta and alvo.startswith(str(pasta).lower().rstrip("\\/")):
            return False
    return True
