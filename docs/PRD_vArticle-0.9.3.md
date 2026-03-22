# PRD_vArticle.md

## WaterAInalytics — Versão congelável para artigo científico

Status deste documento: proposto a partir da análise do código real enviado no `.zip` desta conversa.
Versão de referência do projeto analisado: `v0.9.2`.
Escopo desta proposta: consolidar uma versão **publicável, auditável, reproduzível e interpretável** do sistema.

---

## 0. Base real analisada

### Estrutura efetivamente encontrada

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
- `tests/` (**somente `__pycache__` no pacote enviado; arquivos-fonte de teste não vieram**)
- `requirements.txt`
- `README.md`
- `CHANGELOG.md`

### Leitura arquitetural do sistema atual

O projeto já é mais que um MVP simples. Hoje ele possui quatro trilhas principais:

1. **Aquisição e cache USGS**
   - descoberta de estações via OGC API (`core/cache/get_stations.py`)
   - obtenção de séries IV e cache diário em Parquet (`core/cache/get_station_timeseries.py`)

2. **Processamento e estatística básica**
   - normalização/validação de séries (`core/processing/iv_processing.py`)
   - indicadores descritivos (`core/analysis/iv_indicators.py`)
   - pipeline CLI (`core/pipeline/iv_pipeline.py`, `run_pipeline.py`)

3. **Forecasting**
   - contrato comum de modelos (`core/forecast_models/base.py`)
   - modelos: Persistence, Ridge e Chronos (`core/forecast_models/`)
   - treinamento administrativo via UI (`core/ui/admin_models.py`)
   - inferência e visualização (`core/ui/forecasting.py`)

4. **Camada analítica narrativa / agentic**
   - contexto estruturado do forecast
   - coleta web
   - extração determinística de fatos
   - geração de artefatos e relatório
   - camada opcional LLM, inclusive modo determinístico OFF
   - avaliação de artefatos (`core/llm_analysis/`, `run_eval.py`, `run_eval_llm.py`)

### Pontos fortes já existentes

- Separação razoável por domínio (`cache`, `processing`, `forecast_models`, `llm_analysis`, `ui`).
- Contrato de forecasting explícito com `ForecastRequest` e `ForecastOutput`.
- Persistência de artefatos por estação/parâmetro/modelo.
- Existência de modo determinístico para o analista LLM (`provider="off"`).
- Existência de camada de avaliação para artefatos narrativos.
- Uso de três estações âncora no Playground, o que é muito útil para artigo.
- Estrutura Streamlit funcional e já integrada com exploração, séries temporais, forecasting e análise textual.

### Fragilidades objetivas já visíveis no código

1. **Documentação desatualizada**
   - `README.md` ainda descreve o esqueleto inicial.
   - `docs/design/architecture.md` está essencialmente vazia.
   - Há inconsistência de nomenclatura entre `WaterWatch` e `WaterAInalytics`.

2. **Reprodutibilidade ainda incompleta**
   - há uso de `hash(...)` do Python para seeds e bases sintéticas; isso não é estável entre processos/sessões.
   - `uuid4()` é usado para `run_id`, o que impede identidade determinística do run.
   - o pacote enviado não contém os testes-fonte.
   - dependências críticas opcionais de forecasting (ex.: `torch`, `chronos-forecasting`, possivelmente `transformers`) não estão pinadas em `requirements.txt`.

3. **Estado do pacote enviado não é “release-grade”**
   - o `.zip` incluiu `.git/`, `.env`, `__pycache__/` e caches locais.
   - isso é aceitável para desenvolvimento, mas inadequado para congelamento metodológico e replicação externa.

4. **Camada de “análise com tom humano” ainda está espalhada**
   - parte está no agentic/LLM pipeline.
   - parte está em relatórios determinísticos.
   - ainda não existe uma **camada única, explícita e central** de interpretação quantitativamente ancorada para séries + forecast.

