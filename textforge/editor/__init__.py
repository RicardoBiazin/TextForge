"""O widget de edicao e suas partes.

`EditorDeTexto` e' um `QPlainTextEdit` subclassado. A escolha nao e' por
comodidade: o `QPlainTextEdit` usa `QPlainTextDocumentLayout`, que faz layout
preguicoso por bloco, enquanto o `QTextEdit` faz o layout do documento inteiro e
engasga em arquivos grandes. E' a mesma base do exemplo oficial "Code Editor" do
Qt, do Spyder e do pyqode.

QScintilla, que resolveria muita coisa de graca, esta' fora: so' existe binding
para PyQt5/PyQt6, que sao GPL da Riverbank, e isso tornaria o projeto GPL.
"""
