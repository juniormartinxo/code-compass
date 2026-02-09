# Review Checklist — Arquitetura

Use esta lista para revisar mudanças estruturais antes de concluir a entrega.

## Contratos e compatibilidade
- [ ] Contratos públicos afetados estão identificados e documentados.
- [ ] Mudança é aditiva ou tem estratégia de migração explícita.
- [ ] Request/response/payload possuem exemplos atualizados.
- [ ] Versionamento e janela de compatibilidade estão definidos.

## Performance e custo
- [ ] Impacto esperado em latência/throughput/custo foi analisado.
- [ ] Existem limites operacionais definidos (topK, volume, timeout, batch).
- [ ] Trade-off entre qualidade e custo está explícito na decisão.

## Segurança
- [ ] Princípio de default deny está preservado.
- [ ] Allowlist/blocklist e validação de path continuam efetivas.
- [ ] Não há vazamento de segredo em logs, exemplos ou payloads.
- [ ] Mudanças de auth/autorização têm risco residual declarado.

## Dados e migração
- [ ] Schema de coleção/payload foi validado contra consumidores.
- [ ] IDs determinísticos e idempotência foram preservados.
- [ ] Rollout e rollback são executáveis e testáveis.
- [ ] Plano de backfill/cutover existe quando necessário.

## Operação e observabilidade
- [ ] Logs têm correlação suficiente para depuração.
- [ ] Métricas mínimas foram consideradas para o novo fluxo.
- [ ] Fluxo local é reproduzível com Docker Compose + Makefile.
- [ ] Passos de validação e evidências estão anexados.

## Governança
- [ ] Decision Record/ADR foi criado quando a mudança é estrutural.
- [ ] Owners e próximos passos estão definidos por domínio.
- [ ] Riscos abertos foram registrados com plano de mitigação.

