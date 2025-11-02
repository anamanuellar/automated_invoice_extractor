# 🏗️ ARQUITETURA DO PROJETO - ESTRUTURA TÉCNICA

---

## 📊 DIAGRAMA DE FLUXO

```
┌─────────────────────────────────────────────────────────────────┐
│                  EXTRATOR INTELIGENTE v2.4                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  1. INTERFACE (streamlit_app.py)                                │
│  └─ Camada de apresentação Streamlit                            │
│     ├─ Upload PDFs                                              │
│     ├─ Exibição de tabelas                                      │
│     ├─ Gráficos Plotly                                          │
│     ├─ Seleção de Regime + IE                                  │
│     ├─ Botão Análise Fiscal                                     │
│     ├─ Botão Análise IA                                         │
│     └─ Exportação PDF                                           │
└──────────────────┬──────────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────────┐
│  2. EXTRAÇÃO (extrator.py)                                      │
│  └─ Leitura e processamento de PDFs                             │
│     ├─ Extrai DANFE usando PyPDF2/pdfplumber                    │
│     ├─ OCR com EasyOCR/Tesseract                                │
│     ├─ Retorna DataFrame com dados                              │
│     └─ Formata colunas (NF, emitente, valor, etc)              │
└──────────────────┬──────────────────────────────────────────────┘
                   │
    ┌──────────────┴──────────────┬───────────────────┐
    │                             │                   │
┌───▼──────────────┐ ┌──────────▼──────┐  ┌────────▼────────────┐
│ 3a. ANÁLISE      │ │ 3b. ENRIQUECI-  │  │ 3c. ANÁLISE COM     │
│ FISCAL           │ │ MENTO FISCAL    │  │ IA                  │
├──────────────────┤ ├─────────────────┤  ├─────────────────────┤
│ analise_fiscal_  │ │ enriquecedor_   │  │ extrator_ia_        │
│ financeira.py    │ │ fiscal_api.py   │  │ itens_impostos.py   │
│                  │ │                 │  │                     │
│ • Metricas fin.  │ │ • Consulta API  │  │ • Gemini            │
│ • Regime CNPJ    │ │   ReceitaWS     │  │ • OpenAI            │
│ • CFOP correto   │ │ • Consulta API  │  │ • HuggingFace       │
│ • Impacto CFOP   │ │   BrasilAPI     │  │                     │
│ • Multas calc.   │ │ • Cache local   │  │ • Análise padrões   │
│ • Recomend.      │ │ • IE status     │  │ • Recomendações     │
└──────────────────┘ └─────────────────┘  └─────────────────────┘
    │                             │                   │
    └──────────────┬──────────────┴───────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────────┐
│  4. EXPORTAÇÃO (streamlit_app.py)                               │
│  └─ Gera arquivos de saída                                      │
│     ├─ Excel (openpyxl)                                         │
│     ├─ CSV (pandas)                                             │
│     └─ PDF (reportlab) - Multi-página                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 ARQUIVOS DO PROJETO

### **1. streamlit_app.py** (Interface)
```
Camada de Apresentação
├─ Sidebar configuração
├─ Upload de PDFs
├─ Display de tabelas
├─ 4 gráficos Plotly
├─ Seleção Regime + IE
├─ Botão Análise Fiscal
├─ Botão Análise IA (NOVO)
├─ Botão Exportar PDF
└─ Rodapé informativo
```

### **2. extrator.py** (Extração)
```
Processamento de PDFs
├─ processar_pdfs()
│  └─ Lê PDFs com PyPDF2/pdfplumber
│  └─ OCR com EasyOCR
│  └─ Retorna DataFrame
├─ exportar_para_excel_com_itens()
│  └─ Salva em Excel
└─ exportar_para_csv()
   └─ Salva em CSV
```

### **3. analise_fiscal_financeira.py** (Análise Fiscal)
```
Análise Profissional
├─ calcular_metricas_financeiras()
│  └─ Total, média, max, min
├─ analisar_por_fornecedor()
│  └─ Agrupamento e ranking
├─ calcular_impacto_cfop_incorreto()
│  └─ ICMS, PIS, COFINS indevidos
├─ gerar_relatorio_impacto_cfop()
│  └─ Formatação de impacto
└─ gerar_analise_completa(df, regime, ie_status)
   └─ Análise final estruturada
