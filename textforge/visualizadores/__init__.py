"""Visualizadores alternativos de um documento.

Cada um e' registrado numa `Aba` por nome (`aba.registrar_view("tabela", widget)`) e
a troca e' um `setCurrentIndex` na pilha -- e' o que preserva a pilha de desfazer do
documento quando o usuario alterna entre Texto e Tabela.
"""
