# PRD_vArticle.md

## WaterAInalytics — versão congelável para artigo científico

Status deste documento: **revisado** após análise do código real enviado no `.zip` e após os requisitos adicionais definidos nesta conversa.  
Versão-base analisada: `v0.9.2`  
Objetivo: consolidar uma versão **publicável, auditável, reproduzível, robusta e interpretável**, sem placeholders em fluxos expostos ao usuário final.

---

## 0. Base real analisada

### 0.1 Estrutura efetivamente encontrada

- `app.py`
- `run_pipeline.py`
- `run_eval.py`
- `run_eval_llm.py`
- `core/`
  - `auth/`
  - `rbac/`
  - `ui/`
  - `cache/`
  - `processing/`
  - `analysis/`
  - `pipeline/`
  - `forecast_models/`
  - `llm_analysis/`
  - `utils/`
- `docs/`
  - `design/architecture.md`
  - `contracts/schema_v1_usgs_nwis_iv.md`
- `eval/`
- `iv_cache/`
- `tests/` (**apenas `__pycache__` no pacote recebido; os arquivos-fonte não vieram**)
- `requirements.txt`
- `README.md`
- `CHANGELOG.md`
- `.env`
- `.env.example`

### 0.2 Leitura arquitetural do sistema atual

O sistema já tem quatro trilhas reais e utilizáveis:

1. **Aquisição e cache de dados hidrológicos**
   - descoberta de estações em `core/cache/get_stations.py`
   - obtenção e cache de séries IV em `core/cache/get_station_timeseries.py`

2. **Processamento e indicadores**
   - normalização e agregação em `core/processing/iv_processing.py`
   - indicadores em `core/analysis/iv_indicators.py`
   - execução por pipeline/CLI em `core/pipeline/iv_pipeline.py`

3. **Forecasting**
   - contrato comum em `core/forecast_models/base.py`
   - modelos `persistence`, `ridge` e `chronos`
   - treinamento/administração via `core/ui/admin_models.py`
   - inferência e exibição via `core/ui/forecasting.py`

4. **Camada narrativa / agentic**
   - pipeline determinístico de coleta/contexto/artefatos
   - camada opcional LLM
   - UI em `core/ui/agentic_analysis.py`
   - avaliação em `run_eval.py` e `run_eval_llm.py`

### 0.3 Achados concretos relevantes para esta revisão

1. **Admin Users está placeholder no app**
   - Em `app.py`, a aba `Admin Users` hoje mostra apenas:
     - `st.info("Admin Users not implemented yet.")`
   - Isso **não pode permanecer** na versão do artigo.

2. **Existe senha hard-coded de reset do admin**
   - Em `core/auth/admin_reset.py`, o reset usa:
     - `"Admin-Reset-1234"`
   - Isso deve sair do código.

3. **O projeto usa variáveis de ambiente, mas não há política central de carga de `.env`**
   - Há vários `os.getenv(...)`.
   - Porém não há carregador explícito de `.env` no código analisado.
   - Logo, para depender de `.env` de forma controlada, é necessário adicionar uma política/configuração central.

4. **A documentação ainda não espelha fielmente a base real**
   - `README.md` e `docs/design/architecture.md` ainda não representam a versão 0.9.x com fidelidade suficiente para artigo.

5. **Os testes-fonte não vieram**
   - Isso passa a ser item obrigatório de recomposição nesta fase.

6. **A camada de contexto externo do modo Playground é hoje muito restrita**
   - A allowlist atual do Playground considera essencialmente:
     - `usgs.gov`
     - `noaa.gov`
     - `weather.gov`
   - Isso é bom para segurança, mas estreito demais para a contextualização ambiental mais rica que você deseja.

---

## 1. Objetivo da versão

### 1.1 Objetivo central

Definir e implementar uma versão do WaterAInalytics que possa ser **congelada para publicação científica**, com:

- comportamento previsível;
- saídas auditáveis;
- interface utilizável e sem placeholders críticos;
- interpretação textual quantitativamente ancorada;
- documentação suficiente para repetição por terceiros.

### 1.2 Definição operacional de “versão congelável para publicação”