```

### **4. enriquecedor_fiscal_api.py** (Enriquecimento)
```
Consultas Externas
├─ consultar_cnpj_receitaws()
│  └─ API ReceitaWS
├─ consultar_cnpj_brasilapi()
│  └─ Fallback BrasilAPI
├─ consultar_cpf_brasilapi()
│  └─ Dados CPF
├─ enriquecer_cnpj()
│  └─ Retorna regime, IE, etc
├─ enriquecer_dataframe_fiscal()
│  └─ Enriquece DF em lote
└─ validar_nfs_com_ia_enriquecida()
   └─ Validações automáticas
```

### **5. extrator_ia_itens_impostos.py** (IA)
```
Integração com IA
├─ Classe: ExtractorIA
│  ├─ __init__(api_key, modelo)
│  ├─ extrair_nf_completa()
│  │  └─ Gemini / OpenAI / HuggingFace
│  └─ analisar_texto()
│     └─ Análise com IA
└─ Modelos suportados
   ├─ Gemini (gemini-2.5-flash)
   ├─ OpenAI (gpt-4o-mini)
   └─ HuggingFace (BART)
```

### **6. requirements.txt** (Dependências)
```
Core: pandas, numpy
PDF: PyPDF2, pdfplumber, reportlab, PyMuPDF
OCR: pytesseract, easyocr
Excel: openpyxl
Web: streamlit, plotly
API: google-generativeai, openai, requests
ML: transformers, torch, scikit-learn
```

---

## 🔄 FLUXO DE DADOS

### **Entrada** 
```
PDFs (DANFE)
   ↓
```

### **Processamento**
```
1. extrator.py processa PDFs
   ├─ PyPDF2 / pdfplumber lê arquivo
   ├─ EasyOCR extrai texto/dados
   └─ Retorna DataFrame com:
      ├─ numero_nf
      ├─ emitente_nome / emitente_doc
      ├─ dest_nome / dest_doc
      ├─ valor_total_num
      ├─ data_emissao
      ├─ cfop
      └─ ...

2. enriquecedor_fiscal_api.py enriquece
   ├─ ReceitaWS: regime do emitente
   ├─ IE status (ativa/isenta)
   ├─ Optante Simples Nacional
   └─ Cache local

3. analise_fiscal_financeira.py analisa
   ├─ Usuário seleciona: Regime + IE
   ├─ Calcula métricas
   ├─ Valida CFOPs
   ├─ Calcula impacto CFOP incorreto
   └─ Gera recomendações

4. extrator_ia_itens_impostos.py (IA)
   ├─ Prepara dados
   ├─ Chamada API (Gemini/OpenAI/HuggingFace)
   ├─ Análise com IA
   └─ Insights
```

### **Saída**
```
├─ Tabela DataFrame (display)
├─ Excel (.xlsx)
├─ CSV (.csv)
├─ Gráficos (Plotly interativos)
├─ Análise Fiscal (texto)
├─ Análise IA (markdown)
└─ PDF Multi-página (reportlab)
```

---

## 🔌 DEPENDÊNCIAS EXTERNAS

### **APIs Consultadas**
```
1. ReceitaWS (CNPJ)
   └─ Regime tributário
   └─ IE status
   └─ Optante Simples

2. BrasilAPI (CNPJ/CPF - Fallback)
   └─ Dados básicos

3. Google Gemini (IA)
   └─ Análise automática

4. OpenAI (IA - Alternativa)
   └─ Análise automática

5. HuggingFace (IA - Alternativa)
   └─ Análise automática
