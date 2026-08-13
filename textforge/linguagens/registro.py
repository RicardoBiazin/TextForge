"""Registro de provedores de linguagem.

O nucleo pergunta aqui; nunca importa um provedor concreto. E' o que permite um
plugin acrescentar uma linguagem sem tocar em nenhum arquivo do nucleo.

ORDEM DE RESOLUCAO em `por_caminho`, parando no primeiro que decide:

  1. nome de arquivo INTEIRO      Makefile, Dockerfile, .gitignore, web.config
  2. extensao, a MAIS LONGA       ".d.ts" antes de ".ts"
  3. shebang da primeira linha    #!/usr/bin/env python3
  4. assinatura do inicio         "<?php", "<?xml", "{" ou "[" de JSON
  5. detectar_por_conteudo()      maior pontuacao entre todos os provedores
  6. texto puro

Empates sao resolvidos por `prioridade` (plugin > embutido).

`por_caminho` recebe a amostra JA DECODIFICADA -- quem chama e' o `Documento`, que
ja' leu o arquivo e detectou a codificacao. Nenhum provedor toca em disco.
"""

from __future__ import annotations

import os
import pathlib

from textforge import log_interno
from textforge.linguagens.base import ProvedorDeLinguagem

log = log_interno.obter(__name__)

# Assinaturas de inicio de arquivo, na ordem de teste. O nome e' o do provedor.
ASSINATURAS: tuple[tuple[str, str], ...] = (
    ("<?php", "PHP"),
    ("<?xml", "XML"),
    ("<!DOCTYPE html", "HTML"),
    ("<!doctype html", "HTML"),
    ("<html", "HTML"),
)