Uma versão é considerada congelável quando:

- o fluxo principal pode ser repetido com entradas e parâmetros rastreáveis;
- o sistema registra versões, artefatos e assinaturas de entrada;
- os outputs principais têm contrato estável;
- os componentes visíveis ao usuário estão completos ou removidos do escopo;
- a interpretação textual é derivada de métricas reais;
- os casos do artigo podem ser regenerados ou reproduzidos por replay.

### 1.3 Escopo funcional exato da versão artigo

Esta versão deve cobrir, no mínimo:

1. autenticação funcional;
2. administração mínima de usuários sem placeholder;
3. exploração de estações e séries temporais USGS;
4. forecasting curto prazo com Ridge e Chronos, quando disponíveis;
5. saída interpretável e quantitativamente ancorada;
6. enriquecimento contextual confiável para as análises;
7. bundle auditável dos casos do artigo;
8. comportamento limitado e explicitamente truncado no Playground.

### 1.4 Fora de escopo

- sistema completo de IAM empresarial;
- expansão arbitrária da arquitetura;
- múltiplos provedores externos não auditáveis;
- redesign visual grande sem impacto metodológico;
- narrativa baseada prioritariamente em LLM externo.

---

## 2. Princípios da versão artigo

### 2.1 Reprodutibilidade determinística

- substituir fontes instáveis de identidade/seed;
- registrar assinaturas estáveis de entrada;
- separar claramente o que é determinístico do que depende de rede/modelo externo;
- permitir replay dos casos do artigo.

### 2.2 Transparência de modelos

Cada forecast deve informar:

- modelo usado;
- artefato/model file;
- horizonte;
- intervalos;
- fallback aplicado;
- limitações conhecidas.

### 2.3 Robustez de execução

- falhar de forma explícita;
- nunca esconder pré-condições ausentes;
- documentar dependências opcionais;
- garantir execução mínima auditável.

### 2.4 Interpretabilidade

A interpretação é componente de primeira classe do sistema e não enfeite de UI.

### 2.5 Segurança operacional sem engessar demais a análise

A versão artigo deve manter uma superfície confiável e controlada, mas sem restringir artificialmente a contextualização ambiental útil.  
O princípio será:

- **preferir fontes oficiais e datasets/serviços determinísticos**;
- **ampliar com critério a allowlist**, sem abrir a porta para scraping arbitrário e ruidoso.

### 2.6 Nada de placeholders visíveis em fluxos incluídos no escopo

Se uma função está visível ao usuário na versão do artigo, ela precisa estar:

- implementada de forma mínima porém correta; ou
- removida/ocultada até estar pronta.

---

## 3. Definição de “análise com tom humano”

### 3.1 Definição

“Tom humano” significa uma saída natural e legível, porém **estritamente apoiada em dados observados, forecast numérico, métricas explícitas e contexto confiável**.

### 3.2 O sistema deve gerar automaticamente

1. **explicação textual dos dados observados**
   - último valor;
   - faixa recente;
   - variação recente;
   - estabilidade vs oscilação.

2. **interpretação do comportamento da série**
   - tendência local;
   - variabilidade;
   - comportamento atípico local;
   - persistência ou reversão.

3. **interpretação do forecast**
   - direção do forecast;
   - magnitude da mudança;
   - largura do intervalo;
   - nível de conservadorismo/incerteza.

4. **contexto ambiental confiável**
   - aspectos geográficos, climáticos, locacionais e ambientais relevantes;
   - sem extrapolar causalidade;
   - com referência explícita à origem do contexto.

### 3.3 O sistema não deve fazer

- alucinar causalidade;
- usar frases genéricas sem base;
- citar contexto externo não auditável como fato central;
- misturar dados observados com especulação.

### 3.4 Base quantitativa mínima

Cada bloco interpretativo deve derivar de ao menos um destes elementos:

- comparação entre último valor observado e H+1;
- tendência local;
- amplitude recente;
- variabilidade robusta;
- critério simples de anomalia;
- largura absoluta/relativa do intervalo;
- mudança percentual contra baseline recente;
- contexto ambiental obtido de fonte confiável e identificado como contexto, não como prova causal.

