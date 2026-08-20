# Testes do TextForge

```
.venv\Scripts\python.exe tests\rodar_todos.py
```

Sem pytest, de propósito — é o padrão dos outros projetos desta máquina. O
`rodar_todos.py` roda cada suíte **num processo separado** e conta as ocorrências
de `"  OK   "` e `"  FALHA"` na saída. Vantagem prática: um travamento de Qt numa
suíte não leva as outras.

Para rodar uma suíte isolada:

```
.venv\Scripts\python.exe tests\teste_configuracao.py
```

## Convenções

| Item | Regra |
|---|---|
| Nome do arquivo | `teste_*.py` (não `test_*.py`) |
| Verificação | `checa(cond, "descrição")` — os espaços em `"  OK   "` importam, o runner conta por eles |
| Comparação | `checa_igual(obtido, esperado, "descrição")` — imprime os dois valores quando falha |
| Exceção esperada | `checa_levanta(TipoDoErro, funcao, "descrição", args...)` |
| Fim da suíte | `sys.exit(resumir())` |
| Interface | `preparar_qt()` na primeira linha executável; se devolver `False`, `sys.exit(pular("..."))` |
| `%APPDATA%` | sempre via `appdata_temporario()` — nunca escrever no `%APPDATA%\TextForge` de verdade |

## Suítes

Na ordem em que `rodar_todos.py` as executa. "Precisa de" diz o que a suíte exige
para rodar; sem PySide6 ela imprime **PULADO** em vez de falhar.

