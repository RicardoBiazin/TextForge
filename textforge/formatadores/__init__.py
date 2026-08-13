"""Formatadores por linguagem (requisito 6).

Cada `ProvedorDeLinguagem` devolve o seu em `formatador()`. Nenhum formatador roda
sozinho: "Formatar documento" e "Validar" sao SEMPRE comandos explicitos do usuario
(requisito 38 -- nao formatar automaticamente um arquivo inteiro sem acao dele).

Regra que atravessa todos: quando a formatacao PERDERIA informacao, ela e' recusada
com aviso, em vez de silenciosamente entregar um arquivo diferente do original.
"""
