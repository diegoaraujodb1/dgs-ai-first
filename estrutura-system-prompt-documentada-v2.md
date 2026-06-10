## O que mudou do v1 para o v2

**R5 — Sem comparação entre tiers.** Essa restrição protege o negócio de uma situação comum: o cliente perguntar "meu SLA é pior que o de outros?" e o assistente confirmar inadvertidamente que sim. A instrução é positiva — "informe apenas o SLA do tier em atendimento" — o que é mais robusto que uma instrução negativa ("não compare"), pois guia o comportamento esperado em vez de apenas proibir um.

**R6 — Região do frete = destino da pergunta.** Essa foi a maior vulnerabilidade do v1. O campo `região` nos dados do cliente (Sudeste) poderia ser usado pelo modelo como atalho para calcular fretes, mesmo quando o destino real era diferente. A correção está em dois lugares: na regra do system prompt e em um aviso explícito no bloco de contexto dinâmico, logo abaixo dos dados do cliente. Reforço duplo porque esse tipo de erro semântico — usar o dado mais saliente em vez do dado correto — é frequente em modelos.

**R7 — Explicitar lacunas parciais.** A versão anterior tratava ausência como binário: "encontrou" ou "não encontrou". Mas a pergunta sobre frete para Manaus mostrou um caso intermediário — o multiplicador existe, o valor base não. A R7 instrui o modelo a sempre decompor o que sabe do que não sabe, em vez de tratar a resposta parcial como resposta completa ou como ausência total.

---

## Impacto no orçamento de tokens

O system prompt cresceu de ~280 para ~380 tokens (+100 tokens), principalmente pelo detalhamento das novas regras e pelo aviso de região no bloco dinâmico. O budget total de 4K tokens permanece confortável — há ~3.125 tokens livres para histórico de conversa e expansão futura de chunks.