5. **Coerência de versão/schema ainda não está totalmente consolidada**
   - `core/llm_analysis/config.py` ainda defaulta `schema_version="0.8.1"`
   - vários componentes já falam em `0.9.1`
   - isso precisa ser unificado antes de uma versão de artigo.

6. **Dependência excessiva do ambiente operacional**
   - parte importante do sistema depende de rede, cache prévio, artefatos já treinados e assets locais.
   - para artigo, é necessário estabelecer um modo “frozen/replayable”.

---

## 1. Objetivo da versão

### Objetivo central

Definir e implementar uma versão do WaterAInalytics que possa ser **congelada para publicação científica**, com comportamento previsível, saídas auditáveis e interpretação textual metodologicamente defensável.

### Definição operacional de “versão congelável para publicação”

Uma versão congelável é aquela em que:

- o fluxo principal pode ser executado novamente com resultado rastreável;
- o conjunto de entradas, parâmetros, versões e artefatos é explicitamente registrado;
- os outputs principais têm contrato estável;
- a análise textual é derivada de evidências quantitativas e não de formulação vaga;
- a documentação descreve fielmente o sistema executado;
- os exemplos do artigo podem ser regenerados ou reproduzidos por replay.

### Escopo funcional exato da versão artigo

Esta versão deve cobrir, no mínimo:

1. seleção e exploração de estações USGS;
2. carregamento/uso de séries temporais hidrológicas com cache local;
3. geração de forecast para horizonte curto;
4. exibição de forecast com proveniência do modelo;
5. geração automática de interpretação textual ancorada em métricas reais;
6. exportação/registro de artefatos suficientes para auditoria;
7. execução de casos demonstrativos com as 3 estações fixas do projeto.

### Fora de escopo da versão artigo

- expansão grande de funcionalidades de autenticação/RBAC;
- redesign radical da UI;
- agentização mais sofisticada do que o necessário para o artigo;
- suporte amplo a múltiplas fontes externas além do que já existe;
- otimizações prematuras de performance sem impacto metodológico.

---

## 2. Princípios da versão artigo

### 2.1 Reprodutibilidade determinística

O sistema deve minimizar variabilidade não controlada. Isso implica:

- eliminar seeds derivadas de `hash(...)` do Python;
- introduzir função de hash estável própria para seeds;
- separar claramente o que é determinístico do que depende de rede/modelo externo;
- registrar configuração, parâmetros, janela temporal e assinaturas de entrada;
- definir um modo de replay/freeze para os exemplos do artigo.

### 2.2 Transparência de modelos

Cada forecast deve informar explicitamente:

- modelo usado;
- artefato carregado;
- parâmetros relevantes;
- horizonte;
- intervalo de predição e método do PI;
- qualquer fallback aplicado.

### 2.3 Robustez de execução

A versão artigo deve falhar de modo explícito e interpretável, nunca silencioso. Isso inclui:

- validação de pré-condições;
- mensagens claras para artefatos faltantes;
- smoke tests reproduzíveis;
- consistência de schema/versionamento;
- documentação operacional mínima para outro pesquisador repetir os passos.

### 2.4 Interpretabilidade (ESSENCIAL)

A camada de interpretação não deve ser um adorno. Ela passa a ser um componente de primeira classe do sistema.

Ela deve:

- transformar métricas e comportamento temporal em texto claro;
- explicitar tendência, estabilidade, variabilidade e desvios;
- distinguir observado vs previsto;
- evitar inferências causais não suportadas;
- deixar claro o nível de confiança e as limitações.

---

## 3. Definição de “Análise com tom humano”

### Definição

“Análise com tom humano” significa uma saída textual legível, natural e útil, porém **estritamente ancorada em dados observados e valores calculados**, e não em improvisação linguística.

### O sistema deve gerar automaticamente

Junto com os resultados numéricos e gráficos, o sistema deve produzir:

1. **explicação textual dos dados observados**
   - faixa de valores recente
   - último valor
   - variação recente
   - presença de tendência local
   - estabilidade ou oscilação