| Arquivo | O que cobre | Precisa de |
|---|---|---|
| `teste_configuracao.py` | `padrao()` cobre o requisito 30, round-trip, config corrompido, merge de chave nova, pastas de `%APPDATA%`, modo portátil, `sys._MEIPASS`, lista de recentes | nada |
| `teste_cli.py` | `--line`, `--col`, vários arquivos, caminho relativo, e a **recusa** de dispositivos do Windows (`CON`, `NUL`, `COM1`, `LPT1`, `PRN`, `AUX`) | nada |
| `teste_tarefas.py` | progresso limitado a 10 Hz, cancelamento cooperativo, exceção no worker virando sinal, pools separados | PySide6 |
| `teste_instancia_unica.py` | canal por usuário, entrega **entre processos**, 5 processos simultâneos, lixo no canal, pipe órfão | PySide6 |
| `teste_fonte.py` | a **mesma bateria** nas 3 implementações de `FonteDeTexto`, sobre o mesmo conteúdo | PySide6 |
| `teste_acoes.py` | nenhum atalho duplicado, nenhum `Ctrl+Alt+letra` (é AltGr no ABNT2), todo comando com rótulo, geração de menu e palette | PySide6 |
| `teste_tema.py` | todo papel citado por qualquer provedor existe nos dois temas, merge de tema parcial, contraste | PySide6 |
| `teste_indentacao.py` | detecção **por arquivo** (tab, 2, 4, 8 e misto), largura visual, conversões | nada |
| `teste_operacoes_linha.py` | ordenar, inverter, duplicar, remover duplicadas, aparar, e as conversões de caixa | nada |
| `teste_editor.py` | margem crescendo de 99 para 100 linhas, `paintEvent` com documento vazio, Tab em bloco num só undo, camadas de seleção, marcadores | PySide6 |
| `teste_janela.py` | janela, menus gerados, comandos ligados, e a checagem de que o não implementado aparece **desabilitado** | PySide6 |
| `teste_codificacao.py` | cada BOM, UTF-32 x UTF-16, UTF-16 sem BOM, cp1252, `.dat` binário x largura fixa, assinaturas, perdas na conversão | nada |
| `teste_documento.py` | **round-trip byte a byte de 12 fixtures**, salvar atômico, `.tfnew` nunca sobrando, `AlteradoNoDisco` | PySide6 |
| `teste_vigia.py` | alteração externa por watcher **e** por consulta periódica | PySide6 |
| `teste_abas.py` | identidade por arquivo (`resolve()` + caixa), asterisco de modificado, menu de contexto, documento liberado ao fechar | PySide6 |
| `teste_sessao.py` | round-trip da sessão, **trava detectada por rename** (não por PID), recuperação guardando o codec | PySide6 |
| `teste_realce.py` | regras combinadas num regex, pilha internada, contexto multi-linha, regra que casa vazio, quantificador aninhado | PySide6 |
| `teste_linguagens.py` | resolução por nome/extensão/shebang/conteúdo, prioridade de plugin, e **cada provedor** validado (papéis, regex, dobra) | PySide6 |
| `teste_realce_embutido.py` | PHP em HTML, JS/CSS em tag, heredoc `<<<SQL`, pilha de profundidade 4, pareamento | PySide6 |
| `teste_painel_estrutura.py` | árvore por `ast`, fallback regex em arquivo com erro de sintaxe, filtro, navegação | PySide6 |
| `teste_busca.py` | critério, **offsets de `re.finditer` casando com `QTextCursor`**, substituir 500 num só undo, regex que casa vazio | PySide6 |
| `teste_busca_em_arquivos.py` | varredura, filtros, junction auto-referente sem laço, cancelamento | PySide6 |
| `teste_seguranca.py` | XXE, billion laughs, **varredura estática do próprio fonte**, prova de efeito colateral | nada |
| `teste_formatadores.py` | fidelidade de XML/JSON/SQL/CSS/HTML/Python, idempotência, recusas, coluna do expat | PySide6 |
| `teste_csv.py` | dialeto, registro multi-linha, **`para_texto()` sem edição idêntico**, parse lazy | PySide6 |
| `teste_indice_grande.py` | índice esparso em 20 pontos, **padrão na fronteira de bloco**, teto de RAM, visor, cancelamento | PySide6, ~200 MB em `%TEMP%` |
| `teste_tail.py` | leitura incremental, **multibyte cortado**, linha parcial, truncamento, rotação, pausar/retomar | PySide6 |
| `teste_xlsx.py` | **patch sem perder gráfico/macro**, tipos de célula, `<dimension>` mentiroso, fórmula compartilhada, recusas | openpyxl; a parte de `Documento` pede PySide6 |
| `teste_conversoes.py` | Base64/URL/HTML/JSON, tolerâncias do Base64, e o peso da **codificação** | nada |
| `teste_hash.py` | digests contra **valores publicados**, leitura em blocos, texto x arquivo | nada |
| `teste_paleta.py` | busca por **subsequência**, abertura rápida com teto, comentar/descomentar | PySide6 |
| `teste_empacotamento.py` | `.spec`, `versao.txt`, manifesto, `associar.ps1` com BOM, imports proibidos — tudo **estático** | nada |

`ajudante_enviar.py` não é uma suíte — é o processo auxiliar que o
`teste_instancia_unica.py` dispara.

**Ao acrescentar uma suíte:** entre nesta tabela e em `SUITES` do `rodar_todos.py`.
Se ela demorar mais que 180 s, use `LIMITE_PROPRIO_S` — não suba o teto geral, que é
o que faz um diálogo modal esquecido aparecer em segundos.

## Regressões que estas suítes guardam

São os casos em que o código *parecia* certo e não estava. Se um destes testes
quebrar, leia o comentário no código antes de "consertar" o teste.

- **`teste_csv.py`, "para_texto() sem edição devolve a entrada IDÊNTICA".** É o
  teste central da etapa 9. Regenerar o CSV com `csv.writer` altera o arquivo
  **mesmo sem nenhuma edição**: o `QUOTE_MINIMAL` transforma `"Ana"` em `Ana`, o
  espaço depois do delimitador some e um número citado deixa de ser citado. Num
  arquivo de integração isso é destruição silenciosa e torna qualquer `fc /b`
  inútil. Se este teste quebrar, o `ModeloCsv` voltou a reconstruir linhas que
  ninguém editou — o `registros_crus`/`sujas` existe exatamente para impedir isso.
