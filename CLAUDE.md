# CLAUDE.md — convenções do TextForge

Instruções para quem for editar este projeto depois. Vale para pessoas e para
agentes. O que está aqui não é preferência de estilo: cada regra existe porque a
alternativa já produziu um defeito.

## As três regras que não se negociam

**1. Um arquivo aberto é DADO, nunca código.** Nada do que o usuário abre é
executado. `eval`, `exec`, `compile`, `os.system`, `subprocess(shell=True)`,
`pickle.load` e `yaml.load` sem `SafeLoader` estão proibidos no pacote inteiro.
`ast.parse` é permitido — analisa sem executar. `tests/teste_seguranca.py` **varre
o próprio fonte** procurando essas construções; ele vai falhar se alguém as
introduzir. "Executar o script aberto" está permanentemente fora de escopo.

**2. Nunca alterar conteúdo em silêncio.** Codificação, BOM, fim de linha (inclusive
os **mistos**, linha a linha), indentação, espaço no fim das linhas e a ausência de
quebra final são preservados ao salvar. Qualquer operação que perderia informação
**recusa e explica** — não faz um trabalho pela metade. `teste_documento.py` tem
round-trip byte a byte de 12 fixtures; ele é a rede que segura isso.

**3. Só a thread da interface toca `QTextDocument`, `QWidget` e
`QSyntaxHighlighter`.** Worker recebe dado imutável e devolve dado imutável por
sinal. Ver `tarefas.py`.

## Armadilhas específicas deste código

Cada uma já causou um defeito real. Estão anotadas também no ponto exato do código.

