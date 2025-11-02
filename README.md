# Extrator Inteligente de Notas Fiscais v2.4

> **Trabalho Final de Conclusão do Curso de Agentes Autônomos de IA**

Automatização inteligente da extração de dados de Notas Fiscais Eletrônicas (DANFEs) em PDF com análise fiscal e financeira avançada, transformando documentos não estruturados em inteligência de negócio acionável.

## 👥 Autores

- **Ana Manuella da Silva Ribeiro**
- **Letivan Gonçalves de Mendonça Filho**

---

## 📋 Sumário

- [Visão Geral](#visão-geral)
- [Características Principais](#características-principais)
- [Arquitetura do Sistema](#arquitetura-do-sistema)
- [Tecnologias Utilizadas](#tecnologias-utilizadas)
- [Instalação](#instalação)
- [Uso](#uso)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Módulos Principais](#módulos-principais)
- [Análise Fiscal Avançada](#análise-fiscal-avançada)
- [Contribuições e Melhorias Futuras](#contribuições-e-melhorias-futuras)
- [Licença](#licença)

---

## 🎯 Visão Geral

O **Extrator Inteligente de Notas Fiscais** é uma solução completa e modular que automatiza a extração de dados de Notas Fiscais Eletrônicas (DANFEs) em formato PDF. O sistema combina técnicas tradicionais de processamento de texto (Regex, OCR) com inteligência artificial (LLMs) para garantir alta precisão na extração de informações fiscais e financeiras.

Além da extração, o projeto oferece uma análise fiscal e financeira sofisticada, incluindo:

- **Análise de Impacto CFOP:** Simulação do impacto financeiro de Códigos Fiscais de Operação (CFOPs) incorretos
- **Enriquecimento Fiscal:** Consulta de regime tributário e status de Inscrição Estadual (IE) via APIs externas
- **Métricas Financeiras:** Cálculo de totais, médias, concentração de compras e análise por fornecedor
- **Relatórios Executivos:** Geração automática de relatórios em múltiplos formatos (Excel, CSV, PDF)

- **Acesse aqui:** [Agente-NFs](https://agente-nfs.streamlit.app/)

---

## ✨ Características Principais

### 1. **Extração Híbrida de Dados**
- Combinação de **Regex**, **OCR** (EasyOCR) e **IA** (Gemini/OpenAI) para máxima robustez
- Suporte a múltiplos formatos de DANFE (textuais e digitalizados)
- **Caching persistente** em disco para otimização de performance

### 2. **Enriquecimento Fiscal Automático**
- Integração com **ReceitaWS** e **BrasilAPI** para consulta de dados de CNPJ
- Extração automática de Regime Tributário (Simples Nacional, Lucro Real/Presumido, IE Isenta)
- Status de Inscrição Estadual (IE Ativa/Isenta)
- Cache local para reduzir requisições a APIs externas

### 3. **Análise Fiscal Avançada**
- **Simulação de Impacto CFOP:** Cálculo do impacto financeiro de CFOPs incorretos para empresas com IE Isenta
- **Alertas Fiscais:** Identificação de riscos (IE inativa, CFOP incorreto, PIS/COFINS em Simples Nacional)
- **Análise por Fornecedor:** Agrupamento e enriquecimento com regime tributário

### 4. **Interface Web Intuitiva**
- Desenvolvida com **Streamlit** para máxima usabilidade
- Visualizações interativas com **Plotly** (gráficos de barras, linhas, pizza)
- Upload de múltiplos PDFs com processamento paralelo
- Controles para seleção de regime tributário e status de IE

### 5. **Exportação Versátil**
- **Excel:** Dados estruturados com abas separadas para NFs e Itens
- **CSV:** Formato tabular para integração com outros sistemas
- **PDF:** Relatório multi-página com análise executiva formatada

---

## 🏗️ Arquitetura do Sistema

O projeto é estruturado em **4 camadas** para garantir escalabilidade, manutenibilidade e separação de responsabilidades:

```
┌─────────────────────────────────────────────────────────────┐
│  CAMADA 1: APRESENTAÇÃO (streamlit_app.py)                  │
│  Interface Web, Visualizações Plotly, Controles de Análise  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  CAMADA 2: LÓGICA DE NEGÓCIO (analise_fiscal_financeira.py) │
│  Análise Fiscal, Cálculos Financeiros, Lógica de IA         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  CAMADA 3: PROCESSAMENTO (extrator.py)                      │
│  Extração de Texto (Regex + OCR), Caching, Normalização    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  CAMADA 4: DADOS E INTEGRAÇÕES (enriquecedor_fiscal_api.py) │
│  APIs Externas (CNPJ, Regime Tributário), APIs de IA       │
└─────────────────────────────────────────────────────────────┘
```

### Fluxo de Dados

1. **Entrada:** PDFs (DANFEs) são enviados via interface web
2. **Extração Híbrida:** Combinação de Regex, OCR e IA extrai dados estruturados
3. **Enriquecimento Fiscal:** APIs externas fornecem regime tributário e status de IE
4. **Análise de Negócio:** Métricas financeiras e análise de impacto CFOP são calculadas
5. **Análise Executiva:** IA gera insights de alto nível e recomendações
6. **Saída:** Relatórios em múltiplos formatos (Web, Excel, CSV, PDF)

---

## 🛠️ Tecnologias Utilizadas

| Categoria | Tecnologia | Função |
| :--- | :--- | :--- |
| **Interface Web** | Streamlit | Criação da UI interativa |
| **Manipulação de Dados** | Pandas, NumPy | Estruturação e análise de dados |
| **Extração de PDF** | pdfplumber, PyMuPDF, PyPDF2 | Leitura de PDFs |
| **OCR** | EasyOCR, Pytesseract | Reconhecimento óptico de caracteres |
| **Visualização** | Plotly, Matplotlib, Seaborn | Gráficos interativos |
| **Geração de Relatórios** | ReportLab, openpyxl | PDF e Excel |
| **IA e LLMs** | Google Gemini, OpenAI, Hugging Face | Extração inteligente e análise executiva |
| **Integração Web** | Requests | Comunicação com APIs externas |
| **Utilitários** | Python 3.11+ | Linguagem base |

---

## 📦 Instalação

### Pré-requisitos

- Python 3.11 ou superior
- pip (gerenciador de pacotes Python)
- Chaves de API para Gemini ou OpenAI (opcional, para extração com IA)

### Passos de Instalação

1. **Clone o repositório:**
   ```bash
   git clone https://github.com/anamanuellar/automated_invoice_extractor.git
   cd extrator-inteligente-notas-fiscais
   ```

2. **Crie um ambiente virtual:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # No Windows: venv\Scripts\activate
   ```

3. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure as variáveis de ambiente (opcional):**
   ```bash
   # Crie um arquivo .env na raiz do projeto
   GEMINI_API_KEY=sua_chave_aqui
   OPENAI_API_KEY=sua_chave_aqui
   ```

5. **Execute a aplicação:**
   ```bash
   streamlit run streamlit_app.py
   ```

A aplicação será aberta em `http://localhost:8501`

---

## 🚀 Uso

### Interface Web

1. **Upload de PDFs:** Clique na área de upload ou arraste arquivos PDF (DANFEs)
2. **Configuração:** Selecione seu regime tributário e status de IE na barra lateral
3. **Processamento:** A aplicação extrai e analisa automaticamente os dados
4. **Visualização:** Explore os dados em tabelas e gráficos interativos
5. **Exportação:** Baixe os resultados em Excel, CSV ou PDF

### Exemplo de Uso Programático

```python
from extrator import processar_pdfs
from analise_fiscal_financeira import gerar_analise_completa

# Processar PDFs
df = processar_pdfs(["caminho/para/danfe1.pdf", "caminho/para/danfe2.pdf"])

# Gerar análise
regime_destinatario = "Lucro Real"
ie_status = "IE Ativa"
relatorio = gerar_analise_completa(df, regime_destinatario, ie_status)

print(relatorio)
```

---

## 📁 Estrutura do Projeto

```
extrator-inteligente-notas-fiscais/
├── streamlit_app.py                    # Interface web principal
├── extrator.py                         # Extração de dados de PDFs
├── extrator_ia_itens_impostos.py       # Integração com LLMs
├── analise_fiscal_financeira.py        # Análise fiscal e financeira
├── enriquecedor_fiscal_api.py          # Enriquecimento via APIs
├── requirements.txt                    # Dependências do projeto
├── ARQUITETURA_PROJETO.md              # Documentação técnica detalhada
├── README.md                           # Este arquivo
├── cache_nf/                           # Cache de PDFs processados
├── cache_fiscal_enriquecimento.json    # Cache de consultas de API
└── .env.example                        # Exemplo de variáveis de ambiente
```

---

## 🔧 Módulos Principais

### `extrator.py`
Responsável pela extração de dados de PDFs. Combina:
- **Extração de Texto:** PyPDF2, pdfplumber, PyMuPDF
- **OCR:** EasyOCR para PDFs digitalizados
- **Regex:** Padrões para campos estruturados (NF, CNPJ, Valor)
- **Caching:** Cache em disco para otimizar reprocessamento

**Funções principais:**
- `processar_pdfs(lista_caminhos)`: Processa múltiplos PDFs e retorna DataFrame
- `extrair_numero_nf(texto)`: Extrai número da NF
- `extrair_cnpj_emitente(texto)`: Extrai CNPJ do emitente
- `extrair_valor_total(texto)`: Extrai valor total da NF

### `enriquecedor_fiscal_api.py`
Integração com APIs externas para enriquecimento de dados fiscais:
- **ReceitaWS:** Consulta de dados de CNPJ (regime tributário, IE)
- **BrasilAPI:** Fallback para consultas de CNPJ
- **Cache Local:** Reduz requisições repetidas

**Funções principais:**
- `enriquecer_cnpj(cnpj)`: Retorna regime tributário e status de IE
- `validar_nfs_com_ia_enriquecida(df)`: Gera alertas fiscais

### `analise_fiscal_financeira.py`
Análise de negócio com foco em impacto fiscal:
- **Métricas Financeiras:** Total, média, concentração de compras
- **Análise por Fornecedor:** Agrupamento e enriquecimento
- **Simulação de CFOP:** Cálculo de impacto de CFOPs incorretos
- **Relatórios Executivos:** Geração de análise completa

**Funções principais:**
- `calcular_metricas_financeiras(df)`: Retorna métricas agregadas
- `calcular_impacto_cfop_incorreto(df)`: Simula impacto de CFOP incorreto
- `gerar_analise_completa(df, regime, ie_status)`: Gera relatório executivo

### `extrator_ia_itens_impostos.py`
Integração com modelos de IA para extração avançada:
- **Gemini:** Google Generative AI
- **OpenAI:** GPT-4o-mini
- **Hugging Face:** Modelos de sumarização

**Funções principais:**
- `ExtractorIA.extrair_nf_completa(texto)`: Extrai itens e impostos em JSON
- `ExtractorIA.analisar_texto(texto)`: Gera análise executiva

### `streamlit_app.py`
Interface web completa com:
- Upload de múltiplos PDFs
- Visualizações interativas (Plotly)
- Controles de análise (regime, IE status)
- Exportação em múltiplos formatos

---

## 🎯 Análise Fiscal Avançada

### Simulação de Impacto CFOP

O projeto oferece uma funcionalidade crítica: **simulação do impacto financeiro de CFOPs incorretos** para empresas com **IE Isenta**.

#### Cenário: IE Isenta com CFOP Incorreto

**Situação:** Uma empresa com IE Isenta usa CFOP 5.102 (tributado) em vez de 5.949 (isento)

**Impostos Indevidos Calculados:**
- **ICMS:** 18% do valor (não recuperável para IE isenta)
- **PIS:** 1,65% do valor
- **COFINS:** 7,65% do valor

**Consequências Fiscais:**
- Multa de 75% sobre ICMS indevido
- Juros de mora acumulados
- Risco de auditoria fiscal
- Bloqueio de créditos futuros

#### Exemplo de Saída

```
════════════════════════════════════════════════════════════════════════════════
              📊 ANÁLISE EXECUTIVA - FISCAL + FINANCEIRA                        

📌 DESTINATÁRIO: EMPRESA XYZ
Regime: IE Isenta - Operações devem ser isentas (CFOP 5.949)

════════════════════════════════════════════════════════════════════════════════

💰 ANÁLISE FINANCEIRA

Total Agregado:           R$ 1.500.000,00
Quantidade de NFs:        50
Valor Médio por NF:       R$ 30.000,00
Maior Compra:             R$ 150.000,00
Menor Compra:             R$ 5.000,00
Concentração Top 3:       45,0%

════════════════════════════════════════════════════════════════════════════════

⚠️  CENÁRIO: CFOP INCORRETO (5.102 Tributado vs 5.949 Isento)

IMPACTO FINANCEIRO ESTIMADO:

RESUMO DO RISCO:
  • Quantidade de NFs em risco: 30
  • Valor total em risco: R$ 1.000.000,00
  
  • ICMS indevido total: R$ 180.000,00
  • PIS indevido total: R$ 16.500,00
  • COFINS indevido total: R$ 76.500,00
  ════════════════════════════════
  • IMPOSTO TOTAL INDEVIDO: R$ 273.000,00
  
  VALOR FINAL (se CFOP incorreto): R$ 1.273.000,00

════════════════════════════════════════════════════════════════════════════════

🚨 CONSEQUÊNCIAS FINANCEIRAS E TRIBUTÁRIAS

SE CFOP ESTIVER INCORRETO (5.102 em vez de 5.949):

1. IMPACTO FINANCEIRO DIRETO:
   ❌ Custo adicional: R$ 273.000,00
   ❌ Seu custo final seria: R$ 1.273.000,00
   
2. IMPACTO TRIBUTÁRIO:
   ❌ ICMS: R$ 180.000,00 (não recuperável para IE isenta)
   ❌ PIS: R$ 16.500,00 (não recuperável)
   ❌ COFINS: R$ 76.500,00 (não recuperável)
   
3. IMPACTO FISCAL/LEGAL:
   ❌ Risco de auditoria fiscal (empresa isenta com ICMS)
   ❌ Possível multa de 75% sobre ICMS indevido
   ❌ Juros de mora
   ❌ Possibilidade de bloqueio de créditos futuros
```

---

## 🔄 Fluxo de Processamento Detalhado

```
1. ENTRADA
   ↓
   PDFs (DANFEs) → Upload via Streamlit
   ↓
2. EXTRAÇÃO HÍBRIDA
   ├── Tentativa 1: PyPDF2/pdfplumber (extração de texto)
   ├── Tentativa 2: EasyOCR (se PDF for digitalizado)
   ├── Tentativa 3: Regex (padrões estruturados)
   └── Tentativa 4: IA (Gemini/OpenAI) para detalhes finos
   ↓
3. ENRIQUECIMENTO FISCAL
   ├── Consulta ReceitaWS/BrasilAPI para CNPJ
   ├── Extração de Regime Tributário
   ├── Extração de Status de IE
   └── Cache local para otimização
   ↓
4. ANÁLISE DE NEGÓCIO
   ├── Cálculo de métricas financeiras
   ├── Análise por fornecedor
   ├── Simulação de impacto CFOP
   └── Geração de alertas fiscais
   ↓
5. ANÁLISE EXECUTIVA (IA)
   ├── Identificação de tendências
   ├── Detecção de anomalias
   └── Recomendações de ação
   ↓
6. SAÍDA
   ├── Interface Web (Streamlit + Plotly)
   ├── Exportação Excel (com abas)
   ├── Exportação CSV
   └── Exportação PDF (ReportLab)
```

---

## 📊 Visualizações Disponíveis

A interface web oferece 4 gráficos interativos:

1. **Top 5 Emitentes (Valor Total):** Identifica os principais fornecedores
2. **Tendência Mensal (Valor Total):** Análise temporal de compras
3. **Distribuição (Gráfico de Pizza):** Proporção de compras por fornecedor
4. **Quantidade de NFs por Emitente:** Volume de transações

---

## 🔐 Segurança e Privacidade

- **Chaves de API:** Armazenadas em variáveis de ambiente (não commitadas)
- **Cache Local:** Dados sensíveis armazenados localmente, não em nuvem
- **Validação de Entrada:** Validação de PDFs e CNPJs
- **Tratamento de Erros:** Erros capturados e registrados sem exposição de dados sensíveis

---

## 🚀 Melhorias Futuras

1. **Expansão de CFOP:** Incluir regras de validação para Lucro Real/Presumido
2. **Visualização de Alertas:** Integrar alertas fiscais na interface Streamlit
3. **Suporte a Outros Documentos:** CT-e, NFS-e, Cupom Fiscal
4. **Machine Learning:** Detecção automática de anomalias em padrões de compra
5. **Dashboard Avançado:** Análise temporal e previsões de impacto fiscal
6. **API REST:** Exposição de funcionalidades via API para integração com ERP
7. **Integração com Contadores:** Envio automático de alertas para contadores

---

## 📝 Documentação Adicional

Para mais detalhes técnicos, consulte:
- **[ARQUITETURA_PROJETO.md](./ARQUITETURA_PROJETO.md):** Documentação técnica completa
- **[Apresentação do Projeto](./presentation_project/):** Slides em HTML com design de dashboard

---

## 🤝 Contribuições

Contribuições são bem-vindas! Para contribuir:

1. Faça um *fork* do repositório
2. Crie uma *branch* para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a *branch* (`git push origin feature/AmazingFeature`)
5. Abra um *Pull Request*

---

## 📄 Licença

Este projeto é licenciado sob a **MIT License** - veja o arquivo [LICENSE](./LICENSE) para detalhes.

---

## 📞 Contato

Para dúvidas ou sugestões, entre em contato com os autores:

- **Ana Manuella da Silva Ribeiro**
- **Letivan Gonçalves de Mendonça Filho**

---

## 🎓 Contexto Acadêmico

Este projeto foi desenvolvido como **Trabalho Final de Conclusão do Curso de Agentes Autônomos de IA**, demonstrando a aplicação prática de conceitos avançados em:

- Processamento de Linguagem Natural (NLP)
- Integração com Large Language Models (LLMs)
- Arquitetura de software modular e escalável
- Análise de dados e business intelligence
- Desenvolvimento de aplicações web com Python

---

**Versão:** 2.4  
**Última Atualização:** Novembro de 2025  
**Status:** ✅ Pronto para Produção