- **`teste_abas.py`, "o QTextDocument da aba fechada é LIBERADO".** Esta verificação
  já existiu como `checa(referencia() is None or True, ...)` — sempre verdadeira — e
  escondeu um vazamento real por várias etapas. As lambdas de
  `GerenciadorAbas.adicionar` capturam a aba no `__defaults__`, e a conexão vive num
  objeto que a própria aba possui: um ciclo através do C++ que o coletor do Python
  não enxerga. **Medido: 20 abas de um arquivo de 1,1 MB faziam a memória privada
  subir 523 MB.** Se este teste quebrar, alguém acrescentou um `connect()` em
  `adicionar` sem pôr em `aba.conexoes`.
- **`teste_seguranca.py`, "FORMATAR preserva o comentário do prólogo".** Também
  nasceu como `checa(tem_comentario or True, ...)`, e escondia o formatador de XML
  **apagando** um comentário que vem antes do elemento raiz — alteração silenciosa de
  conteúdo, que o requisito 38 proíbe. O prólogo é reemitido do texto original,
  porque ele não cabe na árvore (um comentário antes da raiz não é filho de ninguém).
- **`teste_empacotamento.py`, "PySide6.QtNetwork NÃO está nos excludes".** É onde
  vivem `QLocalServer`/`QLocalSocket` — instância única e "Abrir com". Excluí-lo
  parece razoável ("não usamos rede") e mata os dois **só no `.exe`**. O teste lê a
  lista pela **árvore** (`ast`), e não por busca de texto: o próprio `.spec` explica
  em comentário por que QtNetwork não pode sair, e uma busca textual acusaria esse
  comentário como se fosse a exclusão.
- **`teste_empacotamento.py`, "todo módulo de linguagem está no `__init__`".** Criar
  `lua.py` e esquecer de registrar produz "o realce não funciona nesse arquivo" na
  máquina do usuário, e nada aqui. Um módulo conta como linguagem quando define
  `PROVEDORES` — critério derivado do código, não uma lista de exceções à mão.
- **`teste_conversoes.py` e `teste_hash.py`, "a codificação importa".** `"ação"` em
  cp1252 e em UTF-8 são bytes diferentes, logo Base64 diferente e hash diferente. Um
  editor que assumisse UTF-8 sempre geraria um Base64 que decodifica errado no
  sistema de destino. Os digests são conferidos contra **valores publicados** (RFC
  1321, FIPS 180), e não contra o próprio `hashlib` — comparar com `hashlib` provaria
  apenas que o módulo chama o `hashlib`.
- **`teste_tail.py`, "caractere UTF-8 multibyte cortado na fronteira".** Um `ç` em
  UTF-8 são dois bytes. Se o processo gravou o primeiro e ainda não o segundo,
  `bytes.decode` produziria um **U+FFFD permanente** no lugar de um caractere que
  chega inteiro no milissegundo seguinte — e o log mostraria lixo. O
  `codecs.getincrementaldecoder` segura os bytes incompletos; é o motivo de ele
  existir. Se este teste quebrar, alguém trocou o decodificador vivo por um
  `decode` avulso.
- **`teste_tail.py`, "pausado, nenhuma leitura NOVA acontece".** A garantia é
  precisa e vale ler antes de "consertar": `pausar()` só volta quando o worker está
  fora da leitura (há um lock), mas um lote lido no instante anterior ao clique
  **ainda chega**, porque descartá-lo perderia linhas para sempre — o offset já
  avançou e não há como des-ler. O teste drena a fila antes de medir. Numa versão
  anterior, `pausar()` só baixava uma bandeira e o worker seguia lendo por uma volta
  inteira; a suíte passava por sorte de temporização e a fumaça com um processo
  gravando de verdade pegou o vazamento.