| Onde | O quê |
|---|---|
| `documento.py` | `toRawText()`, **nunca** `toPlainText()`. O segundo troca U+00A0 por espaço e U+2028/U+2029 por `\n` — corrupção silenciosa, e ainda desalinha os offsets de busca. |
| `realce/regras.py` | Nenhum quantificador aninhado (`(a+)+`). 5 MB numa linha de JS minificado congela a thread da UI. Há teste que varre os padrões. |
| `realce/regras.py` | Regra insensível a caixa usa flag com **escopo** — `(?i:...)` — e não `re.IGNORECASE`. As regras de um contexto entram todas no mesmo regex combinado. |
| `formatadores/de_xml.py` | **Nunca** `minidom.toprettyxml`. Ele insere texto em nós de texto existentes: `<nome>Ana</nome>` viraria `<nome>\n  Ana\n</nome>`, e o conteúdo **muda**. |
| `seguranca.py` | O offset do expat, com entrada `str`, vem em **caracteres** — não em bytes do UTF-8. Foi **medido** nesta máquina, e contradiz a receita comum. Converter introduziria o defeito que a conversão promete corrigir. |
| `codificacao.py` | UTF-16 sem BOM é testado **antes** do UTF-8 estrito: aqueles bytes *são* UTF-8 válido. E o charset-normalizer só é consultado com ≥16 bytes não-ASCII — abaixo disso ele devolve cp1250 para português. |
| `analisadores/de_csv.py` | Registro **não é** linha. Um campo entre aspas contém `\n`. Dividir por linha desloca a tabela inteira dali para frente. |
| `visualizadores/tabela_csv.py` | Linha não editada sai **verbatim**. Regenerar com `csv.writer` altera o arquivo mesmo sem edição (`"Ana"` vira `Ana`). |
| `planilha/gravador.py` | **Nunca** `openpyxl.save()` para gravar um `.xlsx`. Ele reconstrói o pacote a partir do que openpyxl entendeu e **descarta** gráficos, tabelas dinâmicas, slicers e comentários encadeados — o arquivo continua válido, só que sem eles. A gravação é patch nos bytes da aba editada; o resto do ZIP é copiado. openpyxl só **lê**. |
| `planilha/folha_xml.py` | O patch da aba é recorte de **bytes**, e não `ElementTree.tostring()`. O segundo reescreve o XML inteiro e emite `mc:Ignorable="x14ac xr xr2 xr3"` sem declarar os prefixos que nenhum elemento usou — o Excel recusa o arquivo. |
| `planilha/leitor.py` | `reset_dimensions()` antes de `iter_rows()` **não é opcional**. Em modo streaming o openpyxl acredita no `<dimension>` da aba, e ele mente com frequência: uma coluna inteira que existe no arquivo simplesmente não apareceria na grade. |
| `planilha/pasta.py` | Data digitada em célula que **não era** data vira texto. O que faz `45366` aparecer como `15/03/2024` é o formato numérico do estilo, e este editor não mexe em estilo — gravar o serial numa célula de formato Geral mostraria o número ao usuário. |
| `vigia.py` | O tail **nunca** usa mmap (o arquivo cresce debaixo do mapeamento) e **sempre** um `IncrementalDecoder` (senão meio caractere multibyte vira U+FFFD permanente). |
| `grande/indice.py` | Fechar o mmap com o worker lendo dele estoura. `parar()` **adia** o fechamento em vez de bloquear a interface. |
| `arquivos.py` | `ReplaceFileW` via ctypes, e não `os.replace`: o segundo perde as ACEs explícitas e os fluxos alternativos do original. |
| `interface/abas.py` | Todo `connect()` que o gerenciador cria para uma aba entra em `aba.conexoes` e é **desfeito** em `encerrar()`. O lambda captura a aba no `__defaults__` e a conexão vive num objeto que a aba possui: um ciclo que atravessa o C++, invisível para o coletor do Python. Medido: 20 abas de 1,1 MB faziam a memória subir **523 MB**; desconectando, 41 MB. |
| `interface/menus.py` | **Nunca** `QAction.menu()`. No PySide6 o QMenu devolvido tem o tempo de vida atrelado ao wrapper Python do QAction: quando ele é coletado, o shiboken **destrói o QMenu em C++** e a barra fica com ponteiro pendurado. Use `vinculos.menu(grupo)`. Há varredura estática em `teste_janela.py`. |
| `interface/janela.py` | Comando de menu **não** vai direto em `aba.editor`. O atalho do QAction é resolvido pelo `QShortcutMap` **antes** de o evento chegar ao widget em foco, então com a aba mostrando o visor, a tabela ou o log ao vivo, o comando ia para o editor **escondido**: `Ctrl+C` copiava nada e `Ctrl+D` marcava como modificado um arquivo somente-leitura. Ao criar uma view nova, ensine `_no_editor` a rotear para ela. |
| `editor/widget.py` | Tecla que é **só modificador** (Ctrl, Shift, Alt…) nunca conta como "ação" na seleção em bloco. Apertar Ctrl para depois apertar C gera um KeyPress do próprio Ctrl **antes** do C — e limpar ali fazia a seleção sumir no caminho, sem o `Ctrl+C` nunca ter bloco para copiar. |
| `editor/bloco.py` | As colunas do retângulo são **visuais**, não índices de caractere — senão o retângulo sai torto em arquivo com TAB, que é justamente onde a seleção por coluna serve. E editar percorre as linhas **de baixo para cima**: de cima para baixo, mudar o comprimento de uma linha desloca as posições já calculadas das de baixo. |
| `TextForge.spec` | `PySide6.QtNetwork` **não** entra nos excludes. Parece dispensável e é onde vivem `QLocalServer`/`QLocalSocket` — instância única e "Abrir com". |
| `TextForge.spec` | `uac_admin=False`. Elevado, o arrastar-e-soltar do Explorer **para de funcionar**. |
| `associar.ps1` | UTF-8 **com BOM**. O PowerShell 5.1 lê sem BOM como ANSI e destrói os acentos. |

## Como o código é organizado

**`fonte.py` é o seam central.** Existem dois mundos de dados — `QTextDocument` e
arquivo mapeado com índice esparso. Busca, CSV, diff e tail falam com
`FonteDeTexto` e não sabem qual está por baixo. Ao acrescentar um recurso que lê
conteúdo, fale com a `FonteDeTexto`; se você precisar de um `if` para o modo grande,
provavelmente o lugar certo é a interface, e não o núcleo.

**Comando se declara uma vez.** `interface/acoes.py` tem o registro; menu, toolbar,
menu de contexto, atalho e paleta são **gerados** dali. Nunca cadastre um comando em
dois lugares.