class Registro:
    def __init__(self) -> None:
        self._todos: list[ProvedorDeLinguagem] = []
        self._por_extensao: dict[str, list[ProvedorDeLinguagem]] = {}
        self._por_nome_de_arquivo: dict[str, list[ProvedorDeLinguagem]] = {}
        self._por_nome: dict[str, ProvedorDeLinguagem] = {}

    # ==================================================================
    # Registro
    # ==================================================================

    def registrar(self, provedor: ProvedorDeLinguagem) -> None:
        """Acrescenta um provedor. Substitui o de mesmo nome e menor prioridade."""
        if not provedor.nome:
            raise ValueError("provedor sem nome")
        existente = self._por_nome.get(provedor.nome)
        if existente is not None:
            if existente.prioridade > provedor.prioridade:
                log.info("provedor %r ignorado: ja' existe um de prioridade "
                         "maior", provedor.nome)
                return
            self._remover(existente)

        self._todos.append(provedor)
        self._por_nome[provedor.nome] = provedor
        for ext in provedor.extensoes:
            self._por_extensao.setdefault(ext.lower(), []).append(provedor)
        for nome in provedor.nomes_de_arquivo:
            self._por_nome_de_arquivo.setdefault(nome.lower(), []).append(provedor)

    def _remover(self, provedor: ProvedorDeLinguagem) -> None:
        if provedor in self._todos:
            self._todos.remove(provedor)
        self._por_nome.pop(provedor.nome, None)
        for lista in list(self._por_extensao.values()):
            if provedor in lista:
                lista.remove(provedor)
        for lista in list(self._por_nome_de_arquivo.values()):
            if provedor in lista:
                lista.remove(provedor)

    def limpar(self) -> None:
        """So' para teste: devolve o registro ao estado vazio."""
        self.__init__()

    # ==================================================================
    # Consulta
    # ==================================================================

    def todos(self) -> list[ProvedorDeLinguagem]:
        return list(self._todos)

    def nomes(self) -> list[str]:
        return sorted(self._por_nome)

    def por_nome(self, nome: str) -> ProvedorDeLinguagem | None:
        return self._por_nome.get(nome)

    def de_texto(self) -> ProvedorDeLinguagem | None:
        """O provedor de texto puro, usado como fallback."""
        return self._por_nome.get("Texto")

    def extensoes_conhecidas(self) -> list[str]:
        return sorted(self._por_extensao)

    @staticmethod
    def _melhor(candidatos: list[ProvedorDeLinguagem]
                ) -> ProvedorDeLinguagem | None:
        if not candidatos:
            return None
        return max(candidatos, key=lambda p: p.prioridade)

    def por_extensao(self, nome_do_arquivo: str) -> ProvedorDeLinguagem | None:
        """Resolve pela extensao, tentando a MAIS LONGA primeiro.

        ".d.ts" antes de ".ts", ".tar.gz" antes de ".gz". Sem isso, um provedor de
        TypeScript de declaracao nunca seria alcancado.
        """
        nome = nome_do_arquivo.lower()
        partes = nome.split(".")
        # Da mais longa para a mais curta: para "a.d.ts" tenta ".d.ts" e ".ts".
        for corte in range(1, len(partes)):
            candidata = "." + ".".join(partes[corte:])
            melhor = self._melhor(self._por_extensao.get(candidata, []))
            if melhor is not None:
                return melhor
        return None

    def por_shebang(self, primeira_linha: str) -> ProvedorDeLinguagem | None:
        if not primeira_linha.startswith("#!"):
            return None
        linha = primeira_linha.lower()
        for provedor in sorted(self._todos, key=lambda p: -p.prioridade):
            for padrao in provedor.padroes_de_shebang:
                if padrao.lower() in linha:
                    return provedor
        return None

    def por_assinatura(self, amostra: str) -> ProvedorDeLinguagem | None:
        inicio = amostra.lstrip()[:200]
        for marca, nome in ASSINATURAS:
            if inicio.startswith(marca):
                provedor = self._por_nome.get(nome)
                if provedor is not None:
                    return provedor
        return None

    def por_conteudo(self, amostra: str) -> ProvedorDeLinguagem | None:
        """O provedor mais confiante. None se ninguem passar de 50."""
        melhor: ProvedorDeLinguagem | None = None
        melhor_nota = 0
        for provedor in self._todos:
            try:
                nota = int(provedor.detectar_por_conteudo(amostra))
            except Exception as exc:      # noqa: BLE001 - provedor de plugin
                log.warning("detectar_por_conteudo de %r falhou: %s",
                            provedor.nome, exc)
                continue
            # Desempate por prioridade, para um plugin poder ganhar de um embutido
            # com a mesma confianca.
            if nota > melhor_nota or (nota == melhor_nota and melhor is not None
                                     and provedor.prioridade > melhor.prioridade
                                     and nota > 0):
                melhor, melhor_nota = provedor, nota
        return melhor if melhor_nota > 50 else None

    def por_caminho(self, caminho: str | os.PathLike[str] | None,
                    amostra: str = "") -> ProvedorDeLinguagem | None:
        """A resolucao completa. Ver a ordem no docstring do modulo."""
        if caminho is not None:
            nome_do_arquivo = pathlib.Path(caminho).name
            exato = self._melhor(
                self._por_nome_de_arquivo.get(nome_do_arquivo.lower(), []))
            if exato is not None:
                return exato
            por_ext = self.por_extensao(nome_do_arquivo)
            if por_ext is not None:
                return por_ext

        if amostra:
            primeira = amostra.split("\n", 1)[0]
            por_sb = self.por_shebang(primeira)
            if por_sb is not None:
                return por_sb
            por_ass = self.por_assinatura(amostra)
            if por_ass is not None:
                return por_ass
            por_cont = self.por_conteudo(amostra)
            if por_cont is not None:
                return por_cont

        return self.de_texto()

    # ==================================================================
    # Diagnostico (usado pelos testes)
    # ==================================================================

    def extensoes_em_conflito(self) -> dict[str, list[str]]:
        """Extensoes reivindicadas por mais de um provedor de MESMA prioridade.

        Nao e' erro em si -- um plugin sobrepondo um embutido e' o caso de uso --,
        mas dois EMBUTIDOS disputando ".ts" na mesma prioridade significa que a
        escolha fica ao acaso da ordem de registro.
        """
        conflitos: dict[str, list[str]] = {}
        for ext, provedores in self._por_extensao.items():
            if len(provedores) < 2:
                continue
            maior = max(p.prioridade for p in provedores)
            empatados = [p.nome for p in provedores if p.prioridade == maior]
            if len(empatados) > 1:
                conflitos[ext] = sorted(empatados)
        return conflitos


REGISTRO = Registro()


def registrar(provedor: ProvedorDeLinguagem) -> None:
    """Ponto de entrada dos plugins: `api.registrar_linguagem(...)`."""
    REGISTRO.registrar(provedor)


def por_caminho(caminho=None, amostra: str = "") -> ProvedorDeLinguagem | None:
    return REGISTRO.por_caminho(caminho, amostra)
