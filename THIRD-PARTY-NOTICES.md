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

## openpyxl — MIT

Usado para **ler** os valores de planilhas `.xlsx` e `.xlsm`. Licença MIT, a
mesma deste projeto; puro Python, sem extensão nativa. Traz uma dependência
própria, `et_xmlfile`, também MIT.

Ele **não** participa da gravação. O TextForge grava aplicando um patch nos
bytes do pacote original (`textforge/planilha/gravador.py`), porque
`openpyxl.save()` reconstrói o arquivo a partir do que openpyxl entendeu e
descarta gráficos, tabelas dinâmicas e macros. A escolha está explicada em
`textforge/planilha/__init__.py`.

Licença: <https://foss.heptapod.net/openpyxl/openpyxl/-/blob/branch/3.1/LICENCE.rst>

## pandas e numpy — deliberadamente NÃO usados

A tentação num recurso de planilha é trazer pandas. Ele está na lista de
`excludes` do `TextForge.spec`, e há teste (`teste_empacotamento.py`) que falha
se entrar: pandas e numpy somam dezenas de MB ao executável para fazer o que a
grade já faz sem eles. openpyxl não depende de nenhum dos dois.

## PyQt6 e QScintilla — deliberadamente NÃO usados

PyQt6 e QScintilla **não** são usados: são GPL da Riverbank, e a GPL tornaria
este projeto GPL também.
