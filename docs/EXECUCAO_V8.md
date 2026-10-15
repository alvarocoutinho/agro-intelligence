# Execução e armazenamento V8

Use Python 3.10+ a partir da raiz do repositório. O pipeline V8 e a auditoria usam apenas
a biblioteca-padrão. A V6/V7 legada tem dependências próprias e não é necessária para
reprocessar um ZIP V7 existente.

## Verificação offline

```bash
python3 -m unittest discover -s tests -v
```

Os testes constroem um ZIP V7 sintético em diretório temporário e verificam a geração
de CSV, pares, SQLite e a auditoria estrutural. Eles cobrem 10/30/50/60 kg, lacunas,
duplicatas, preço ausente e negativo, outlier, diferencial negativo e meses posteriores
à baseline. Nenhum dado privado ou acesso à rede é necessário.

## Reprocessamento com dados autorizados

Coloque o ZIP V7 autorizado em `data/private/`, que é ignorado pelo Git. Os dados
originais não devem ser editados. Para reproduzir a referência da baseline, omita a
opção de data; o padrão vem de `docs/baseline_v8.json` (`2026-10-14`).

```bash
python3 src/agro/pipeline_v8.py data/private/resultados_agro_v7.zip --output data/private/reprocessado_v8
```

Para calcular defasagem em outra data:

```bash
python3 src/agro/pipeline_v8.py data/private/resultados_agro_v7.zip --output data/private/rodada_atual --reference-date 2026-11-01
```

O auditor recebe um ZIP V8. Para auditar a saída reprocessada, empacote os artefatos
com seus nomes na raiz do ZIP:

```bash
(cd data/private/reprocessado_v8 && python3 -m zipfile -c ../reprocessado_v8.zip *.csv *.json *.sqlite)
python3 scripts/audit_v8.py --input data/private/reprocessado_v8.zip
```

Compare `data/private/reprocessado_v8/resumo_v8.json` com
`docs/baseline_v8.json` quando usar o mesmo ZIP V7 e a data da baseline. A auditoria
verifica integridade estrutural e contagens internas; ela não valida metodologia,
representatividade, interpretação econômica nem licença. Sem os ZIPs originais, a
reprodução numérica da baseline permanece pendente.
`docs/auditoria_estrutural_v8.json` registra uma auditoria anterior; não substitui
uma nova execução com os arquivos originais.

## Arquivos e proveniência

| Camada | Local | Conteúdo |
| --- | --- | --- |
| Entrada bruta | `data/private/resultados_agro_v7.zip` | CSVs auditados, metadados, cobertura e, quando presente, SQLite V7. Preservar o ZIP original. |
| Observações normalizadas | `fao_precos_normalizados_v8.csv` | Preço original, massa, R$/kg recalculado, etapa comercial, origem, data e sinalizações de qualidade. |
| Séries e pares | `fao_series_classificadas_v8.csv`, `fao_pares_atacado_varejo_v8.csv` | Fonte, cobertura e defasagem por série; pares por produto, praça e mês. |
| Derivados e alertas | `fao_resumo_diferenciais_v8.csv`, `alertas_qualidade_v8.csv`, `resumo_v8.json` | Estatísticas da amostra comparável, pendências e totais da rodada. |
| Banco | `agro_integrado_v8.sqlite` | Cópia do SQLite V7, quando presente, acrescida das tabelas V8; sem dados V7, banco V8 novo. |

Os arquivos de saída ficam no diretório passado por `--output`. O SQLite V8 usa chaves
primárias para impedir duplicatas e `INTEGER` para contagens e flags. Valores monetários
decimais permanecem em `TEXT` para preservar a precisão original; consulte o
[schema V8](SCHEMA_V8.md). É possível reprocessar uma série sem pares ou alertas:
as tabelas e os CSVs correspondentes ficam vazios, com cabeçalhos. Preço equivalente
a 60 kg é apenas conversão matemática, não preço ao produtor; diferencial
varejo/atacado não é margem de lucro. Verifique as licenças antes de distribuir dados.
