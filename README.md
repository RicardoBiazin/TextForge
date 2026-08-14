# TextForge

Editor de arquivos técnicos para Windows: `.txt` `.log` `.dat` `.csv` `.ini`
`.json` `.xml` `.yaml` `.py` `.php` `.js` `.ts` `.html` `.css` `.sql` `.md`
`.bat` `.ps1` `.sh` e o resto do que aparece no dia a dia.

Existe para o que o Bloco de Notas não faz e a IDE faz pesado demais: abrir um
arquivo, olhar, procurar, corrigir e fechar — sem esperar indexação de projeto e
sem corromper a codificação no caminho.

**O que ele nunca faz** — e isso é projeto, não omissão:

- não executa nada do que você abre. Um `.py`, um `.bat` ou um `.ps1` é **dado**,
  e é exibido como texto. Não há comando "Executar", e não haverá.
- não altera arquivo em silêncio. Codificação, BOM, fim de linha, indentação e a
  ausência de quebra final são **preservados** ao salvar.
- não formata nada sozinho. Formatar é sempre uma ação sua.
- não é editor de documentos. DOC e DOCX estão fora de escopo.

---

## Instalação a partir do fonte

```bat
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

Opcionais (o programa funciona inteiro sem eles):

```bat
.venv\Scripts\python.exe -m pip install -r requirements-extras.txt
```

`lxml` melhora a fidelidade do XML (sem ele, formatar um XML **com CDATA** é
recusado em vez de corrompido). `black` liga o formatador de Python — sem ele,
"Formatar documento" num `.py` avisa em vez de aplicar uma indentação caseira, que
é o caminho mais curto para quebrar código, porque em Python a indentação **é** a
sintaxe.

> **Ao gerar o `.exe`, instale as opcionais ANTES.** Elas entram no pacote se
> estiverem no venv na hora do build; num executável já gerado, `pip install` não
> resolve nada. O `--autoverificacao` do `build.bat` imprime quais foram incluídas,
> justamente para isso não passar despercebido.

## Gerar o executável

```bat
build.bat              :: dist\TextForge\    (one-dir, recomendado)
build.bat umarquivo    :: dist\TextForge.exe (portátil, um arquivo só)
```

### Qual dos dois copiar

Medido nesta máquina, e não estimado:

| | one-dir (padrão) | one-file (`umarquivo`) |
|---|---|---|
| O que copiar | a **pasta** `dist\TextForge\` inteira | só o `TextForge.exe` |
| Tamanho | 92 MB em 165 arquivos | **38,6 MB**, um arquivo |
| Partida | **~1,5 a 2,4 s** | ~2,8 a 3,9 s, toda vez |
| Processos no Gerenciador | 1 | 2 (normal — ver abaixo) |

**Por que o one-file demora mais.** O log registra quanto tempo o programa gasta
depois que o Python começa (`partida: JANELA NA TELA`). Medido: **0,4 s** no
one-file e 1,2 s no one-dir. Ou seja, no portátil **2,4 a 3,5 s se passam antes de o
Python existir** — é o bootloader descompactando 38 MB em `%TEMP%` e o antivírus
varrendo o que saiu. Não é o programa, é o modo de empacotamento.

**A primeira abertura de todas é a mais lenta** (pode passar de 10 s): o Windows
Defender faz uma varredura completa de um `.exe` que nunca viu. As seguintes são as
da tabela. Se isso incomodar, use o one-dir ou adicione a pasta às exclusões do
Defender.

**No one-dir, o `TextForge.exe` sozinho não funciona.** Ele tem 2,7 MB; os outros
97 MB estão em `_internal\` (Qt, Python, os recursos). Copiar só o `.exe` produz um
erro do Windows na abertura — foi verificado.

Por isso o `build.bat` gera, além da pasta, **`dist\TextForge-0.1.0-win64.zip`**
(39 MB comprimido) com a pasta `TextForge\` na raiz — extrair no Explorer produz a
pasta certa em vez de despejar 169 arquivos onde você estiver. Dentro do ZIP vai um
**`ARQUIVOS.txt`** listando tudo agrupado por função, dizendo o que quebra se cada
grupo faltar; o mesmo arquivo fica em `dist\TextForge-0.1.0-arquivos.txt`.

Nada precisa ser instalado, nada é escrito fora da pasta do programa e de
`%APPDATA%\TextForge`, e não é preciso administrador.

**No one-file**, o `.exe` basta. O preço é que ele descompacta ~38 MB em `%TEMP%` **a
cada abertura**, o que custa 4 a 6 s de partida — num editor aberto dezenas de vezes
por dia isso incomoda. E ele aparece como **dois** processos no Gerenciador de
Tarefas: o bootloader que descompacta e o programa de verdade. É normal do
PyInstaller, não são duas instâncias — o que importa para a instância única é que
abrir um segundo arquivo não crie um segundo *par*.

O `build.bat` roda a suíte **antes** de empacotar e uma fumaça do `.exe` **depois**
(`TextForge.exe --autoverificacao`). Excludes agressivos quebram o programa só em
tempo de execução; sem a fumaça, isso chegaria como relatório de bug do usuário.

## Registrar em "Abrir com"

```powershell
.\associar.ps1 .log .xml .csv        # registra SÓ o que você pedir
.\associar.ps1 .log -Simular         # mostra o que faria, sem escrever
.\associar.ps1 -Remover              # desfaz
```

Escreve **apenas em HKCU** — sem administrador. Usa `OpenWithProgids`, que
**acrescenta** o TextForge à lista "Abrir com" sem roubar o programa padrão: seu
`.xml` continua abrindo no que você já usa.

**Aviso honesto:** no Windows 11 o item do menu de contexto aparece em *"Mostrar
mais opções"*. O menu novo exige uma extensão de shell `IExplorerCommand`
empacotada em MSIX, e isso não sai de um script.

---

## O que ele faz

**Arquivo.** Abas, sessão restaurada, arrastar-e-soltar, arquivos recentes,
"Abrir com" com uma instância só, salvamento atômico (`ReplaceFileW`, que preserva
ACLs e fluxos alternativos), aviso de alteração externa com *Recarregar / Manter o
meu / Comparar*.

**Codificação (o motivo principal do programa existir).** Detecção em cascata:
BOM → binário? → UTF-16 sem BOM → UTF-8 estrito → codificação declarada →
charset-normalizer → cp1252. Se a leitura produzir um caractere inválido, a barra
de status mostra a codificação **em vermelho** e a aba entra em somente leitura —
salvar por cima de um arquivo que não foi lido direito destrói dados. Converter
avisa **antes**, listando os caracteres que seriam perdidos, com o nome Unicode de
cada um.

**Seleção em bloco (por coluna).** `Alt+arrastar` marca um **retângulo** em vez de
linhas inteiras. No editor, digitar altera todas as linhas na mesma coluna de uma
vez — e um `Ctrl+Z` desfaz tudo junto; uma linha curta demais é completada com
espaços até a coluna. No visor de arquivo grande é somente leitura, para copiar uma
coluna de um log de largura fixa. `Alt+Shift+setas` faz o mesmo pelo teclado, `Esc`
sai. As colunas são **visuais**: um TAB não vale uma coluna, então o retângulo sai
alinhado mesmo num arquivo indentado com TAB.

**Realce** para 23 linguagens, com contextos multi-linha de verdade: PHP dentro de
HTML, `<script>` e `<style>`, heredoc de PHP, comentário de bloco atravessando
linhas.

**Formatar e validar** XML, JSON, SQL, CSS, HTML e Python. Erro vai para um painel
navegável, não para um diálogo modal. Quando formatar **perderia informação**, o
programa **recusa** e explica — um JSON com chave duplicada não é reindentado, é
recusado, porque reindentar apagaria dados.

**Pesquisa** incremental com contador, regex com grupos, "na seleção", marcadores
na margem, e pesquisa em pasta com filtros, em thread cancelável.

**CSV em modo tabela.** Editar células numa grade e voltar para o texto. Sem
edição, o texto volta **byte a byte idêntico** — inclusive aspas desnecessárias e
espaços depois do delimitador.

**Arquivo grande.** Acima de 20 MB (ou com uma linha acima de 20 mil caracteres) o
arquivo abre num visor virtualizado, somente leitura, com índice esparso construído
em thread. 178 MB abrem em **0,01 s**. Rolar, ir para linha, pesquisar e copiar
continuam funcionando.

**Acompanhar log (tail).** Segue um `.log` que está sendo escrito, com pausar e
retomar, detecção de truncamento e de rotação, e teto de memória automático.

**Extras.** Base64, URL, HTML e JSON (escapar e desescapar), MD5/SHA-1/SHA-256/
SHA-512, paleta de comandos (`Ctrl+Shift+P`), abertura rápida (`Ctrl+P`).

---

## Onde ficam as coisas

| | |
|---|---|
| Configuração | `%APPDATA%\TextForge\config.json` |
| Log | `%APPDATA%\TextForge\textforge.log` |
| Erros não tratados | `%APPDATA%\TextForge\erro.log` |
| Sessão | `%APPDATA%\TextForge\sessao.json` |
| Recuperação | `%APPDATA%\TextForge\recuperacao\` |
| Temas do usuário | `%APPDATA%\TextForge\temas\*.json` |
| Linguagens do usuário | `%APPDATA%\TextForge\linguagens\*.json` |

**Modo portátil:** um `config.json` ao lado do `.exe` tem precedência sobre o de
`%APPDATA%`.

Não há diálogo de preferências, e é decisão consciente: **Ferramentas →
Configurações** abre o `config.json` numa aba do próprio editor, e salvar reaplica.
As ~40 chaves estão documentadas por comentário em
[configuracao.py](textforge/configuracao.py); o público deste programa edita JSON o
dia inteiro, e um diálogo seria mais interface para manter em sincronia com o
arquivo.

Um tema do usuário faz **merge** sobre o embutido — pode declarar só os três papéis
que quiser mudar.

---

## Privacidade e segurança

O modelo de ameaça em uma linha: **o TextForge abre arquivos não confiáveis que por
acaso são formatos executáveis.** Tudo decorre de *um arquivo é dado, sempre*.

- **Nada é executado.** `eval`, `exec`, `compile`, `os.system`, `subprocess` com
  `shell=True`, `pickle.load` e `yaml.load` sem `SafeLoader` são proibidos no
  pacote inteiro, e há um teste que **varre o próprio fonte** procurando por eles.
  `ast.parse` é permitido: analisa sem executar.
- **XML não expande DTD.** Entidade externa (XXE) e *billion laughs* são recusados
  com explicação e com um caminho de saída ("validar sem o DTD"), e não com uma
  parede.
- **O log nunca grava conteúdo de documento** — só caminhos e tamanhos. Um
  traceback com um trecho do seu arquivo dentro, enviado por e-mail, é vazamento
  de dados.
- **A pasta de recuperação guarda cópias em texto claro** em `%APPDATA%`. Se você
  edita arquivos sensíveis, use `recuperacao_pastas_excluidas` no `config.json`.

## Limites conhecidos

Escritos aqui para não serem descobertos no pior momento:

- Arquivo grande é **somente leitura**. Editar exigiria pilha de desfazer
  virtualizada e reescrever 1 GB a cada salvamento; o caso real é ler e pesquisar.
- `</script>` **dentro de uma string JavaScript** não fecha o bloco no realce (o
  navegador fecharia). Corrigir custaria uma busca separada por bloco no laço
  central do pintor.
- A barra de rolagem horizontal do visor de arquivo grande se ajusta à **maior
  linha já vista**, e cresce conforme você rola. Medir a linha mais longa de 1 GB
  exigiria lê-lo inteiro.
- A validação de SQL é **estrutural** (parênteses e apóstrofos), não sintática.
  Cada banco tem sua gramática, e prometer validação completa seria enganar.
- Não há filtro no acompanhamento de log. O que sairia barato filtraria só as
  linhas futuras, deixando o histórico completo na tela — confunde mais que ajuda.
- Nenhum teste exercita arquivo grande em **compartilhamento de rede** nem escreve
  no registro de verdade.

## Testes

```bat
.venv\Scripts\python.exe tests\rodar_todos.py
```

2.445 verificações em 31 suítes, sem pytest. `tests\README.md` diz o que cada suíte
cobre, quanto ocupa em `%TEMP%` e — a seção que importa — **quais regressões elas
guardam**.

`teste_indice_grande.py` gera ~200 MB em `%TEMP%` (1 GB com `--gigante`) e apaga no
fim.

## Licença

MIT — veja [LICENSE](LICENSE). PySide6-Essentials é LGPLv3, compatível.
PyQt e QScintilla ficaram **fora** de propósito: são GPL da Riverbank e
contaminariam a licença deste projeto.