2. **interpretação do comportamento da série**
   - série estável / crescente / decrescente / oscilatória
   - magnitude de variação recente
   - presença de outliers ou comportamento atípico local

3. **interpretação do forecast**
   - direção do forecast vs último observado
   - tamanho da mudança prevista
   - abertura do intervalo de predição
   - sinalização de forecast conservador vs incerto

4. **identificação de padrões**
   - tendência
   - variabilidade
   - anomalias simples
   - persistência ou reversão local

### O sistema não deve fazer

- inventar causas hidrológicas sem suporte;
- dizer que “há forte evidência” sem quantificação;
- usar frases genéricas como “os dados sugerem insights importantes”;
- apresentar interpretação desligada do gráfico e dos números.

### Requisitos obrigatórios da camada textual

Cada sentença interpretativa deve ser construída a partir de pelo menos um destes tipos de base quantitativa:

- comparação entre último valor observado e forecast H+1;
- inclinação local estimada;
- amplitude recente;
- desvio-padrão ou medida robusta de variabilidade;
- z-score robusto, MAD ou critério equivalente de anomalia;
- largura absoluta/relativa do intervalo de predição;
- comparação percentual entre forecast e baseline recente.

### Exemplo do tom esperado

Bom exemplo:

> “Nas últimas 24 horas, a série permaneceu relativamente estável, com variação baixa em torno do valor recente. O forecast de 24 horas mantém esse padrão, com mudança pequena em relação ao último ponto observado e intervalo de predição estreito.”

Mau exemplo:

> “A estação apresenta comportamento interessante e o forecast parece coerente com fatores ambientais recentes.”

### Implementação metodológica desejada

A “human-like insight layer” da versão artigo deve ser:

- **determinística por padrão**;
- desacoplada da UI;
- baseada em funções explícitas e testáveis;
- reutilizável em Streamlit, export e artigo.

---

## 4. Gap analysis (estado atual vs necessário para artigo)

## 4.1 O que já está pronto ou próximo do pronto

### Dados e cache

- Há descoberta de estações e cache local de IV.
- Há caminho claro para séries temporais por estação/parâmetro.
- Há schema de cache relativamente explícito.

### Forecasting

- Existe contrato comum de inferência.
- Persistence e Ridge estão metodologicamente legíveis.
- Chronos já está integrado com wrappers de compatibilidade.
- Há treinamento administrativo para Ridge e otimização de contexto para Chronos.

### UI

- Explorer, Plot Time Series, Forecasting e Agentic Analysis já existem.
- Há seleção de estações e uso das três estações âncora.

### Saídas analíticas

- Já existe pipeline de artefatos narrativos.
- Já existe validação do relatório LLM e métricas de avaliação.
- Já existe modo determinístico (`provider="off"`).

## 4.2 O que precisa ajustar

### A. Reprodutibilidade e congelamento

Necessário:

- substituir `hash(...)` por função estável;
- decidir política de `run_id` determinístico ou semi-determinístico;
- registrar assinatura estável do input dos exemplos do artigo;
- definir “frozen demo set” com saídas esperadas.

### B. Documentação fiel ao sistema real

Necessário:

- atualizar `README.md`;
- substituir `docs/design/architecture.md` por documentação real;
- explicitar fluxo completo de execução e dependências opcionais.

### C. Testabilidade

Necessário:

- recuperar os arquivos-fonte de teste;
- adicionar testes da camada interpretativa;
- adicionar smoke tests dos fluxos principais;
- adicionar ao menos um teste de golden output para as estações âncora.

### D. Padronização de schemas e contratos

Necessário:

- unificar a versão de schema dos artefatos narrativos;
- padronizar nomes e campos de saída;
- explicitar contrato do interpretation layer.

### E. Camada de interpretação textual

Necessário:

- criar módulo dedicado para interpretação quantitativa;
- desacoplar interpretação da dependência opcional de LLM;
- garantir que a interpretação principal do artigo funcione sem LLM externo.

