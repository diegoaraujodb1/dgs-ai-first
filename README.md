# dgs-ai-first

Repositório da trilha de Formação - DGS AI First

## POC de RAG local

Este repositório agora inclui uma prova de conceito mínima de RAG com stack gratuita e open-source:

- Python
- ChromaDB como vector store local
- sentence-transformers com o modelo all-MiniLM-L6-v2 para embeddings
- Orquestração manual em Python, sem dependência de API proprietária

### Estrutura adicionada

- `anexo-a-documentos-individuais/`: 5 documentos Markdown da NovaTech usados na ingestão
- `rag_pipeline.py`: ingestão, busca, montagem de prompt e avaliação simples
- `tests/coverage_questions.json`: 5 perguntas baseadas no mapa de cobertura do Anexo B
- `requirements.txt`: dependências da POC

### Estratégia de chunking

O chunking é orientado por seções Markdown:

1. Cada documento é dividido por headings (`##`, `###`) para preservar unidade semântica.
2. Se uma seção ultrapassar ~1200 caracteres, ela é quebrada por parágrafos com sobreposição de 1 parágrafo.
3. Tabelas pequenas permanecem junto da seção em que aparecem, o que evita separar contexto e valores.

Essa estratégia é adequada para a POC porque os documentos têm estrutura editorial clara e perguntas costumam mirar seções específicas, como prazo, exceções, multiplicadores ou tiers.

### Como executar

```powershell
uv run --isolated --python 3.12 --with-requirements requirements.txt --script rag_pipeline.py ingest
uv run --isolated --python 3.12 --with-requirements requirements.txt --script rag_pipeline.py search --question "Qual o prazo de devolução?" --top-k 3
uv run --isolated --python 3.12 --with-requirements requirements.txt --script rag_pipeline.py prompt --question "Frete para 600kg para Manaus?" --top-k 4
uv run --isolated --python 3.12 --with-requirements requirements.txt --script rag_pipeline.py evaluate --top-k 4
```

### Fluxo recomendado em ambiente corporativo

Se a máquina bloquear a execução de `.exe` dentro da pasta `Documentos`, prefira `uv run --isolated`.
Nesse modo, o `uv` cria um ambiente efêmero fora da pasta do projeto e executa o script sem exigir privilégios de administrador.

Primeira execução típica:

```powershell
uv run --isolated --python 3.12 --with-requirements requirements.txt --script rag_pipeline.py ingest
```

Observações práticas:

- A primeira execução pode demorar porque `sentence-transformers` instala `torch`.
- Não é necessário ativar `.venv` nem instalar Python como administrador para esse fluxo.
- Se a sua política corporativa bloquear execução em `Documentos`, `uv run` tende a funcionar melhor que `.venv\Scripts\python`.

### Fluxo alternativo com virtualenv local

Se a sua máquina permitir executar binários dentro da pasta do projeto, você também pode usar uma virtualenv tradicional:

```powershell
uv venv .venv --seed
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python rag_pipeline.py ingest
```

Se `python.exe` dentro de `.venv\Scripts` retornar `Acesso negado`, volte para o fluxo com `uv run --isolated`.

### O que cada comando faz

- `ingest`: lê os documentos, gera chunks, cria embeddings e persiste no ChromaDB local.
- `search`: gera embedding da pergunta, recupera os chunks mais similares e imprime score de similaridade.
- `prompt`: monta um prompt completo pronto para colar no Claude ou em outro LLM.
- `evaluate`: roda 5 perguntas de cobertura e mostra se os chunks esperados apareceram no topo.

### Observações

- O pipeline aceita `.md`, `.txt` e `.pdf`. Para PDF, a extração usa `pypdf`.
- O prompt privilegia documentos formais e instrui o LLM a explicitar conflitos ou ausência de base documental.
- Para esta POC, o LLM fica fora do código: a saída do comando `prompt` pode ser colada manualmente no Claude ou usada com Ollama em uma etapa posterior.
- Em ambientes Windows corporativos, bloqueio de execução em `Documentos` pode afetar `.venv\Scripts\python` mesmo quando o Python instalado em `AppData` funciona normalmente.
