import streamlit as st
from PIL import Image
import tempfile
import os
from pathlib import Path
from datetime import datetime
import pandas as pd
from extrator import processar_pdfs, gerar_relatorio_pdf, exportar_para_excel_com_itens 
from codigos_fiscais_destinatario import gerar_resumo_analise, analisar_nf_como_destinatario
from ia_simples import (
    classify_expense_hf,
    analyze_supplier_risk,
    simple_forecast,
    add_ia_to_streamlit,
    inferir_ncm 
)
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from agente_financeiro import get_model_provider, analisar_contexto_ia

# =============== FUNÇÃO AUXILIAR ===============
def exportar_para_excel(df) -> bytes:
    """Exporta DataFrame para bytes de arquivo Excel"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Notas Fiscais', index=False)
        
        # Estilizar cabeçalho
        worksheet = writer.sheets['Notas Fiscais']
        header_fill = PatternFill(start_color="1F77B4", end_color="1F77B4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")
        
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Ajustar larguras
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
    
    output.seek(0)
    return output.getvalue()

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

# ==================== NOVO BLOCO: GESTÃO DE CHAVES DE API (streamlit_app.py) ====================

# É altamente recomendado que você coloque a configuração na barra lateral
with st.sidebar:
    st.divider()
    st.subheader("🤖 Provedor de Análise de IA")

    # 1. Inicializar variáveis de estado (SÓ EXECUTA NA PRIMEIRA VEZ)
    # Isso impede que o estado seja resetado a cada interação
    if 'ia_provider' not in st.session_state:
        st.session_state['ia_provider'] = 'hf'
    if 'ia_api_key' not in st.session_state:
        st.session_state['ia_api_key'] = None
        
    provider_options = ["Hugging Face (Padrão/Grátis)", "Google Gemini (Requer Chave)", "OpenAI ChatGPT (Requer Chave)"]
    
    # Define o índice de seleção baseado no estado atual
    if st.session_state.get('ia_provider') == 'gemini':
        default_index = 1
    elif st.session_state.get('ia_provider') == 'chatgpt':
        default_index = 2
    else:
        default_index = 0

    ia_provider_display = st.selectbox(
        "Escolha o motor de IA para Análises:",
        provider_options,
        index=default_index, # Mantém a seleção anterior
        key="ia_provider_select"
    )

    # 2. Lógica de atualização e campos de token
    
    # Limpa a chave se o usuário voltar para Hugging Face
    if ia_provider_display == "Hugging Face (Padrão/Grátis)":
        st.session_state['ia_api_key'] = None
        st.session_state['ia_provider'] = 'hf'

    elif "Google Gemini" in ia_provider_display:
        st.session_state['ia_provider'] = 'gemini'
        
        token = st.text_input(
            "Insira sua Chave de API do Gemini:", 
            type="password",
            # RECUPERA O VALOR JÁ SALVO PARA EVITAR O RESET
            value=st.session_state.get('ia_api_key', ''), 
            key="gemini_api_key_input"
        )
        
        if token:
            st.session_state['ia_api_key'] = token
        else:
            st.session_state['ia_api_key'] = None


    elif "OpenAI ChatGPT" in ia_provider_display:
        st.session_state['ia_provider'] = 'chatgpt'
        
        token = st.text_input(
            "Insira sua Chave de API do OpenAI (GPT):", 
            type="password",
            # RECUPERA O VALOR JÁ SALVO PARA EVITAR O RESET
            value=st.session_state.get('ia_api_key', ''), 
            key="openai_api_key_input"
        )
        
        if token:
            st.session_state['ia_api_key'] = token
        else:
            st.session_state['ia_api_key'] = None
        
    # Exibição do status atual
    status_key_ok = st.session_state.get('ia_api_key') is not None and st.session_state['ia_api_key'] != ''
    provider_name = st.session_state.get('ia_provider', 'hf')

    st.caption(f"Status da IA: **{provider_name.upper()}** {'(🔑 Chave OK)' if status_key_ok else '(🔑 Chave Pendente)' if provider_name != 'hf' else ''}")

# ==================== FIM DO NOVO BLOCO (streamlit_app.py) ====================

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

df_filtrado = pd.DataFrame()  # evita erro de variável não definida

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
            df = processar_pdfs(pdf_paths, _progress_callback=update_progress)
            
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
                    width="stretch",
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

                # ========== NOVO BLOCO: RESUMO DA ANÁLISE ==========
                with st.expander("📊 Resumo da Análise Fiscal"):
                    st.markdown("Gere a análise fiscal detalhada de uma NF específica ou veja um resumo consolidado.")

                    if not df_filtrado.empty:
                        nf_escolhida = st.selectbox(
                            "Selecione o número da NF para análise detalhada:",
                            df_filtrado["numero_nf"].astype(str).unique()
                        )

                        if st.button("Gerar Resumo da Análise"):
                            nf_dados = df_filtrado[df_filtrado["numero_nf"].astype(str) == nf_escolhida].iloc[0]

                            analise_nf = analisar_nf_como_destinatario(
                                cfop=nf_dados.get("cfop", ""),
                                ncm=nf_dados.get("ncm", ""),
                                csosn_ou_cst_recebido=nf_dados.get("csosn") or nf_dados.get("ocst") or "",
                                regime_destinatario=nf_dados.get("regime_tributario", "normal"),
                                regime_emitente=nf_dados.get("regime_emitente", "simples"),
                                uf_origem=nf_dados.get("uf_origem", "BA"),
                                valor_total=float(nf_dados.get("valor_total_num", 0.0))
                            )

                            resumo_txt = gerar_resumo_analise(analise_nf)
                            st.text(resumo_txt)

                            if st.button("📄 Exportar Resumo em PDF"):
                                gerar_relatorio_pdf(pd.DataFrame([analise_nf]))
                                st.success("📄 Resumo exportado como PDF com sucesso!")

                # ========== SEÇÃO IA ==========
                st.divider()
                add_ia_to_streamlit(df_filtrado)
                
                # Download Excel
                st.divider()
                st.subheader("📥 Exportar Resultados")
                
                excel_data = exportar_para_excel_com_itens(df_filtrado)
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

                st.divider()
                st.subheader("🧭 Agente Financeiro Inteligente")

                provider = get_model_provider()
                if st.button("Executar Análise de IA"):
                    analisar_contexto_ia(df_filtrado, provider)

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
        except Exception:
            pass
    try:
        os.rmdir(temp_dir)
    except Exception:
        pass

else:
    st.info("👆 Envie um ou mais arquivos PDF para começar a extração de dados.")
    
    with st.expander("ℹ️ Como usar"):
        st.markdown("""
        ### Passo a Passo:
        
        1. **Clique em 'Browse files'** para selecionar seus PDFs  
        2. **Você pode enviar múltiplos arquivos** de uma vez  
        3. **O sistema irá:**  
           - Extrair dados de cada NF  
           - Buscar nomes de empresas via CNPJ  
           - Organizar os dados em tabela  
        4. **Baixe os resultados** em Excel ou CSV  
        """)

st.divider()
st.markdown("""
<div style="text-align: center; color: gray; font-size: 12px; margin-top: 50px;">
📄 Extrator de Notas Fiscais v1.0 | Desenvolvido com ❤️ | 
<a href="https://github.com" target="_blank">GitHub</a>
</div>
""", unsafe_allow_html=True)