### F. Higiene de release científica

Necessário:

- separar o que é pacote de release do que é ambiente local;
- remover dependência de `.git/`, `.env`, `__pycache__` e caches acidentais do bundle final;
- documentar dados mínimos requeridos.

## 4.3 O que precisa remover ou simplificar

### Simplificações recomendadas para a versão artigo

- evitar usar a camada LLM externa como componente central dos resultados do artigo;
- evitar múltiplas variantes de narrativa simultâneas sem contrato claro;
- reduzir dispersão de nomenclaturas legadas (`WaterWatch` vs `WaterAInalytics`);
- evitar comportamentos “best-effort” demais nos caminhos centrais do artigo.

## 4.4 O que precisa melhorar

### Melhorias prioritárias

1. consistência de identidade/versionamento;
2. modo freeze/replay;
3. camada interpretativa quantitativa única;
4. documentação e testes;
5. contrato explícito das saídas do artigo.

---

## 5. Arquitetura alvo (versão artigo)

## 5.1 Visão geral

Fluxo alvo:

`Station selection / cached data`
→ `series normalization + validation`
→ `forecast model inference`
→ `forecast summary metrics`
→ `deterministic interpretation layer`
→ `UI + export bundle + article figures/tables`

## 5.2 Arquitetura lógica proposta

### Camada 1 — Data access

Responsável por:

- carregar estações;
- carregar janela temporal da série;
- garantir cache local;
- retornar DataFrame canônico.

Base atual aproveitada:

- `core/cache/get_stations.py`
- `core/cache/get_station_timeseries.py`
- `core/processing/iv_processing.py`

### Camada 2 — Forecast core

Responsável por:

- construir `ForecastRequest`;
- carregar artefatos de modelo;
- executar inferência;
- produzir `ForecastOutput` com metadados claros.

Base atual aproveitada:

- `core/forecast_models/base.py`
- `core/forecast_models/persistence.py`
- `core/forecast_models/ridge.py`
- `core/forecast_models/chronos.py`
- `core/forecast_models/pi.py`

### Camada 3 — Interpretation layer (**nova camada explícita**)

Responsável por:

- calcular métricas interpretativas da série e do forecast;
- transformar métricas em texto natural determinístico;
- produzir objeto estruturado, reutilizável e testável.

Saída proposta:

- resumo executivo curto;
- achados da série observada;
- interpretação do forecast;
- limitações e avisos;
- evidências quantitativas usadas.

### Camada 4 — Presentation / export

Responsável por:

- exibir no Streamlit;
- exportar CSV/PNG/JSON/MD;
- manter bundle replicável para figuras do artigo.

### Camada 5 — Evaluation / freeze

Responsável por:

- golden cases das 3 estações âncora;
- validação dos outputs;
- verificação de determinismo;
- marcação de code freeze.

## 5.3 Onde entra a camada de interpretação

A camada de interpretação deve entrar **depois** do forecast numérico e **antes** da renderização UI/export.

Não deve depender da interface.

Não deve depender de busca web.

Não deve depender de provedor LLM externo.

LLM externo, se mantido, deve ser complementar e não o mecanismo principal do artigo.

---

## 6. Plano incremental de implementação (CRÍTICO)

> Regra geral: passos pequenos, auditáveis, com mínimo impacto estrutural.
> Cada step deve produzir valor verificável e preparar o seguinte.

---

### Step 1 — Stabilize project identity, docs and release baseline

#### Objetivo

Eliminar drift documental e alinhar o projeto ao estado real, sem alterar ainda a lógica científica principal.

#### Arquivos afetados (prováveis)

- `README.md`
- `docs/design/architecture.md`
- `CHANGELOG.md`
- referências textuais em:
  - `app.py`
  - `core/auth/login_ui.py`
  - `core/cache/get_station_timeseries.py`
  - `core/cache/get_stations.py`
  - `docs/contracts/schema_v1_usgs_nwis_iv.md`