---

## 4. Gap analysis (estado atual vs necessário para artigo)

## 4.1 O que já está pronto ou próximo do pronto

### Dados e cache
- descoberta e cache local de séries;
- três estações âncora já presentes no projeto;
- pipeline funcional.

### Forecasting
- contrato comum;
- modelos principais já integrados;
- UI de forecasting já existe.

### UI
- fluxo real de exploração, séries, forecast e análise;
- login funcional.

### Saídas narrativas
- já existe pipeline analítico/narrativo;
- já existe modo determinístico com LLM desligado.

## 4.2 O que precisa ajustar

### A. Auth/Admin Users
Necessário:
- retirar placeholder da aba `Admin Users`;
- implementar administração mínima de usuários;
- decidir escopo mínimo: listar, criar, ativar/desativar e resetar senha;
- manter RBAC simples e auditável.

### B. Segredos e reset do admin
Necessário:
- remover senha hard-coded do reset;
- centralizar leitura de configuração;
- permitir senha de reset via `.env` ou mecanismo equivalente controlado;
- garantir que segredo não seja commitado nem exibido indevidamente.

### C. Reprodutibilidade
Necessário:
- endurecimento de seeds/IDs;
- documentação de replay;
- bundles congeláveis dos casos do artigo.

### D. Documentação real
Necessário:
- atualizar `README.md`;
- atualizar `docs/design/architecture.md`;
- documentar configuração e execução;
- documentar dependências opcionais.

### E. Testes
Necessário:
- recompor `tests/` com arquivos-fonte;
- adicionar testes de interpretação;
- adicionar smoke/golden tests;
- adicionar teste específico para regras do Playground.

### F. Contexto ambiental confiável
Necessário:
- ampliar o enriquecimento contextual de forma segura;
- preferir integrações/datasets oficiais e determinísticos;
- não depender de scraping aberto para esse papel.

### G. Playground truncado
Necessário:
- truncar de forma explícita a saída exibida no Playground;
- adicionar aviso visível;
- tornar a fração configurável por `.env`;
- aplicar truncamento de modo consistente e testável.

## 4.3 O que precisa remover ou simplificar

- placeholder de `Admin Users`;
- uso de senha hard-coded;
- dependência excessiva de caminhos “best effort” em resultados centrais;
- drift de nomenclatura e documentação.

## 4.4 O que precisa melhorar

1. identidade do projeto e docs;
2. política de config/env;
3. auth/admin mínimo sem placeholder;
4. determinismo;
5. interpretação quantitativa;
6. enriquecimento contextual confiável;
7. suíte mínima de testes reproduzíveis;
8. modo Playground explicitamente limitado.

---

## 5. Arquitetura alvo (versão artigo)

## 5.1 Fluxo alvo

`auth/config`
→ `station selection + cached data`
→ `series normalization`
→ `forecast inference`
→ `summary metrics`
→ `deterministic interpretation layer`
→ `trusted context enrichment`
→ `presentation/export`
→ `freeze/replay`

## 5.2 Camadas

### Camada 1 — Configuração e segredos
Nova responsabilidade explícita:

- carregar configuração da aplicação;
- suportar `.env` de forma controlada;
- expor parâmetros seguros e tipados;
- concentrar defaults da versão do artigo.

Exemplos de parâmetros previstos:
- `ADMIN_RESET_PASSWORD`
- `PLAYGROUND_OUTPUT_FRACTION`
- `PLAYGROUND_TRUNCATION_NOTICE`
- eventuais toggles de contexto externo.

### Camada 2 — Auth/RBAC mínimo
Base existente:
- `core/auth/storage.py`
- `core/auth/session.py`
- `core/auth/login_ui.py`

Evolução necessária:
- UI real de `Admin Users`;
- operações mínimas de gestão;
- remover placeholder.

### Camada 3 — Dados e forecast
Aproveita a estrutura atual.

### Camada 4 — Interpretation layer
Nova camada explícita, determinística e testável.

### Camada 5 — Trusted context enrichment
Nova subcamada explícita para enriquecer a análise com contexto confiável por estação, por exemplo:

- localização e altitude;
- região hidrográfica / contexto hidrográfico quando disponível;
- clima e normals/climatologia oficial;
- land cover / vegetação / urbanização quando houver fonte oficial adequada;
- metadados geográficos/ambientais auditáveis.

**Diretriz importante:**  
Para a versão do artigo, essa camada deve preferir **fontes oficiais e/ou datasets estruturados** em vez de busca web aberta irrestrita.

### Camada 6 — Presentation / export
Inclui:
- UI Streamlit;
- aviso de truncamento no Playground;
- export dos bundles do artigo.

## 5.3 Onde entra a camada de interpretação

A interpretação entra **depois do forecast** e **antes da renderização final**.

## 5.4 Onde entra o contexto confiável

O contexto confiável deve alimentar a interpretação como um bloco separado de evidência contextual, com três regras:

1. não substituir a evidência da série/forecast;
2. não inventar causalidade;
3. ser rastreável à fonte.

---

## 6. Decisões específicas desta revisão

### 6.1 Login / adição / remoção de usuários
**Decisão:** entra no PRD da versão do artigo, em escopo mínimo.

Justificativa:
- o login já existe;
- a aba `Admin Users` já está exposta na UI;
- placeholder visível é incompatível com uma versão congelável de artigo.

Escopo mínimo recomendado:
- listar usuários;
- criar usuário;
- ativar/desativar;
- resetar senha;
- opcional: excluir usuário, desde que feito com muito cuidado.

### 6.2 Senha hard-coded de reset do admin
**Decisão:** remover do código e passar para configuração segura.

Observação técnica:
- usar `.env` é aceitável **desde que**:
  - continue fora do versionamento;
  - exista carregamento explícito e central;
  - o segredo não seja logado.
- como o código atual não implementa um carregador central de `.env`, isso precisa virar tarefa formal.

### 6.3 Testes e itens faltantes
**Decisão:** o PRD passa a tratar recomposição de testes e docs como obrigatória.  
Mesmo sem arquivos adicionais além de `/data` e `/assets`, a própria versão artigo deve providenciar:

- documentação correta;
- testes mínimos executáveis;
- bundle de demonstração.

### 6.4 Contexto geográfico/geológico/climático etc.
**Decisão:** incluir uma camada de enriquecimento confiável, mas com segurança preservada por desenho.

Diretriz metodológica:
- preferir fonte oficial/estruturada;
- expandir allowlist com critério;
- evitar scraping irrestrito como núcleo;
- tornar o enriquecimento audível e desligável.

### 6.5 Truncamento “brutal” do Playground
**Decisão:** entra no escopo obrigatório.

Requisito:
- saída textual do Playground exibida com truncamento forte em **60% por padrão**;
- valor ajustável por configuração;
- aviso explícito ao usuário informando que a limitação é imposta no Playground.

Parâmetro previsto:
- `PLAYGROUND_OUTPUT_FRACTION=0.60`

---

## 7. Plano incremental de implementação (CRÍTICO)

> Regra geral: passos pequenos, mínimo impacto, um step por vez, com teste e commit ao final.

### Step 1 — Config baseline, docs e remoção de segredos hard-coded

#### Objetivo
Criar a base de configuração central da versão artigo e eliminar o reset hard-coded do admin.

#### Arquivos afetados (prováveis)
- `README.md`
- `.env.example`
- `requirements.txt` (se entrar suporte explícito a `.env`)
- novo módulo de config, por exemplo:
  - `core/config/app_settings.py`
- `core/auth/admin_reset.py`
- `app.py` e/ou ponto de bootstrap relevante

#### Entregas
- política central de configuração;
- suporte controlado a `.env`;
- remoção da senha hard-coded;
- documentação inicial de configuração;
- atualização documental mínima alinhada ao sistema real.

#### Critério de aceitação
- não existir senha hard-coded no reset do admin;
- valores de config centralizados;
- `.env.example` documentar os novos knobs principais;
- docs refletirem o estado real.

#### Testes necessários
- smoke import da config;
- teste do fallback/default de configuração;
- teste do reset com senha vinda da config;
- `python -m compileall .`

