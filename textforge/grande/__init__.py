"""Modo de arquivo grande (requisito 15).

Somente leitura na v1, e a decisao e' deliberada: editar exigiria pilha de desfazer
virtualizada e reescrever 1 GB no disco a cada salvamento. O caso real de um arquivo
desse tamanho e' LER e PESQUISAR dentro de um log gigante, e isso funciona inteiro
aqui.

Dois modulos:

  `indice.py`   a indexacao esparsa numa thread, com progresso e cancelamento.
  `visor.py`    a view: um QAbstractScrollArea que pinta so' as linhas visiveis e
                nunca constroi um QTextDocument.

Os dois falam com a `FonteDeArquivo` de `textforge/fonte.py`, que e' quem tem o
mmap e o indice. Nenhum deles conhece o `Documento`.
"""
