# Avisos de terceiros

O TextForge é distribuído sob a licença MIT (veja [LICENSE](LICENSE)). Este
arquivo registra as licenças dos componentes de terceiros que ele usa, e o
raciocínio por trás das escolhas.

## PySide6 (Qt for Python) — LGPLv3

O TextForge usa PySide6, distribuído sob LGPLv3. O TextForge **não modifica o
Qt** e o carrega como biblioteca dinâmica (`Qt6Core.dll`, `Qt6Gui.dll`,
`Qt6Widgets.dll`, `Qt6Network.dll`), entregues como arquivos separados no
pacote — o que atende à exigência da LGPL de permitir a substituição da
biblioteca.

Detalhes da licença do Qt: <https://doc.qt.io/qt-6/licensing.html>

## PyQt6 e QScintilla — deliberadamente NÃO usados

PyQt6 e QScintilla **não** são usados: são GPL da Riverbank, e a GPL tornaria
este projeto GPL também.
