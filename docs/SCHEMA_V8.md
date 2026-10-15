# Schema SQLite V8

O pipeline copia o SQLite V7 do ZIP de entrada, quando presente, e recria cinco
tabelas V8 no arquivo de saída. As tabelas V7 herdadas não são alteradas. Cada
tabela V8 usa `PRIMARY KEY ... WITHOUT ROWID`; uma chave duplicada causa erro em
vez de substituir silenciosamente uma observação.

| Tabela | Chave primária | Colunas `INTEGER` |
| --- | --- | --- |
| `fao_precos_normalizados_v8` | `uuid, data` | `meses_base_2020`, `meses_defasagem_serie`, `serie_defasada_4m`, `flag_outlier` |
| `fao_series_classificadas_v8` | `uuid` | `campos_auxiliares_divergentes`, `observacoes`, `meses_ausentes_internos`, `defasagem_meses`, `serie_defasada_4m`, `meses_base_2020` |
| `fao_pares_atacado_varejo_v8` | `produto, regiao, data` | Nenhuma |
| `fao_resumo_diferenciais_v8` | `produto, ano` | `ano`, `n_pares` |
| `alertas_qualidade_v8` | `tipo, uuid, data` | Nenhuma |

Demais colunas usam `TEXT`. Isso inclui datas ISO (`YYYY-MM-DD`) e quantias
decimais, para que um preço ou diferencial não perca dígitos por conversão
automática para ponto flutuante do SQLite. Os consumidores devem interpretar
esses campos como decimal, não `float`, quando precisarem de aritmética exata.
O índice `idx_precos_v8_tipo` cobre `tipo_preco, produto, regiao, data` para
consultas de preço. As chaves primárias já criam os índices de unicidade.

As tabelas de pares, estatísticas e alertas existem mesmo quando não há linhas.
Para aplicar esse schema a um resultado V8 anterior, reexecute o pipeline com o
ZIP V7 original em um diretório de saída; não edite o banco original manualmente.