```

### **Bibliotecas Principais**
```
Streamlit     → Interface Web
Pandas        → Manipulação dados
PyPDF2        → Leitura PDF
pdfplumber    → Extração PDF
EasyOCR       → OCR
ReportLab     → Geração PDF
Plotly        → Gráficos
Requests      → HTTP
Google Genai  → API Gemini
OpenAI        → API OpenAI
Transformers  → HuggingFace
```

---

## 🎯 CAMADAS DO SISTEMA

```
┌─────────────────────────────────────────────────────┐
│  CAMADA 1: APRESENTAÇÃO (Streamlit)                 │
│  ├─ Interface do usuário                            │
│  ├─ Upload/Download                                 │
│  ├─ Visualizações                                   │
│  └─ Controles interativos                           │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│  CAMADA 2: LÓGICA DE NEGÓCIO                        │
│  ├─ Análise Fiscal (analise_fiscal_financeira.py)   │
│  ├─ Análise IA (extrator_ia_itens_impostos.py)      │
│  ├─ Enriquecimento (enriquecedor_fiscal_api.py)     │
│  └─ Cálculos e regras                               │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│  CAMADA 3: PROCESSAMENTO                            │
│  ├─ Extração de PDFs (extrator.py)                  │
│  ├─ OCR e leitura                                   │
│  ├─ Normalização de dados                           │
│  └─ DataFrame operations                            │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│  CAMADA 4: DADOS E INTEGRAÇÕES                      │
│  ├─ Cache local (JSON)                              │
│  ├─ APIs externas (ReceitaWS, BrasilAPI)           │
│  ├─ APIs IA (Gemini, OpenAI, HuggingFace)          │
│  └─ Armazenamento temporário                        │
└─────────────────────────────────────────────────────┘
```

---

## 📊 ESTRUTURA DE DADOS

### **DataFrame Principal** (após extração)
```python
{
    'numero_nf': str,           # NF número
    'emitente_nome': str,       # Empresa que emitiu
    'emitente_doc': str,        # CNPJ do emitente
    'dest_nome': str,           # Empresa que recebeu
    'dest_doc': str,            # CNPJ destinatário
    'valor_total_num': float,   # Valor em reais
    'valor_icms': float,        # ICMS
    'valor_pis': float,         # PIS
    'valor_cofins': float,      # COFINS
    'data_emissao': datetime,   # Data de emissão
    'cfop': str,                # Código operação
    
    # Enriquecimento (adicionado)
    'regime_emitente': str,     # Regime do emitente
    'ie_ativa': bool,           # IE ativa?
    'ie_isenta': bool,          # IE isenta?
    'optante_simples': bool,    # Simples Nacional?
}
```

---

## ✅ PONTOS DE INTEGRAÇÃO

### **Entre Módulos**
```
streamlit_app.py
├─ Chama: extrator.processar_pdfs()
├─ Chama: analise_fiscal_financeira.gerar_analise_completa()
├─ Chama: extrator_ia_itens_impostos.ExtractorIA.analisar_texto()
└─ Chama: enriquecedor_fiscal_api.enriquecer_cnpj()

extrator.py
├─ Retorna: DataFrame com dados extraídos
└─ Exporta: Excel, CSV

analise_fiscal_financeira.py
├─ Recebe: DataFrame + regime + ie_status
├─ Chama: enriquecedor_fiscal_api (internamente)
└─ Retorna: Análise em texto

extrator_ia_itens_impostos.py
├─ Recebe: Texto para análise
├─ Chama: APIs (Gemini/OpenAI/HuggingFace)
└─ Retorna: Análise formatada

enriquecedor_fiscal_api.py
├─ Consulta: ReceitaWS / BrasilAPI
├─ Cacheia: Resultados em JSON
└─ Retorna: Dados enriquecidos
```

---

## 🚀 FLUXO COMPLETO DO USUÁRIO

```
1. Abrir: streamlit_app.py
   └─ Interface Streamlit inicia

2. Upload PDFs
   └─ extrator.py processa
      └─ Retorna DataFrame

3. Ver Tabela
   └─ Display do DataFrame

4. Exportar Excel/CSV
   └─ extrator.py salva arquivos

5. Ver Gráficos
   └─ Plotly renderiza 4 gráficos

6. Selecionar Regime + IE
   └─ Usuário escolhe 2 parâmetros

7. Gerar Análise Fiscal
   └─ analise_fiscal_financeira.py
      ├─ enriquecedor_fiscal_api.py consulta APIs
      ├─ Calcula impactos
      └─ Retorna análise

8. Gerar Análise IA
   └─ extrator_ia_itens_impostos.py
      ├─ Prepara dados
      ├─ Chama IA (Gemini/OpenAI/HuggingFace)
      └─ Retorna insights

9. Exportar PDF
   └─ gerar_pdf_completo()
      ├─ reportlab cria PDF multi-página
      ├─ Insere análise
      └─ Retorna bytes para download

10. Download
    └─ Arquivo PDF pronto
```

---

## 🎯 RESUMO ARQUITETÔNICO

| Aspecto | Implementação |
|---------|---------------|
| **Frontend** | Streamlit |
| **Backend** | Python puro |
| **Extração** | PyPDF2 + pdfplumber + EasyOCR |
| **Análise** | Pandas + lógica customizada |
| **IA** | Gemini / OpenAI / HuggingFace |
| **Gráficos** | Plotly |
| **Exportação** | Excel (openpyxl) + CSV (pandas) + PDF (reportlab) |
| **APIs** | ReceitaWS + BrasilAPI |
| **Cache** | JSON local |
| **Deployment** | Streamlit Cloud ready |

---

**Arquitetura:** Modular, escalável, com camadas bem definidas  
**Status:** ✅ Pronto para produção
