# Prompt inicial para Codex

Analise este repositório Agro Intelligence. Leia AGENTS.md, README.md, docs/ROADMAP.md,
docs/RELATORIO_TECNICO_V8.md e docs/baseline_v8.json. Antes de escrever novas features,
explique a arquitetura e identifique dívida técnica. Em seguida:

1. Execute os testes `python -m unittest discover -s tests -v`.
2. Faça uma refatoração incremental de `src/agro/pipeline_v8.py` para remover as contagens
   fixas (31 séries e 3926 observações) e parametrizar a data de referência. Não mude as
   regras de qualidade nem os resultados da baseline 2026-10-14.
3. Crie fixtures sintéticas para testes offline, incluindo ausência de meses, repetição
   de UUID/data, unidades 10/30/50/60 kg, dados estranhos, spread negativo e novos meses.
4. Documente comandos reproduzíveis e a estrutura de armazenamento com dados brutos e normalizados.
5. Não use scraping proibido, não desabilite TLS, não publique dados FAO/CONAB sem revisar licenças.

Após concluir, proponha PR com testes, justificativa e relatório do que mudou. Não implemente
um dashboard antes de estabilizar a coleta e o modelo de dados.
