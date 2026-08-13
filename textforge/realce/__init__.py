"""Motor de realce de sintaxe.

Nao existe um realcador por linguagem: existe UM motor, dirigido pelas regras que
cada `ProvedorDeLinguagem` declara. Acrescentar uma linguagem e' declarar dados,
nao escrever um QSyntaxHighlighter.

O motor tem tres pecas:

  `regras.py`          Regra, Contexto e RegrasDeRealce. Cada contexto compila UM
                       regex combinado, e uma passada de finditer por bloco --
                       nao N regex por bloco.
  `pilha.py`           Internador de pilha de contextos. O Qt guarda UM int por
                       bloco, e uma pilha (HTML -> script -> template -> ${}) nao
                       cabe num int.
  `pintor.py`          O QSyntaxHighlighter. Alem de pintar, grava DadosDoBloco --
                       nivel de dobra, tokens e pares -- que alimentam o folding,
                       o minimapa e o painel Estrutura sem nenhuma passagem extra
                       de parsing.
"""