- **`teste_xlsx.py`, "sem edição, salvar devolve os MESMOS bytes" e "o gráfico
  sai IDÊNTICO".** São os dois testes centrais da etapa 13, e existem porque o
  caminho óbvio falha nos dois **em silêncio**: `openpyxl.load_workbook()`
  seguido de `.save()` produz um arquivo perfeitamente válido, só que sem os
  gráficos, sem as tabelas dinâmicas e sem os comentários encadeados. O usuário
  corrige um número num relatório e descobre semanas depois. Se estes testes
  quebrarem, alguém trocou o patch por uma regravação — leia
  `textforge/planilha/__init__.py` antes de "consertar" o teste.
- **`teste_xlsx.py`, "célula FORA do `<dimension>` declarado é lida assim
  mesmo".** Em modo streaming o openpyxl acredita no `<dimension ref="A1:D4"/>`
  da aba e para de ler ali. E `dimension` mente com frequência — programas que
  geram planilha o escrevem estreito demais. Sem o `reset_dimensions()` do
  `leitor.py`, uma coluna inteira que **existe** no arquivo simplesmente não
  apareceria na grade, e nada avisaria.
- **`teste_csv.py`, "Registro não é linha".** Um campo entre aspas pode conter
  `\n`. Dividir o CSV por linha parte o registro ao meio e desloca a tabela
  inteira dali para a frente. `dividir_registros` varre respeitando as aspas, e a
  junção com `\n` reconstrói o texto exato — é o que sustenta o teste acima.

- **`teste_instancia_unica.py`, seção 4.** Neste Qt (6.11 no Windows), destruir um
  `QLocalSocket` antes de os bytes drenarem **descarta os bytes**, e
  `bytesToWrite()` / `flush()` / `waitForBytesWritten()` não são confiáveis para
  detectar isso — devolvem `False` mesmo quando a escrita deu certo. Numa versão
  anterior, três envios seguidos entregavam **um** pedido só: exatamente o caso de
  selecionar vários arquivos no Explorer e mandar abrir. A espera pela confirmação
  em `enviar_para_instancia_existente` é o que corrige. Se ela for removida
  "porque parece redundante", esta seção quebra.
- **`teste_tarefas.py`, seção 4.** Uma exceção dentro de um `QRunnable` não sobe
  para o `sys.excepthook`: o Qt aborta o processo sem mensagem. O
  `except BaseException` em `Tarefa.run` é o que impede isso.
- **`teste_configuracao.py`, seção 1.** `padrao()` tem de devolver um objeto novo
  a cada chamada. Devolvendo uma constante de módulo, o primeiro módulo que
  alterasse o dicionário contaminaria todos os `carregar()` seguintes.

## Consumo em disco e tempo

Quase todas as suítes escrevem só em pastas temporárias de poucos KB, apagadas no
fim mesmo quando o teste estoura.

A exceção é **`teste_indice_grande.py`**: ele gera **~200 MB** em
`%TEMP%\textforge-testes` (e **~1 GB** com `--gigante`) e apaga no `finally`,
mesmo se estourar no meio. Ele é a suíte mais lenta da rodada, e por isso tem um
teto próprio de 900 s em `LIMITE_PROPRIO_S` — o teto geral continua em 180 s de
propósito, para um diálogo modal esquecido aparecer em segundos em vez de pendurar
a rodada.

Sem ele, a rodada leva ~30 s, dominada pelos processos filhos do teste de
instância única.

## Limites conhecidos

Escrito aqui para ninguém confundir "a suíte passou" com "está coberto":

- Nenhum teste exercita arquivo grande em **compartilhamento de rede** (`Y:`).
  O `QFileSystemWatcher` perde eventos em SMB, e é por isso que o `vigia.py` tem
  polling — mas a verificação disso é manual.
- Nenhum teste escreve no **registro do Windows**. O `associar.ps1 -Simular`
  mostra o que faria; validar o "Abrir com" de verdade exige uma passada manual.
- Nenhum teste exercita **pasta somente leitura** (o caso do `Y:\Sunset`). O
  caminho de contingência do `gravar_atomico` é testado com `monkeypatch`, não
  contra uma unidade real.
- Os testes de interface rodam com `QT_QPA_PLATFORM=offscreen`. Eles provam que a
  lógica e o desenho não estouram, **não** que a aparência está correta.
