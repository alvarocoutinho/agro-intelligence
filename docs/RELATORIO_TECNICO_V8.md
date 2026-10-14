# Pipeline Agro V8 — Classificação econômica dos preços e painel pareado
**Referência dos testes:** 14/10/2026. **Insumo:** `resultados_agro_v7.zip`.

## Síntese da auditoria

- 31 UUIDs foram associados a metadados oficiais do FPMA (31/31).
- **Todas as 31 séries indicam como fonte primária a Companhia Nacional de Abastecimento — CONAB**; os dados aqui foram obtidos através da API FAO FPMA.
- 3.926 preços mensais preservados: **2.408 de atacado** e **1.518 de varejo**.
- **1.399 pares** correspondem ao mesmo produto, região e mês. **1.398** são utilizados em agregados devido à exclusão analítica de um valor suspeito, que continua preservado na base.
- **15/31 séries** terminaram há quatro meses ou mais em relação à data de referência; portanto, não representam preços correntes.
- **120 lacunas mensais internas** acumuladas nas 31 séries, sem interpolação automática.
- O campo `market_type` retornou `Retail` nas 31 séries, inclusive nas 19 cujo campo explícito `price_type` é `WHOLESALE`. A classificação primária por etapa baseia-se em `price_type`, com o campo auxiliar preservado para auditoria. São campos semanticamente distintos: a divergência merece anotação, não substituição.
- As séries abrangem arroz beneficiado tipo 1, feijão-preto, milho amarelo, farinha de trigo e trigo em grão. **Não há soja e não há preço ao produtor neste conjunto.**

## Indicador experimental: diferencial varejo/atacado

Para cada par comparável, a normalização usa `preço_original / massa_da_embalagem_em_kg`, sem aproximar fatores de 30 kg ou 60 kg. Calculamos `100 × (preço_varejo / preço_atacado − 1)`, **somente quando produto, localidade e mês coincidem**. Valores suspeitos ficam no CSV completo, mas fora de resumos.

Este diferencial **não é margem de lucro, nem margem bruta do varejista**. Pode incluir mercados heterogêneos, diferentes apresentações, custos, tributos e condições de comercialização. Não utilizar médias desses pares para inferir diferença nacional representativa.

### Resumo de 2025, amostra pareada

| Produto | Pares | Mediana do diferencial (%) |
|---|---:|---:|
| Feijão-preto | 40 | 3,7 |
| Arroz beneficiado tipo 1 | 48 | 8,9 |
| Farinha de trigo | 48 | 15,4 |

Esse resumo não é inflação, não é lucro e não é um levantamento representativo de todos os estabelecimentos do país.

## Tratamento de qualidade

1. Preços de origem, UUID, etapa, praça e unidade originais são preservados no SQLite herdado e no CSV enriquecido.
2. Preço por quilograma é recalculado a partir da massa física exata, sem a aproximação numérica do fator apresentado na API.
3. Índices nominais por série usam a **média mensal do ano de 2020 igual a 100**, apenas para séries com ao menos seis meses naquele ano; não são deflacionados.
4. O outlier de feijão-preto no atacado de São Paulo em fevereiro de 2016 permanece disponível, sinalizado.
5. São sinalizadas séries cuja última observação é anterior em quatro meses ou mais à data 14/10/2026.
6. O preenchimento de faltantes e a comparação com preços ao produtor **não** são executados automaticamente.

## Documentação e direitos de uso

- API FPMA (séries): https://fpma-documentation.web.app/docs/api-docs/time-series/
- API FPMA (valores): https://fpma-documentation.web.app/docs/api-docs/series-price/
- Termos de bases estatísticas FAO: https://www.fao.org/contact-us/terms/db-terms-of-use/en
- Fonte original identificada pelas 31 séries: https://www.gov.br/conab/pt-br

A FAO adota em regra licença CC BY 4.0 para suas bases estatísticas, salvo exceções de metadados e terceiros. Os termos também contêm restrições relativas à promoção de empresas/produtos e impõem respeito às condições de fornecedores originais. **Não considerar a exploração comercial nem a redistribuição irrestrita como automaticamente autorizadas** sem validar os termos aplicáveis a essas séries e aos dados da CONAB.

## Estrutura entregue

- `resultados/fao_precos_normalizados_v8.csv`: observações com tipo de preço, origem, índice e QA.
- `resultados/fao_series_classificadas_v8.csv`: 31 UUIDs, cobertura, fonte, tipo e defasagem.
- `resultados/fao_pares_atacado_varejo_v8.csv`: 1.399 pares, com sinalização de 1 outlier.
- `resultados/fao_resumo_diferenciais_v8.csv`: agregação experimental por produto/ano.
- `resultados/alertas_qualidade_v8.csv`: pendências de interpretação.
- `resultados/agro_integrado_v8.sqlite`: banco SQLite legado da V7 mais tabelas V8.
- `Painel_Precos_Agro_V8.xlsx`: painel-resumo e abas de auditoria.
- `Colab_Agro_V8.ipynb`: processa diretamente o ZIP V7, sem APIs externas nem dependências adicionais.
- `pipeline_agro_v8.py`: script reprodutível em Python puro.

## Próxima integração útil

Construir adaptadores para **preço recebido pelo produtor da CONAB**, microdados **Comex Stat (MDIC)** e **custos de produção da CONAB**, com cargas incrementais e controle de licença. O trabalho com o conjunto FAO disponível já está suficientemente auditado para análises exploratórias de atacado/varejo; novas rodadas de descoberta genérica de APIs terão retorno marginal menor.
