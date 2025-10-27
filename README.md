# Automated Invoice (Nota Fiscal) Extractor

This project extracts key information from Brazilian electronic invoices (NF-e) in **PDF format** using Python.  
It combines **text extraction (pdfplumber)** and **OCR (pytesseract + PyMuPDF)** to capture invoice data, then enriches missing company names by querying the **ReceitaWS API** based on the CNPJ (company tax ID).

## 🔍 Features
- 📑 Extracts **invoice number, series, issue date, issuer and recipient data, and total value**.
- 🏷️ Automatically formats **CNPJ/CPF**.
- 🔎 Falls back to **OCR** when the PDF is image-based.
- 🏛️ Enriches issuer and recipient names via **ReceitaWS API**, even when only the CNPJ root is available (handles branches).
- 📊 Exports consolidated results into **Excel (.xlsx)**.

## 🛠️ Tech Stack
- **Python 3.10+**
- [pdfplumber](https://github.com/jsvine/pdfplumber)
- [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/)
- [pytesseract](https://github.com/madmaze/pytesseract)
- [Pandas](https://pandas.pydata.org/)
- [ReceitaWS API](https://www.receitaws.com.br/)

## 🚀 How It Works
1. Place your `.pdf` invoices inside the `data/` folder.
2. Run the script:
   ```bash
   python src/main.py
3. The extracted and enriched dataset will be saved in:
   `output/notas_capas_YYYYMMDD_HHMMSS.xlsx

## 📌 Use Cases

- Automating financial back-office tasks (Accounts Payable/Receivable).
- Assisting controllership and auditing processes.
- Improving data ingestion pipelines in ERPs.

## 📜 License

MIT License


---
### 📄 README.md (Portuguese)

# Extrator Automático de Notas Fiscais (NF-e)

Este projeto automatiza a extração de informações de **Notas Fiscais eletrônicas em PDF** usando Python.  
Ele combina **extração de texto (pdfplumber)** e **OCR (pytesseract + PyMuPDF)** para capturar dados da NF, e enriquece informações faltantes consultando a **API da ReceitaWS** com base no CNPJ (inclusive raiz para filiais).

## 🔍 Funcionalidades
- 📑 Extrai **número da NF, série, data de emissão, emitente, destinatário e valor total**.
- 🏷️ Formata automaticamente **CNPJs/CPFs**.
- 🔎 Usa **OCR** quando o PDF é baseado em imagem.
- 🏛️ Enriquece nomes de emitentes e destinatários via **ReceitaWS API**, corrigindo divergências.
- 📊 Exporta resultados consolidados em **Excel (.xlsx)**.

## 🛠️ Stack Tecnológico
- **Python 3.10+**
- pdfplumber
- PyMuPDF
- pytesseract
- Pandas
- ReceitaWS API

## 🚀 Como Funciona
1. Coloque os arquivos `.pdf` dentro da pasta `data/`.
2. Rode o script:
   ```bash
   python src/main.py
3. O Excel consolidado será gerado em:
  `output/notas_capas_YYYYMMDD_HHMMSS.xlsx

## 📌 Casos de Uso

- Automação de tarefas de Contas a Pagar/Receber.
- Suporte para controladoria e auditoria.
- Ingestão de dados em sistemas ERP.

## 📜 Licença

MIT License.