#### Entregas

- nome do projeto unificado (`WaterAInalytics`);
- documentação real da arquitetura atual;
- instruções de execução atualizadas;
- nota explícita sobre dependências opcionais de Chronos/LLM.

#### Critério de aceitação

- não restarem referências inconsistentes relevantes entre WaterWatch e WaterAInalytics;
- README refletir o sistema atual;
- arquitetura documentada de forma coerente com os módulos reais.

#### Testes necessários

- smoke import dos módulos principais;
- revisão textual das rotas documentadas;
- `python -m compileall .`

---

### Step 2 — Determinism hardening and reproducibility utilities

#### Objetivo

Tornar a base de execução reprodutível o suficiente para o artigo.

#### Arquivos afetados (prováveis)

- `core/ui/forecasting.py`
- `core/forecast_models/persistence.py`
- possivelmente novo módulo, por exemplo:
  - `core/utils/stable_ids.py`
  - ou `core/utils/repro.py`
- `core/llm_analysis/orchestrators/fixed_pipeline.py`
- `core/llm_analysis/cache/keying.py` (se necessário)

#### Entregas

- função de seed/hash estável;
- remoção de `hash(...)` dos caminhos críticos;
- política explícita de `run_id`;
- registro de assinatura estável de inputs;
- distinção clara entre “cache key”, “run id” e “artifact signature”.

#### Critério de aceitação

- mesma entrada produzir mesma seed e mesmos outputs determinísticos locais;
- forecast deterministic/persistence não variar por reinício do processo;
- runs do modo artigo possuírem identidade rastreável.

#### Testes necessários

- teste unitário de seed estável;
- teste repetido de previsão com mesmas entradas;
- teste de assinatura estável de artefato.

---

### Step 3 — Standardize output contracts for article mode

#### Objetivo

Padronizar o que exatamente o sistema produz quando usado como evidência para o artigo.

#### Arquivos afetados (prováveis)

- `core/forecast_models/base.py`
- `core/ui/forecasting.py`
- `core/llm_analysis/config.py`
- `core/llm_analysis/models.py`
- `core/llm_analysis/orchestrators/fixed_pipeline.py`
- possível novo documento em `docs/contracts/`

#### Entregas

- definição de schema único para outputs principais;
- unificação de schema/version para narrativa/artifacts;
- bundle mínimo de export do artigo.

#### Critério de aceitação

- existir um contrato escrito e implementado para:
  - entrada da série
  - saída do forecast
  - saída da interpretação
  - bundle do run do artigo
- `schema_version` estar coerente nos caminhos centrais.

#### Testes necessários

- testes de serialização JSON;
- validação de campos obrigatórios;
- comparação com golden sample.

---

### Step 4 — Add deterministic interpretation layer

#### Objetivo

Criar a camada central de “análise com tom humano”, independente de LLM externo.

#### Arquivos afetados (prováveis)

- novo módulo, por exemplo:
  - `core/interpretation/metrics.py`
  - `core/interpretation/narrative.py`
  - `core/interpretation/contracts.py`
- integração em:
  - `core/ui/forecasting.py`
  - possivelmente `core/ui/plot_timeseries.py`
  - `core/llm_analysis/forecast_integration/adapter.py` ou novo adapter específico

#### Entregas

- métricas interpretativas explícitas;
- regras linguísticas determinísticas;
- objeto estruturado de interpretação;
- renderização em Markdown/texto claro na UI;
- evidências quantitativas anexadas à interpretação.

#### Critério de aceitação

- a UI deve mostrar insights legíveis e quantitativamente justificados;
- a interpretação deve funcionar sem provedor LLM;
- as frases devem mudar de modo coerente conforme a série muda.

#### Testes necessários

- casos sintéticos controlados:
  - série estável
  - tendência de alta
  - tendência de queda
  - alta variabilidade
  - anomalia local
- verificação textual baseada em regras esperadas;
- teste com pelo menos uma das estações âncora.

