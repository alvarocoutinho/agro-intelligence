# Instruções de desenvolvimento — Agro Intelligence

Objetivo: criar um sistema de ingestão, qualidade, armazenamento, análise e visualização de dados agropecuários brasileiros e internacionais.

## Contrato de dados

- Nunca confundir preço no produtor, atacado e varejo; manter estágio explícito e metodologia da fonte.
- Preservar dado bruto, metadados, unidade, moeda, localidade, fonte, URL e data de atualização. Valores convertidos ficam em colunas separadas.
- Converter R$/kg e R$/saca apenas com a massa correta e sem confundir equivalente matemático com preço recebido por produtor.
- Marcar preços anomalamente baixos/altos sem descartá-los silenciosamente.
- Tratar valores ausentes como ausentes, não como zero. Expor defasagem por série.
- Diferencial de preços de varejo/atacado NÃO é margem de lucro.
- Verificar licenças antes de publicar/redistribuir dados e não incluir credenciais no repositório.
- Testes de APIs com backoff, timeout e limites; nunca desativar validação TLS para contornar erro.
- Não criar dados de soja, custos ou preço ao produtor usando séries que não representam esses conceitos.

## Engenharia

- Mudar V8 em pequenos passos reproduzíveis, preservar comparação com baseline V8.
- Antes de adicionar um conector, criar fixture e teste de resposta com variáveis e unidades reais.
- Corrigir datas fixas e contagens fixas da V8. Usar metadados e invariantes, não `assert len(...) == 3926`.
- Adicionar chaves primárias/índices, tipos SQL adequados, logs de coleta e registros de execução.
- Separar fonte/conector, normalização, validação, armazenamento, análise e API/dashboard.
- Preferir testes offline rápidos; integração online explicitamente habilitada e identificada nos relatórios.
- Manter `docs/ROADMAP.md` atualizado com decisões e pendências.

## Primeiro trabalho recomendado

Executar a auditoria da baseline V8, criar testes adicionais e remover dependências de datas/contagens fixas,
SEM mudar a interpretação econômica ou editar os dados originais.
