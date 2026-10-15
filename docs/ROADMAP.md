# Roadmap técnico

## P0 — Engenharia e reprodutibilidade

- [x] Ler resultados V8 e comparar a auditoria estrutural com a baseline.
- [ ] Reproduzir a geração V8 a partir do ZIP V7 original.
- [x] Substituir `REFERENCIA = date(2026,10,14)` por referência parametrizável, preservando a data de referência da auditoria.
- [x] Remover asserts fixos `31` e `3926`, usando checagens estruturais e tolerância a novas observações.
- [x] Persistir SQLite V8 com contagens/flags inteiras, chaves de unicidade e documentação de schema.
- [x] Criar testes offline para unidades, falta de observações, dados repetidos, outliers e preços negativos.
- [ ] Adicionar Makefile/comandos `test`, `audit`, `collect`, `build`.

A refatoração foi validada com ZIP sintético e auditoria estrutural da saída. A reprodução
da baseline a partir do ZIP V7 original permanece pendente. O ZIP V8 enviado foi
aprovado na auditoria estrutural, com 31 séries e 3.926 observações. O schema SQLite V8 preserva valores decimais exatos como `TEXT`;
tipos inteiros e chaves primárias estão descritos em `docs/SCHEMA_V8.md`. O schema
legado V7 ainda precisa de revisão separada.

## P1 — Fontes brasileiras essenciais

- [ ] CONAB preço ao produtor: descobrir método permitido/documentado de ingestão, teste real e licenças.
- [ ] CONAB custos de produção: ingestão de arquivos, ano agrícola, sistema de produção e componentes de custo.
- [ ] MDIC Comex Stat: NCM, município/UF, mês, US$ FOB, kg líquidos, países de destino.
- [ ] Banco Central: séries econômicas e SICOR (testar arquivos oficiais de dados abertos).
- [ ] IBGE PAM/PPM/LSPA: consultas por cultura/município/ano, sem agregações inválidas.

## P2 — Modelagem analítica

- [ ] Dimensões `produto`, `mercado`, `localidade`, `etapa_comercial`, `unidade`, `fonte`.
- [ ] Série preço observada; custo observado; área/produção; comércio e clima, sem joins espúrios.
- [ ] Indicadores sazonais, variação, spread, variação cambial, margem agrícola somente com comparabilidade.
- [ ] Analisar 89 pares varejo < atacado e divergência auxiliar de metadados FAO.
- [ ] Monitorar atualizações e lacunas das séries, com proveniência e checkpoint.

## P3 — Produto

- [ ] API interna read-only (FastAPI) e dashboard (Streamlit ou frontend), após pipeline estabilizado.
- [ ] Processos agendados e painel de saúde dos conectores.
- [ ] Teste de licenciamento/termos de redistribuição por fonte e rota.

Um primeiro webapp read-only já explora dados sintéticos e V8 local opt-in, com conectores
BCB SGS 1 e IBGE PAM 1612 testados por fixtures. A consulta real a BCB/IBGE ainda depende
de liberação dos domínios no ambiente cloud e validação de resposta ao vivo. MDIC,
CONAB produtor/custos, FAO ao vivo, atualização agendada e revisão de licenças seguem
pendentes antes de considerar o produto completo.

## Foco funcional

Não confundir a amostra de FAO atacado/varejo com preços efetivos recebidos pelo produtor.
A base atual NÃO contém soja nem dados de custo necessários para simulação de margem.
