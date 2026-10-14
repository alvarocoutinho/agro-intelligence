# Roadmap técnico

## P0 — Engenharia e reprodutibilidade

- [ ] Ler resultados V8 e reproduzir baseline localmente.
- [ ] Substituir `REFERENCIA = date(2026,10,14)` por referência parametrizável, preservando a data de referência da auditoria.
- [ ] Remover asserts fixos `31` e `3926`, usando checagens estruturais e tolerância a novas observações.
- [ ] Persistir SQLite com tipos de dados corretos, restrições de unicidade e documentação de schema.
- [ ] Criar testes para unidades, falta de observações, dados repetidos, outliers e preços negativos.
- [ ] Adicionar Makefile/comandos `test`, `audit`, `collect`, `build`.

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

## Foco funcional

Não confundir a amostra de FAO atacado/varejo com preços efetivos recebidos pelo produtor.
A base atual NÃO contém soja nem dados de custo necessários para simulação de margem.
