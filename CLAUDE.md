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
| `vigia.py` | O tail **nunca** usa mmap (o arquivo cresce debaixo do mapeamento) e **sempre** um `IncrementalDecoder` (senão meio caractere multibyte vira U+FFFD permanente). |
| `grande/indice.py` | Fechar o mmap com o worker lendo dele estoura. `parar()` **adia** o fechamento em vez de bloquear a interface. |
| `arquivos.py` | `ReplaceFileW` via ctypes, e não `os.replace`: o segundo perde as ACEs explícitas e os fluxos alternativos do original. |
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
