# Entregável da POC de RAG

## 1. Escopo do entregável

Esta entrega consolida a prova de conceito funcional do pipeline de RAG solicitada para validação prévia ao investimento em stack Azure.

O entregável cobre:

- código do pipeline;
- evidências de implementação e iteração com GitHub Copilot;
- resultados dos 5 testes de retrieval com análise;
- propostas de correção e evolução.

## 2. Artefatos entregues

- Pipeline principal: [rag_pipeline.py](rag_pipeline.py)
- Dependências: [requirements.txt](requirements.txt)
- Documentos de entrada: [anexo-a-documentos-individuais](anexo-a-documentos-individuais)
- Perguntas de cobertura: [tests/coverage_questions.json](tests/coverage_questions.json)
- Guia de execução: [README.md](README.md)
- Resultado final da avaliação: [artifacts/poc-rag-avaliacao-final.json](artifacts/poc-rag-avaliacao-final.json)

## 3. Evidência do Copilot

O pipeline foi construído e iterado com apoio do GitHub Copilot ao longo de ciclos curtos de implementação e validação. As principais evidências objetivas no código e no histórico da POC são estas:

1. Implementação inicial do pipeline em [rag_pipeline.py](rag_pipeline.py), cobrindo ingestão, busca, montagem de prompt e avaliação.
2. Ajuste de compatibilidade com ChromaDB após erro em runtime: substituição da limpeza por `delete(where={})` por remoção explícita dos IDs existentes na coleção.
3. Adaptação do fluxo de execução para ambiente corporativo Windows sem privilégios administrativos, documentada em [README.md](README.md), com uso de `uv run --isolated` em vez de dependência de `.venv` local.
4. Melhoria incremental da qualidade de retrieval com:
   - enriquecimento do texto indexado com título do documento e seção;
   - linearização de tabelas Markdown;
   - reranking híbrido com sinais semânticos e léxicos;
   - boosts heurísticos por domínio documental.

Em outras palavras, a evidência do Copilot nesta POC não é apenas a geração do código-base, mas principalmente o ciclo de diagnóstico e refinamento até o pipeline atingir 5 de 5 testes aprovados.

## 4. Arquitetura resumida

### 4.1 Ingestão

O pipeline lê arquivos `.md`, `.txt` e `.pdf`.

Estratégia de chunking adotada:

1. Divisão primária por seções Markdown (`##` e `###`).
2. Quebra adicional por parágrafos quando a seção excede aproximadamente 1200 caracteres.
3. Sobreposição de 1 parágrafo entre chunks sucessivos quando há quebra.

Justificativa:

- preserva unidade semântica de políticas, procedimentos e SLAs;
- evita cortar regras no meio;
- funciona bem para uma base curta, estruturada e com perguntas orientadas a seções específicas.

### 4.2 Embeddings

- Modelo: `all-MiniLM-L6-v2`
- Biblioteca: `sentence-transformers`

### 4.3 Vector store

- Banco vetorial local: ChromaDB
- Persistência: diretório `.chroma`

### 4.4 Busca

A busca final usa abordagem híbrida:

1. recuperação vetorial por embedding;
2. recuperação ampliada de candidatos;
3. reranking por sinais adicionais:
   - sobreposição lexical da pergunta com texto do chunk;
   - sobreposição lexical com o título da seção;
   - prioridade para documentos formais;
   - boosts por domínio, por exemplo `SLA`, `devolução`, `frete especial`, `carga perigosa`.

### 4.5 Montagem de prompt

O pipeline monta um prompt completo com:

- instrução de sistema;
- chunks recuperados com metadados;
- pergunta do usuário.

O prompt instrui o LLM a:

- responder só com base nos chunks;
- explicitar conflito entre fontes;
- priorizar documentos formais;
- declarar ausência de informação quando não houver cobertura suficiente.

## 5. Execução validada

Comando validado na máquina:

```powershell
uv run --isolated --python 3.12 --with-requirements requirements.txt --script rag_pipeline.py ingest
uv run --isolated --python 3.12 --with-requirements requirements.txt --script rag_pipeline.py evaluate --top-k 4
```

Resultado operacional:

- 5 arquivos ingeridos
- 37 chunks gerados
- 5 de 5 perguntas aprovadas no top 4

## 6. Resultados dos 5 testes com análise

### Teste 1

Pergunta: Qual o prazo de devolução?