#### Commit sugerido
- `refactor(config): centralize app settings and remove hard-coded admin reset password`

---

### Step 2 — Implementar Admin Users mínimo e remover placeholder

#### Objetivo
Entregar a aba `Admin Users` funcional, em escopo mínimo e auditável.

#### Arquivos afetados (prováveis)
- `app.py`
- novo UI module, por exemplo:
  - `core/ui/admin_users.py`
- `core/auth/storage.py`
- possivelmente `core/rbac/permissions.py`
- strings de UI

#### Entregas
- listagem de usuários;
- criação de usuário;
- ativação/desativação;
- reset de senha;
- remoção do placeholder.

#### Critério de aceitação
- nenhuma aba principal do escopo do artigo exibir placeholder;
- fluxo de gestão mínima de usuários funcionar como admin;
- mensagens de erro e sucesso serem claras.

#### Testes necessários
- teste unitário do storage para create/list/activate/reset;
- smoke manual da aba;
- verificação de RBAC mínimo.

#### Commit sugerido
- `feat(auth): implement minimal admin users panel without placeholders`

---

### Step 3 — Determinismo e identidade reproduzível dos runs

#### Objetivo
Endurecer seeds, IDs e assinaturas para dar base ao artigo.

#### Arquivos afetados (prováveis)
- novo util:
  - `core/utils/repro.py`
- `core/ui/forecasting.py`
- `core/llm_analysis/...` onde necessário
- contratos de artefato

#### Entregas
- hash/seed estável;
- distinção entre cache key, run id e artifact signature;
- registro explícito dos inputs do run.

#### Critério de aceitação
- mesma entrada gerar mesma identidade estável nos caminhos determinísticos;
- replay local previsível.

#### Testes necessários
- teste de seed estável;
- teste de repeatability com mesma entrada;
- teste de assinatura estável.

#### Commit sugerido
- `refactor(repro): harden deterministic ids and stable input signatures`

---

### Step 4 — Padronizar outputs e truncamento do Playground

#### Objetivo
Padronizar as saídas da versão artigo e aplicar limitação explícita ao Playground.

#### Arquivos afetados (prováveis)
- `core/ui/forecasting.py`
- `core/ui/agentic_analysis.py`
- possivelmente novo helper:
  - `core/ui/playground_limits.py`
- `docs/contracts/...`

#### Entregas
- contrato claro dos blocos de saída;
- truncamento de saída no Playground;
- aviso explícito de truncamento;
- parâmetro configurável por env, padrão `0.60`.

#### Critério de aceitação
- usuário Playground ver saída limitada e aviso correspondente;
- User/Admin ver saída completa;
- comportamento ser configurável sem mexer no código.

#### Testes necessários
- teste unitário do truncamento;
- teste do parsing da fração configurada;
- smoke manual em Playground e Admin/User.

#### Commit sugerido
- `feat(ui): enforce configurable playground output truncation`

---

### Step 5 — Enriquecimento contextual confiável por estação

#### Objetivo
Adicionar contexto geográfico/ambiental útil e confiável sem abrir demais a superfície do sistema.

#### Arquivos afetados (prováveis)
- novo pacote, por exemplo:
  - `core/context_enrichment/`
- integração em:
  - `core/ui/forecasting.py`
  - `core/ui/agentic_analysis.py`
  - ou adapter intermediário

#### Entregas
- camada explícita de contexto confiável;
- política de allowlist e/ou conectores determinísticos;
- metadados do contexto anexados à análise;
- distinção entre “dado observado” e “contexto ambiental”.

#### Critério de aceitação
- análise passar a incorporar contexto locacional/climático/ambiental útil;
- sem dependência central de scraping aberto irrestrito;
- fontes ficarem rastreáveis.

#### Testes necessários
- teste dos adaptadores de contexto;
- teste de falha graciosa quando fonte externa indisponível;
- smoke com pelo menos uma estação âncora.

#### Commit sugerido
- `feat(context): add trusted environmental enrichment for station analyses`

---

### Step 6 — Camada determinística de interpretação com tom humano