---

### Step 5 — Robustness, packaging and reproducible tests

#### Objetivo

Transformar a base em algo auditável por terceiros.

#### Arquivos afetados (prováveis)

- `requirements.txt`
- eventualmente novos arquivos:
  - `requirements-optional.txt`
  - `requirements-dev.txt`
- `tests/` (restauração dos testes-fonte + novos testes)
- documentação de execução

#### Entregas

- restauração/organização da suíte de testes-fonte;
- separação de dependências base, opcionais e dev;
- smoke test do pipeline principal;
- golden tests das estações âncora;
- checklist de ambiente mínimo.

#### Critério de aceitação

- o pacote consegue ser instalado e testado de maneira mais previsível;
- Chronos e LLM têm status explícito de opcionalidade;
- existe conjunto mínimo de testes executáveis pelo revisor/autores.

#### Testes necessários

- `compileall`
- testes unitários
- testes de integração leve
- teste de replay com bundle congelado

---

### Step 6 — UI refinements for article demonstration

#### Objetivo

Refinar a experiência apenas no que impacta clareza metodológica e apresentação do artigo.

#### Arquivos afetados (prováveis)

- `app.py`
- `core/ui/explorer_map.py`
- `core/ui/plot_timeseries.py`
- `core/ui/forecasting.py`
- possivelmente `core/ui/agentic_analysis.py`

#### Entregas

- distinção clara entre observado, forecast e interpretação;
- exibição de proveniência do modelo e avisos de fallback;
- visibilidade dos três casos âncora;
- modo de demonstração do artigo mais limpo.

#### Critério de aceitação

- um leitor consegue entender o fluxo sem conhecer o código;
- UI não depende de elementos placeholder para sustentar o argumento científico;
- mensagens de erro/fallback são claras.

#### Testes necessários

- smoke manual da UI;
- verificação de rendering dos blocos interpretativos;
- verificação dos casos âncora.

---

### Step 7 — Final freeze and article bundle

#### Objetivo

Congelar a versão final para gerar figuras, tabelas e descrições do artigo.

#### Arquivos afetados (prováveis)

- documentação final
- bundles/export dos casos
- `CHANGELOG.md`
- tag/version bump final

#### Entregas

- bundle congelado dos runs do artigo;
- outputs finais para as 3 estações;
- documentação de freeze;
- checklist do que entra no paper supplement.

#### Critério de aceitação

- os exemplos do artigo podem ser regenerados ou replayed;
- versão final está documentada e testada;
- não há alterações pendentes de arquitetura.

#### Testes necessários

- replay completo dos casos do artigo;
- comparação com outputs congelados;
- revisão final de documentação.

---

## 7. Estratégia de commits

### Regra

Cada step fechado = **1 commit principal**.

Se houver necessidade real, um step pode ter subcommits técnicos, mas o ideal para esta fase é:

- commit pequeno;
- escopo único;
- fácil de revisar;
- fácil de reverter.

### Formato padronizado

```text
type(scope): descrição
```

### Tipos sugeridos

- `docs`
- `refactor`
- `feat`
- `fix`
- `test`
- `chore`

### Exemplos para esta jornada

```text
docs(article): align README and architecture with v0.9.2 codebase
refactor(repro): replace unstable hash-based seeds with stable deterministic ids
feat(interpretation): add deterministic quantitative narrative layer for series and forecast
test(article): add golden tests for the three anchor stations
fix(schema): unify analysis artifact schema versions for article mode
chore(freeze): prepare frozen article bundle and final documentation
```

### Regra adicional

Antes de cada commit:

- código compila;
- testes do step passam;
- documentação do step foi atualizada quando aplicável.

---

## 8. Critério de “code freeze”

A versão estará pronta para freeze quando **todos** os critérios abaixo forem satisfeitos:

1. **Documentação coerente**
   - README e arquitetura representam o sistema real.