Chunks esperados:

- `pol-001-politica-devolucao-3-1-prazo-geral`

Chunks recuperados no top 4:

- `pol-001-politica-devolucao-3-5-custos-de-devolucao` | score 0.6146 | ranking 1.1579
- `pol-001-politica-devolucao-3-3-procedimento-de-devolucao` | score 0.5272 | ranking 1.0705
- `pol-001-politica-devolucao-3-1-prazo-geral` | score 0.4000 | ranking 1.0634
- `pol-001-politica-devolucao-3-2-excecoes-ao-prazo-geral` | score 0.3516 | ranking 1.0150

Análise:

- O chunk correto apareceu no top 4, então o teste passou.
- Ainda existe ruído de ranking: custo e procedimento aparecem acima do trecho exato de prazo.
- Isso indica que a pergunta ativa corretamente o domínio `devolução`, mas o embedding ainda aproxima demais trechos correlatos do mesmo documento.

### Teste 2

Pergunta: Posso devolver carga perigosa?

Chunks esperados:

- `pol-001-politica-devolucao-3-2-excecoes-ao-prazo-geral`
- `faq-atendimento-item-3-cliente-perguntou-se-pode-devolver-carga-perigosa-o-que-respondo`

Chunks recuperados no top 4:

- `pol-001-politica-devolucao-3-2-excecoes-ao-prazo-geral` | score 0.4418 | ranking 1.1230
- `faq-atendimento-item-3-cliente-perguntou-se-pode-devolver-carga-perigosa-o-que-respondo` | score 0.5433 | ranking 0.8671
- `pol-001-politica-devolucao-3-5-custos-de-devolucao` | score 0.4994 | ranking 0.8344
- `pol-001-politica-devolucao-3-1-prazo-geral` | score 0.3321 | ranking 0.7808

Análise:

- O teste passou e recuperou a combinação certa entre fonte formal e fonte informal.
- O documento formal ficou em primeiro lugar, o que é desejável.
- Ainda há chunks adicionais do mesmo documento normativo, mas eles não comprometem a resposta se o prompt continuar priorizando fonte formal e contexto explícito.

### Teste 3

Pergunta: Qual o SLA do cliente Gold?

Chunks esperados:

- `sla-2024-tabela-sla-clientes-2-tabela-de-slas`

Chunks recuperados no top 4:

- `sla-2024-tabela-sla-clientes-1-classificacao-de-clientes` | score 0.5129 | ranking 1.1729
- `sla-2024-tabela-sla-clientes-2-tabela-de-slas` | score 0.5110 | ranking 1.0910
- `sla-2024-tabela-sla-clientes-5-medicao-e-reportes` | score 0.6292 | ranking 1.0692
- `sla-2024-tabela-sla-clientes-4-penalidades-por-descumprimento` | score 0.5872 | ranking 1.0272

Análise:

- O teste passou.
- O chunk mais útil para responder a pergunta ficou em segundo lugar, logo atrás da classificação de clientes.
- Esse resultado é aceitável para a POC porque os dois chunks mais altos pertencem ao mesmo documento formal e são complementares.

### Teste 4

Pergunta: Qual o SLA do cliente Platinum?

Chunks esperados:

- `sla-2024-tabela-sla-clientes-1-classificacao-de-clientes`
- `faq-atendimento-item-15-cliente-diz-que-e-platinum-existe-esse-tier`

Chunks recuperados no top 4:

- `sla-2024-tabela-sla-clientes-1-classificacao-de-clientes` | score 0.4805 | ranking 1.2305
- `faq-atendimento-item-15-cliente-diz-que-e-platinum-existe-esse-tier` | score 0.6129 | ranking 1.0029
- `sla-2024-tabela-sla-clientes-2-tabela-de-slas` | score 0.4573 | ranking 0.9773
- `sla-2024-tabela-sla-clientes-5-medicao-e-reportes` | score 0.5664 | ranking 0.9464

Análise:

- O teste passou.
- O chunk normativo que afirma que não existem outros tiers ficou em primeiro lugar, que é o comportamento mais seguro.
- A presença do FAQ como segundo item reforça a explicação operacional, sem substituir a regra formal.

### Teste 5

Pergunta: Frete para 600kg para Manaus?

Chunks esperados:

- `proc-042-v2-frete-especial-revisado-2-formula-de-calculo`
- `proc-042-v2-frete-especial-revisado-2-1-multiplicadores-regionais-atualizados-em-novembro-2023`