#### Objetivo
Transformar métricas e contexto em texto natural quantitativamente ancorado, sem depender de LLM externo.

#### Arquivos afetados (prováveis)
- novo pacote:
  - `core/interpretation/`
- integração nas UIs e nos exports

#### Entregas
- métricas interpretativas explícitas;
- regras linguísticas determinísticas;
- objeto estruturado de interpretação;
- renderização reutilizável.

#### Critério de aceitação
- a interpretação funcionar com LLM desligado;
- o texto variar coerentemente conforme a série muda;
- o bloco ficar metodologicamente citável no artigo.

#### Testes necessários
- séries sintéticas controladas;
- teste textual por cenários;
- teste com estação âncora.

#### Commit sugerido
- `feat(interpretation): add deterministic human-like insight layer`

---

### Step 7 — Testes, packaging auditável e freeze final

#### Objetivo
Fechar a versão artigo com documentação, testes e bundle de replay.

#### Arquivos afetados (prováveis)
- `tests/`
- `README.md`
- `docs/design/architecture.md`
- `CHANGELOG.md`
- bundles/export dos casos âncora

#### Entregas
- suíte mínima recomposta;
- instruções reprodutíveis;
- cases congelados;
- checklist de freeze.

#### Critério de aceitação
- casos do artigo conseguirem ser repetidos ou replayed;
- docs e testes estarem coerentes;
- nenhuma funcionalidade visível do escopo do artigo estar placeholder.

#### Testes necessários
- unitários;
- integração leve;
- replay dos casos âncora;
- revisão final de documentação.

#### Commit sugerido
- `test(release): add article freeze checks and reproducible demo bundle`

---

## 8. Estratégia de commits

### Regra
Cada step fechado = 1 commit principal.

### Formato
```text
type(scope): descrição
```

### Tipos sugeridos
- `feat`
- `fix`
- `refactor`
- `docs`
- `test`

### Regras adicionais
- commits pequenos e auditáveis;
- evitar misturar UI, lógica e docs sem necessidade;
- toda mudança de comportamento deve vir com teste ou roteiro de validação.

---

## 9. Critério de “code freeze”

A versão estará pronta para freeze quando:

1. não houver placeholders em fluxos visíveis do escopo do artigo;
2. não houver segredo hard-coded;
3. os runs centrais forem rastreáveis e suficientemente reproduzíveis;
4. a camada de interpretação funcionar sem LLM externo;
5. o Playground estiver truncado de modo explícito e configurável;
6. houver contexto confiável suficiente para enriquecer as análises;
7. docs e testes mínimos estiverem presentes;
8. os 3 casos âncora do artigo estiverem congelados.

---

## 10. Estrutura do artigo (opcional, mas desejado)

### 10.1 Como o sistema entra no artigo
O sistema deve ser apresentado como uma plataforma de:

- aquisição/cache de séries hidrológicas;
- forecasting reproduzível;
- interpretação quantitativa assistida por contexto confiável;
- demonstração interativa e operacional.

### 10.2 Como usar as 3 estações fixas
As três estações podem cumprir simultaneamente quatro papéis:

1. demonstração reprodutível;
2. comparação visual entre contextos hidrológicos distintos;
3. estudo de caso da camada de interpretação;
4. base para bundle congelado do artigo.

### 10.3 O que deve aparecer nos resultados
- gráfico da série observada + forecast;
- bloco de métricas-chave;
- bloco de interpretação determinística;
- bloco de contexto ambiental confiável;
- nota explícita sobre limitações.

---

## 11. Observação sobre `/data` e `/assets`

Para esta atualização do PRD, não foi necessário receber essas pastas.  
Para a execução dos próximos passos, pode ser útil depois receber:

- `data/models/` ou estrutura mínima equivalente, se quisermos validar os caminhos reais de artefatos;
- assets, se houver necessidade de verificar consistência visual final da UI.

---

## 12. Próxima etapa

Com este PRD revisado, a implementação deve começar pelo **Step 1**, com mudanças mínimas e completas:

1. configuração central;
2. remoção da senha hard-coded do admin reset;
3. documentação/config inicial alinhada;
4. teste e commit do step.
