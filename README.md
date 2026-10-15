# Agro Intelligence — migração para Codex (baseline V8)

Projeto de integração e inteligência agropecuária. Este repositório contém a base de código e documentação
para continuar, em Codex, o pipeline construído entre as versões V6–V8.

## Estado verificado (14/10/2026)

- 31 séries FAO/CONAB brasileiras: 3.926 cotações mensais de atacado e varejo, cinco produtos.
- 1.399 pares de preços atacado/varejo, dos quais 1.398 aprovados nos indicadores agregados.
- 15 séries defasadas >= 4 meses; 120 lacunas internas; 1 outlier suspeito preservado.
- SQLite V8 com 14 tabelas. 89 pares apresentam varejo abaixo do atacado e exigem auditoria contextual.
- Não contém preços na fazenda, série de soja ou dados de custos de produção.

## Estrutura

- `src/agro/pipeline_v8.py` — código V8 original, **sem mudanças de algoritmo**; precisa de refatoração.
- `legacy/` — V6 e V7 para consulta; não incorporar sem revisão de dependências e duplicações.
- `scripts/audit_v8.py` — auditoria de integridade em ZIP V8, somente biblioteca-padrão.
- `tests/` — testes de fumaça e invariantes; `AGENTS.md` define o contrato de desenvolvimento.
- `docs/` — metodologia, baseline, tarefas prioritárias e prompt inicial para Codex.
- `data/private/` — espaço local para ZIPs originais, **ignorado pelo Git**.

## Executar

Requisitos mínimos: Python 3.10+. Os comandos abaixo não precisam de bibliotecas externas.

```bash
python -m unittest discover -s tests -v
python scripts/audit_v8.py --input data/private/resultados_agro_v8.zip
python src/agro/pipeline_v8.py data/private/resultados_agro_v7.zip --output data/private/reprocessado_v8
```

O pipeline usa por padrão a data de referência de `docs/baseline_v8.json`. Para uma nova rodada,
informe `--reference-date YYYY-MM-DD`. A auditoria do ZIP original exige o arquivo privado;
os testes offline geram uma amostra sintética. Consulte [execução e armazenamento V8](docs/EXECUCAO_V8.md)
para empacotar e auditar a saída reprocessada.

O código da V6/V7 usa `pandas`, `numpy`, `requests`; revisar antes de reinstalar dependências.

## Webapp de exploração

No Bash:

```bash
python3 -m pip install -r requirements-web.txt
PYTHONPATH=src python3 -m uvicorn agro.webapp:app --host 127.0.0.1 --port 8000
```

No PowerShell do Windows:

```powershell
python3 -m pip install -r requirements-web.txt
$env:PYTHONPATH = "src"
python3 -m uvicorn agro.webapp:app --host 127.0.0.1 --port 8000
```

Abra `http://localhost:8000`. A primeira tela usa somente dados sintéticos, identificados
como tal. O app consulta o BCB SGS 1 e a PAM/IBGE 1612 quando os domínios oficiais estão
liberados. Para habilitar a V8 local, configure `AGRO_V8_SQLITE` com o caminho de um
SQLite V8 autorizado; não exponha dados FAO/CONAB antes da revisão de licença.
Veja [fontes e contrato do webapp](docs/WEBAPP.md) para estado dos conectores e limites.

## Migrar para GitHub / Codex

1. Crie um repositório privado `agro-intelligence` no GitHub, copie o conteúdo desta pasta e faça o primeiro commit.
2. Conecte-o ao Codex Cloud (ou abra a pasta no Codex local). Permita acesso externo apenas aos endpoints oficiais necessários.
3. Coloque seus ZIPs da V7/V8 em `data/private/` **somente na sua máquina**. Não publique dados antes de revisar licenças FAO/CONAB e de terceiros.
4. O Codex pode iniciar lendo `AGENTS.md`, `docs/ROADMAP.md` e `docs/PROMPT_INICIAL_CODEX.md`.
5. Execute a auditoria na máquina local; para o Codex Cloud, forneça um fixture/licença aprovada ou implemente coleta API a partir das fontes.

**Importante:** o Codex não acessa automaticamente arquivos deste chat ou da sua máquina no ambiente cloud.
O repositório, ambiente e dados precisam ser disponibilizados de acordo com suas permissões.