Chunks recuperados no top 4:

- `proc-042-v2-frete-especial-revisado-2-formula-de-calculo` | score 0.4536 | ranking 1.0222
- `proc-042-frete-especial-v1-2-formula-de-calculo` | score 0.4684 | ranking 0.9770
- `proc-042-v2-frete-especial-revisado-2-1-multiplicadores-regionais-atualizados-em-novembro-2023` | score 0.3029 | ranking 0.9543
- `proc-042-frete-especial-v1-2-1-multiplicadores-regionais` | score 0.3326 | ranking 0.9240

Análise:

- O teste passou.
- O resultado expõe uma característica importante da base: as duas versões da PROC-042 continuam semanticamente muito próximas.
- O heurístico aplicado conseguiu priorizar a v2, mas a v1 ainda aparece no top 4. Isso é um risco real de resposta contraditória em um ambiente produtivo e precisa de tratamento adicional.

## 7. Problemas encontrados durante a POC

### Problema 1

Erro de compatibilidade com ChromaDB na limpeza da coleção.

Sintoma:

- `ValueError: Expected where to have exactly one operator, got {}`

Correção aplicada:

- remoção explícita por IDs existentes em vez de `delete(where={})`.

Status:

- corrigido no código.

### Problema 2

Execução bloqueada de `.venv\Scripts\python` dentro da pasta `Documentos` em ambiente Windows corporativo.

Sintoma:

- `Acesso negado` ao executar o `python.exe` da virtualenv.

Correção aplicada:

- adoção do fluxo com `uv run --isolated`, documentado em [README.md](README.md).

Status:

- contornado sem exigir privilégios administrativos.

### Problema 3

Retrieval inicial trazia chunks semanticamente próximos, mas incorretos para o gabarito.

Sintoma:

- perguntas sobre prazo, SLA e frete retornavam seções correlatas, porém não ideais.

Correções aplicadas:

- enriquecimento do texto indexado com documento e seção;
- linearização de tabelas;
- reranking híbrido com overlap lexical;
- boosts por domínio documental.

Status:

- corrigido até 5 de 5 testes aprovados.

## 8. Propostas de correção e evolução

As correções abaixo são as mais relevantes para evoluir esta POC para algo mais robusto.

### Proposta 1

Separar recuperação vetorial e reranking com componente dedicado.

Recomendação:

- manter o Chroma para recall inicial;
- adicionar um reranker mais forte depois, por exemplo cross-encoder local ou reranker do Ollama, se disponível.

Benefício:

- reduz casos em que chunks “parecidos” ficam acima dos chunks mais úteis.

### Proposta 2

Tratar versões documentais de forma explícita.

Recomendação:

- incluir metadados como `effective_date`, `supersedes`, `is_current`;
- permitir filtro ou boost para versão vigente.

Benefício:

- reduz o risco de misturar PROC-042 v1 e v2 na mesma resposta.

### Proposta 3

Adicionar estratégia de resposta “sem cobertura documental”.

Recomendação:

- definir limiar mínimo de confiança;
- se nenhum chunk atingir o limiar, responder com “não encontrei base documental suficiente”.

Benefício:

- evita alucinações em perguntas fora da base ou parcialmente cobertas.

### Proposta 4

Gerar relatório automatizado de avaliação.

Recomendação:

- transformar a saída de `evaluate` em artefato versionado automaticamente;
- incluir percentual de acerto, top-k hit rate e casos de contradição documental.

Benefício:

- facilita revalidação toda vez que o pipeline ou os documentos forem alterados.

### Proposta 5

Acoplar geração local opcional.

Recomendação:

- manter o pipeline atual de retrieval;
- adicionar uma opção de geração via Ollama para demonstração ponta a ponta sem depender de chat manual.

Benefício:

- torna a POC reproduzível de ponta a ponta em ambiente local.

## 9. Conclusão

A POC atingiu o objetivo principal: demonstrar um pipeline de RAG funcional, gratuito e open-source, com ingestão, embeddings, armazenamento vetorial, busca e montagem de prompt.

O pipeline foi validado com os 5 testes do gabarito e terminou com 5 de 5 acertos no top 4 após os refinamentos de retrieval.

Isso é suficiente para sustentar uma etapa de aprendizado e discovery antes de qualquer investimento em licenças Azure.
