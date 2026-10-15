# Webapp de exploração

O app usa FastAPI para entregar a interface e uma API read-only. A interface filtra
produto, localidade, etapa e período; mostra série temporal, registros e exportação CSV.
Ela não combina unidades ou etapas comerciais em um único indicador. Quando a seleção
contém várias séries, o resumo não mostra um valor único arbitrário.

## Iniciar

```bash
python3 -m pip install -r requirements-web.txt
AGRO_V8_SQLITE=data/private/agro_integrado_v8.sqlite PYTHONPATH=src python3 -m uvicorn agro.webapp:app --host 127.0.0.1 --port 8000
curl -f http://127.0.0.1:8000/api/sources
```

O arquivo `data/private/agro_integrado_v8.sqlite` é extraído do ZIP V8 autorizado e
permanece fora do Git. Sem `AGRO_V8_SQLITE`, a interface inicia na amostra sintética;
com o banco disponível, abre na V8. Execute localmente até concluir a revisão das
licenças antes de expor o servidor publicamente.

`GET /api/sources` informa quais fontes estão habilitadas.
`GET /api/observations/{id}` devolve `source`, `observations` e `fetched_at`. Cada observação
traz `date`, `value` (nulo quando ausente), `unit`, `product`, `location`, `stage`,
`quality`, `primary_source`, `distributor` e `source_url`. `?refresh=true` ignora o
cache de 15 minutos das APIs externas. Falhas de origem retornam `502` e aparecem
como erro na interface.

## Fontes

| ID | Origem | Unidade e conceito | Estado |
| --- | --- | --- | --- |
| `demo` | `data/samples/demo_observations.json` | BRL/kg sintético, atacado e varejo | Disponível, sempre sinalizado como sintético. |
| `v8` | SQLite V8 indicado por `AGRO_V8_SQLITE` | BRL/kg observado, etapa explícita | Desabilitado até configurar um arquivo autorizado. Não publica dados automaticamente. |
| `bcb` | SGS 1, `api.bcb.gov.br` | BRL/USD, câmbio diário | Conector e fixture implementados; 20 pontos reais consultados nesta sessão, limite informado pela API. |
| `ibge` | PAM 1612, variável 214, `servicodados.ibge.gov.br` | Toneladas produzidas, lavoura temporária por produto/ano | Conector e fixture implementados; consulta ao vivo bloqueada por erro TLS do proxy cloud. |
| `mdic`, `conab_prices`, `conab_costs` | Fontes do roadmap | Comércio exterior, preço ao produtor e custos são conceitos separados | Aguardam endpoint oficial, contrato de dados, fixture e revisão de licença. |

Os conectores externos usam HTTPS com timeout, tentativas limitadas e espera em `429`
ou erros transitórios. A validação TLS permanece ativa. As fixtures em `tests/fixtures/`
testam variáveis e unidades; seus valores são sintéticos. O CSV exportado conserva
fonte primária, distribuidor, URL, qualidade e unidade.

## Verificação e limites

```bash
python3 -m unittest discover -s tests -v
node --check web/app.js
```

O backend e a interface foram testados com a amostra sintética, filtros e exportação.
A API BCB rejeitou `ultimos/120` com limite máximo de 20; o conector agora respeita
esse limite e a chamada real funcionou. A chamada IBGE ao vivo falhou na conexão TLS do proxy e não foi
validada. MDIC/CONAB ainda precisam de validação com acesso oficial antes de uso
analítico. O ZIP V8 enviado foi aprovado na auditoria
estrutural, mas reproduzir sua geração ainda exige o ZIP V7 de entrada.
