import streamlit as st
import pytesseract
from PIL import Image
import tempfile
import os
from pathlib import Path
from datetime import datetime
from extrator import processar_pdfs, exportar_para_excel
from ia_simples import (
    classify_expense_hf,
    detect_anomalies,
    analyze_supplier_risk,
    simple_forecast,
    add_ia_to_streamlit
)

# Configurar Tesseract para português no Streamlit Cloud
os.environ['TESSDATA_PREFIX'] = '/usr/share/tesseract-ocr/5/tessdata'

# Usar inglês + português para melhor reconhecimento
pytesseract.pytesseract.tesseract_cmd = 'tesseract'


# =============== CONFIG STREAMLIT ===============
st.set_page_config(
    page_title="Extrator de Notas Fiscais",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============== ESTILOS ===============
st.markdown("""
    <style>
    .main { padding: 2rem; }
    .stMetric { text-align: center; }
    h1 { color: #1f77b4; }
    </style>
""", unsafe_allow_html=True)

# =============== HEADER ===============
st.title("📄 Extrator Automático de Notas Fiscais")
st.markdown("---")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Status", "🟢 Pronto", help="Sistema operacional")
with col2:
    st.metric("Versão", "1.0", help="Versão do aplicativo")
with col3:
    st.metric("NFs Processadas", "0", help="Contador geral")

st.markdown("---")

# =============== SIDEBAR ===============
with st.sidebar:
    st.header("⚙️ Configurações")
    
    enriquecer_cnpj = st.toggle(
        "Enriquecer dados com CNPJ",
        value=True,
        help="Consultar nome das empresas via APIs"
    )
    
    st.divider()
    
    st.subheader("📋 Sobre")
    st.markdown("""
    **Funcionalidades:**
    - ✅ Extração de dados de NFs em PDF
    - ✅ OCR automático para PDFs digitalizados
    - ✅ Enriquecimento de nomes via CNPJ
    - ✅ Exportação para Excel
    
    **Dados extraídos:**
    - Número da NF
    - Série
    - Data de emissão
    - Emitente (CNPJ/Nome)
    - Destinatário (CNPJ/Nome)
    - Valor total
    """)

# =============== MAIN ===============
st.subheader("📤 Envie seus PDFs de Notas Fiscais")

uploaded_files = st.file_uploader(
    "Selecione um ou mais arquivos PDF",
    type="pdf",
    accept_multiple_files=True,
    help="Você pode enviar múltiplos PDFs de uma vez"
)

if uploaded_files:
    # Criar pasta temporária
    temp_dir = tempfile.mkdtemp()
    
    # Salvar arquivos
    pdf_paths = []
    for uploaded_file in uploaded_files:
        file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        pdf_paths.append(file_path)
    
    # Progress bar e status
    progress_container = st.container()
    status_container = st.container()
    
    with progress_container:
        progress_bar = st.progress(0)
        status_text = st.empty()
    
    progress_messages = []
    
    def update_progress(message):
        progress_messages.append(message)
        with status_container:
            st.info(message)
    
    # Processar PDFs
    with st.spinner("🔄 Processando arquivos..."):
        try:
            df = processar_pdfs(pdf_paths, progress_callback=update_progress)
            
            progress_bar.progress(100)
            
            if not df.empty:
                st.success(f"✅ {len(df)} nota(s) fiscal(is) processada(s) com sucesso!")
                
                # Estatísticas
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total de NFs", len(df))
                with col2:
                    com_valor = df['valor_total_num'].notna().sum()
                    st.metric("Com Valor", com_valor)
                with col3:
                    com_emitente = df['emitente_doc'].notna().sum()
                    st.metric("Com Emitente", com_emitente)
                with col4:
                    com_dest = df['dest_doc'].notna().sum()
                    st.metric("Com Destinatário", com_dest)
                
                st.divider()
                
                # Tabela de dados
                st.subheader("📊 Dados Extraídos")
                
                # Filtros
                col1, col2 = st.columns(2)
                with col1:
                    filtro_nf = st.text_input("Filtrar por NF:", "")
                with col2:
                    filtro_emitente = st.text_input("Filtrar por Emitente:", "")
                
                df_filtrado = df.copy()
                
                if filtro_nf:
                    df_filtrado = df_filtrado[
                        df_filtrado['numero_nf'].astype(str).str.contains(filtro_nf, na=False)
                    ]
                
                if filtro_emitente:
                    df_filtrado = df_filtrado[
                        df_filtrado['emitente_nome'].astype(str).str.contains(filtro_emitente, na=False, case=False)
                    ]
                
                # Display da tabela com scroll
                st.dataframe(
                    df_filtrado,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "numero_nf": st.column_config.TextColumn("NF", width=80),
                        "serie": st.column_config.TextColumn("Série", width=60),
                        "data_emissao": st.column_config.TextColumn("Data", width=100),
                        "emitente_nome": st.column_config.TextColumn("Emitente", width=300),
                        "dest_nome": st.column_config.TextColumn("Destinatário", width=300),
                        "valor_total_num": st.column_config.NumberColumn(
                            "Valor",
                            format="R$ %.2f",
                            width=120
                        ),
                        "arquivo": st.column_config.TextColumn("Arquivo", width=150),
                    }
                )
                # ========== NOVA SEÇÃO: IA ==========

                st.divider()

                # 🤖 Adicionar seção de IA
                add_ia_to_streamlit(df_filtrado)
                
                st.divider()
                
                # Download Excel
                st.subheader("📥 Exportar Resultados")
                
                excel_data = exportar_para_excel(df_filtrado)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.download_button(
                        label="📊 Baixar como Excel",
                        data=excel_data,
                        file_name=f"notas_fiscais_{timestamp}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                
                with col2:
                    csv_data = df_filtrado.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📋 Baixar como CSV",
                        data=csv_data,
                        file_name=f"notas_fiscais_{timestamp}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                
                # Estatísticas avançadas
                st.divider()
                st.subheader("📈 Análise")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Top 5 Emitentes**")
                    top_emitentes = df['emitente_nome'].value_counts().head(5)
                    st.bar_chart(top_emitentes)
                
                with col2:
                    st.markdown("**Distribuição de Valores**")
                    if (df['valor_total_num'] > 0).any():
                        import plotly.express as px
                        fig = px.histogram(df[df['valor_total_num'] > 0], x='valor_total_num', nbins=20)
                        st.plotly_chart(fig)
                    else:
                        st.info("Sem valores para exibir")
                
            else:
                st.warning("❌ Nenhuma nota fiscal foi extraída dos arquivos.")
                st.info("Verifique se os PDFs contêm dados de notas fiscais válidas.")
        
        except Exception as e:
            st.error(f"❌ Erro ao processar arquivos: {str(e)}")
            st.info("Por favor, verifique os arquivos e tente novamente.")
    
    # Limpeza
    for pdf_path in pdf_paths:
        try:
            os.remove(pdf_path)
        except:
            pass
    try:
        os.rmdir(temp_dir)
    except:
        pass

else:
    st.info("👆 Envie um ou mais arquivos PDF para começar a extração de dados.")
    
    with st.expander("ℹ️ Como usar"):
        st.markdown("""
        ### Passo a Passo:
        
        1. **Clique em "Browse files"** para selecionar seus PDFs
        2. **Você pode enviar múltiplos arquivos** de uma vez
        3. **O sistema irá:**
           - Extrair dados de cada NF
           - Buscar nomes de empresas via CNPJ
           - Organizar os dados em tabela
        4. **Baixe os resultados** em Excel ou CSV
        
        ### Dados Extraídos:
        - ✓ Número da Nota Fiscal
        - ✓ Série
        - ✓ Data de Emissão
        - ✓ CNPJ/CPF do Emitente
        - ✓ Nome do Emitente
        - ✓ CNPJ/CPF do Destinatário
        - ✓ Nome do Destinatário
        - ✓ Valor Total
        
        ### Observações:
        - Funciona com PDFs escaneados (usa OCR)
        - Enriquece automaticamente nomes com APIs de CNPJ
        - Suporta Notas Fiscais Eletrônicas (NF-e)
        """)

st.divider()
st.markdown("""
<div style="text-align: center; color: gray; font-size: 12px; margin-top: 50px;">
📄 Extrator de Notas Fiscais v1.0 | Desenvolvido com ❤️ | 
<a href="https://github.com" target="_blank">GitHub</a>
</div>
""", unsafe_allow_html=True)