2. **Determinismo suficiente**
   - seeds estáveis;
   - outputs determinísticos locais reproduzíveis;
   - diferenças de execução explicadas quando houver dependência externa.

3. **Output contract estável**
   - forecast, interpretação e artefatos com schema definido.

4. **Interpretação textual metodologicamente defensável**
   - sem depender de LLM externo para o núcleo do artigo;
   - com evidências quantitativas explícitas.

5. **Testes mínimos executáveis**
   - unitários;
   - integração leve;
   - golden cases das três estações âncora.

6. **Casos do artigo congelados**
   - runs exportados;
   - parâmetros registrados;
   - outputs finais preservados.

7. **Sem pendências arquiteturais críticas**
   - nenhum TODO que comprometa a interpretação ou a reprodutibilidade do paper.

---

## 9. Estrutura do artigo (opcional, mas desejado)

## 9.1 Como o sistema entra no artigo

O sistema pode aparecer como:

- **plataforma experimental reproduzível** para análise e previsão hidrológica de curto prazo;
- **interface explicável** que integra dados observados, forecast e interpretação textual quantitativa;
- **ferramenta demonstrativa** para comparação entre modelos e comunicação de resultados.

## 9.2 Estrutura sugerida do texto

### 1. Introdução

- motivação para análise operacional de séries hidrológicas;
- necessidade de interpretabilidade e reprodutibilidade;
- posicionamento do WaterAInalytics.

### 2. System architecture

- aquisição de dados USGS;
- cache e processamento;
- forecasting;
- camada interpretativa;
- interface e export.

### 3. Forecasting methodology

- Persistence;
- Ridge;
- Chronos;
- intervalos de predição;
- política de fallback.

### 4. Interpretation methodology

- métricas usadas;
- regras textuais determinísticas;
- restrições contra alucinação.

### 5. Experimental setup

- três estações âncora;
- janelas temporais;
- horizontes;
- ambiente de execução;
- freeze bundle.

### 6. Results

- gráficos;
- tabelas;
- forecast vs observado;
- exemplos de interpretação textual.

### 7. Discussion

- forças da abordagem;
- limites da interpretação determinística;
- papel opcional de LLM externo.

### 8. Conclusion

- valor do sistema para análise hidrológica interpretável.

## 9.3 Como usar as 3 estações fixas

As três estações já presentes no código podem ser formalizadas como casos do artigo:

- `USGS-07010000`
- `USGS-05586100`
- `USGS-07374525`

### Uso sugerido

- uma estação com comportamento mais estável;
- uma com dinâmica distinta em vazão/nível;
- uma com parâmetro adicional relevante (ex.: turbidez no cache atual).

### Papel metodológico

- servem como **anchor cases** para demonstração;
- alimentam os golden tests;
- estabilizam a narrativa do paper.

---

## 10. Decisões recomendadas para a versão artigo

1. **A interpretação principal do artigo deve ser determinística.**
2. **LLM externo deve ser opcional e explicitamente secundário.**
3. **A versão artigo deve ter um modo freeze/replay.**
4. **As estações âncora devem virar casos oficiais de validação.**
5. **A documentação deve ser tratada como parte do deliverable científico, não como acessório.**

---

## 11. Materiais adicionais ainda desejáveis para a fase de implementação

O PRD já pode ser usado com o material enviado, mas para executar as próximas fases com validação completa, será muito útil receber depois:

1. `tests/` com os arquivos-fonte reais (`.py`), não apenas `__pycache__`;
2. `data/` mínimo relevante, especialmente:
   - CSV base de estações;
   - `data/models/` com artefatos treinados que você queira preservar para o artigo;
3. `assets/` apenas se a apresentação visual precisar ser validada também;
4. qualquer bundle de runs que você já considere “quase final” para o paper.

---

## 12. Ordem recomendada a partir daqui

1. aprovar este PRD;
2. executar o **Step 1** com mudanças mínimas e completas;
3. testar;
4. commitar;
5. seguir rigorosamente step a step até o freeze.

