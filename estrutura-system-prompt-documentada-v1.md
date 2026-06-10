## Estrutura de contexto documentada

### Partes estáticas (~280 tokens — toda query)

O system prompt contém identidade do assistente, as 4 regras de comportamento, a regra de desempate por versão e o formato de saída esperado. Essa camada raramente muda — apenas em releases formais de produto — e representa o "contrato" do assistente. Por isso vai antes de tudo e nunca é truncada.

### Partes dinâmicas (~260–320 tokens — mudam por query)

Os chunks recuperados via RAG e os dados do cliente (tier, região, ID) são injetados por template a cada request. A ordem importa: chunks aparecem após os dados do cliente, o que faz o modelo contextualizar o cliente antes de ler a documentação. Os metadados de cada chunk incluem obrigatoriamente `id` e `version` — são esses campos que resolvem conflitos (a regra "prevalece a versão mais recente" só funciona se o modelo puder comparar datas).

### Parte runtime (~variável — cresce ao longo da conversa)

O histórico de turns é inserido por último. Quando o contexto total se aproxima do limite, a estratégia recomendada é: preservar o system prompt inteiro + os últimos 3 turns + os chunks do turno atual. Descartar chunks antigos é preferível a descartar o system prompt ou truncar o turn corrente.

---

## Decisões de design e justificativas

**Ordem: system → dados do cliente → chunks → histórico.** Colocar os dados do cliente antes dos chunks faz o modelo "saber quem é o cliente" antes de ler a tabela de SLA, o que evita que ele cite o prazo errado para o tier errado.

**Metadado de versão nos chunks.** A regra de desempate só pode ser aplicada se o modelo tiver acesso à versão de cada documento. Sem esse campo, a instrução "use a fonte mais atual" é inoperante.

**Formato de saída explícito no system prompt.** Exigir `[Fonte: ID-DO-DOCUMENTO]` no final de cada resposta e `[Informação não encontrada — recomendo escalar para o supervisor]` quando ausente transforma as regras 1, 2 e 3 em comportamentos verificáveis — o que facilita avaliação automática (você consegue checar por regex se a resposta seguiu as regras).