**Linguagem se acrescenta sem tocar no núcleo.** Crie o módulo em `linguagens/`
com um `PROVEDORES = (...)` no fim e cite-o em `linguagens/__init__.py`. O
`teste_empacotamento.py` falha se você esquecer o segundo passo. Um provedor cita
**papéis** do tema (`"palavra_chave"`), nunca cores literais.

**Numeração de linha é base ZERO** em todo o núcleo. A conversão para a numeração
de 1 que o usuário vê acontece **num lugar só**: `barra_de_status.py`.

**Português no código e na interface**, sem acento em identificador. Comentário
explica **por quê**, não o quê.

## Testes

Runner caseiro, sem pytest: `tests/rodar_todos.py`. Cada suíte é um processo
separado (um travamento de Qt não leva as outras) e o contrato de saída é exato —
`checa()` imprime `"  OK   "` ou `"  FALHA"`, e o runner conta.

```bat
.venv\Scripts\python.exe tests\rodar_todos.py       :: tudo
.venv\Scripts\python.exe tests\teste_csv.py         :: uma suíte
```

Teto de **180 s por suíte**, de propósito: é o que faz um `QMessageBox` modal
esquecido aparecer em segundos em vez de pendurar a rodada. Suíte que precisa de
mais tempo entra em `LIMITE_PROPRIO_S` — não suba o teto geral.

**Ao mexer na interface, cuidado com modal.** Um `dialogos.avisar` num caminho que
o teste percorre trava a suíte para sempre em modo offscreen. Separe "montar" de
"exibir", como em `GerenciadorAbas.construir_menu_da_aba`.

**Um teste vale pelo que ele garante, não por passar.** Se um teste passa por sorte
de temporização, ele é pior que nenhum — foi o que aconteceu com o `pausar()` do
tail, que a suíte aprovou e a fumaça com um processo real reprovou. Prefira afirmar
a propriedade (nada se perde, nada se repete) a afirmar um instante.

**Nunca escreva `checa(X or True, ...)`.** A auditoria de 15/08/2026 achou cinco
delas, e duas escondiam defeito real: o `QTextDocument` que não era liberado ao
fechar a aba, e o comentário do prólogo que o formatador de XML apagava. Se uma
verificação não passa, ou o código está errado ou a afirmação está errada — enfraquecer
a condição não é a terceira opção. Um `checa(True, "X não estourou")` depois de uma
operação é legítimo; uma condição tautológica com rótulo que promete outra coisa não é.

**Cuidado com o que mede nada:** três armadilhas já apareceram aqui —
`isVisible()` é sempre False numa janela nunca exibida; `processEvents()` **não**
entrega `DeferredDelete` (use `ajudantes.drenar_eventos`); e uma função de medição
que devolve `0.0` no `except` transforma qualquer teto em tautologia (use
`ajudantes.memoria_privada_mb`, que levanta em vez de mentir).

## Ao acrescentar um recurso

1. Ele cabe num `registrar_*` existente? Explorer, minimapa, folding, diff e hex já
   têm o encaixe pronto e **não** precisam tocar em `documento.py`, `fonte.py`,
   `realce/`, `linguagens/base.py` nem `interface/janela.py`.
2. Declare o comando em `acoes.py` e ligue em `janela._ligar_comandos`.
3. Comando não implementado aparece **desabilitado**, e não escondido: o usuário vê
   o que o programa vai ter, e nada clicável finge funcionar.
4. Escreva o teste do caso difícil, e não do caminho feliz. Os cinco que sustentam
   este projeto estão listados em `tests/README.md`.

## Verificação manual que os testes não cobrem

- Abrir um CSV com `;` e acentos, alternar Texto ↔ Tabela **sem editar**, salvar e
  conferir com `fc /b` que o arquivo ficou idêntico.
- Gerar um `.log` de ~500 MB, abrir (deve ser instantâneo), `Ctrl+G` para a última
  linha, pesquisar um termo que só existe no fim.
- Outro terminal gravando no log; ligar **Acompanhar alterações**, pausar, retomar.
- `build.bat`, rodar o `.exe`, `associar.ps1 .log`, duplo-clique num `.log`,
  selecionar 5 arquivos e abrir (deve haver **um** processo), arrastar do Explorer
  para a janela, `associar.ps1 -Remover`.
