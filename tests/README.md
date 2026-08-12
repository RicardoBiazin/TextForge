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

| Arquivo | O que cobre | Precisa de |
|---|---|---|
| `teste_configuracao.py` | `padrao()` cobre o requisito 30, round-trip, config corrompido, merge de chave nova, pastas de `%APPDATA%`, modo portátil, `sys._MEIPASS`, lista de recentes | nada |
| `teste_cli.py` | `--line`, `--col`, vários arquivos, caminho relativo, e a **recusa** de dispositivos do Windows (`CON`, `NUL`, `COM1`, `LPT1`, `PRN`, `AUX`) | nada |
| `teste_tarefas.py` | progresso limitado a 10 Hz, cancelamento cooperativo, exceção no worker virando sinal, pools separados | PySide6 |
| `teste_instancia_unica.py` | canal por usuário, entrega **entre processos**, 5 processos simultâneos, lixo no canal, pipe órfão | PySide6 |

`ajudante_enviar.py` não é uma suíte — é o processo auxiliar que o
`teste_instancia_unica.py` dispara.

## Regressões que estas suítes guardam

São os casos em que o código *parecia* certo e não estava. Se um destes testes
quebrar, leia o comentário no código antes de "consertar" o teste.

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

Hoje as suítes escrevem só em pastas temporárias de poucos KB, apagadas no fim
mesmo quando o teste estoura. A rodada completa leva ~30 s, dominada pelos
processos filhos do teste de instância única.

Quando a etapa 10 entrar, `teste_indice_grande.py` vai gerar **~200 MB** em
`%TEMP%\textforge-testes` (e 1 GB com `--gigante`), apagando no fim.

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
