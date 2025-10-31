import streamlit as st
from datetime import datetime
import pandas as pd
import tempfile
import os
from pathlib import Path
import io

from extrator import processar_pdfs, exportar_para_excel_com_itens

# =================== CONFIGURAÇÃO GERAL ===================
st.set_page_config(
    page_title="📄 Extrator Inteligente de Notas Fiscais",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =================== ESTILO CUSTOMIZADO ===================
st.markdown("""
<style>
/* Fundo geral */
body, .main {
    background-color: #f9fafc !important;
    color: #222;
    font-family: "Inter", sans-serif;
}

/* Títulos */
h1, h2, h3 {
    color: #1e3a8a;
    font-weight: 600;
}

/* Caixa central */
.block-container {
    padding-top: 2rem;
}

/* Botões */
.stButton>button {
    background-color: #2563eb;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 0.5rem 1.2rem;
    font-weight: 600;
    transition: 0.3s ease;
}
.stButton>button:hover {
    background-color: #1e40af;
}

/* Cards e métricas */
div[data-testid="metric-container"] {
    background-color: #ffffff;
    padding: 10px 20px;
    border-radius: 10px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.1);
}

/* Tabelas */
thead tr th {
    background-color: #1e3a8a !important;
    color: white !important;
    font-weight: bold !important;
}
</style>
""", unsafe_allow_html=True)

# =================== CABEÇALHO ===================
st.title("🧾 Extrator Inteligente de Notas Fiscais")
st.caption("Extração híbrida (Regex + IA) • Multi-modelo • OCR automático")

st.markdown("---")

# =================== SIDEBAR ===================
with st.sidebar:
    st.header("⚙️ Configurações")

    modelo_escolhido = st.selectbox(
        "Modelo de IA",
        ["huggingface", "openai", "gemini"],
        index=0,
        help="Selecione o modelo de IA para análise fiscal e enriquecimento de dados"
    )

    api_key_ia = None
    if modelo_escolhido in ["openai", "gemini"]:
        api_key_ia = st.text_input(
            f"🔑 Chave API do {modelo_escolhido.upper()}",
            type="password",
            placeholder="Insira sua chave da API aqui..."
        )

    enriquecer_cnpj = st.toggle(
        "Enriquecer dados via CNPJ",
        value=True,
        help="Consulta o nome das empresas emitente e destinatário"
    )

    st.divider()
    st.subheader("📘 Sobre")
    st.markdown("""
    Este aplicativo combina **extração tradicional via Regex** com **análise IA**, permitindo:
    - 📄 Extração automática de dados de DANFEs em PDF
    - 🔍 Identificação de CFOP, NCM, CST, ICMS, PIS e COFINS
    - 🧠 Enriquecimento inteligente com modelos HuggingFace, Gemini ou OpenAI
    - 📊 Exportação consolidada em Excel e CSV
    """)

# =================== ÁREA PRINCIPAL ===================
st.subheader("📤 Envie seus arquivos PDF de Notas Fiscais")

uploaded_files = st.file_uploader(
    "Selecione um ou mais arquivos PDF",
    type=["pdf"],
    accept_multiple_files=True,
    help="Você pode enviar múltiplos PDFs de uma vez"
)

if uploaded_files:
    temp_dir = tempfile.mkdtemp()
    pdf_paths = []

    for uploaded_file in uploaded_files:
        file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        pdf_paths.append(file_path)

    # =============== PROCESSAMENTO =================
    progress_container = st.container()
    with progress_container:
        progress_text = st.empty()
        progress_bar = st.progress(0)

    def update_progress(msg: str):
        progress_text.info(msg)

    st.info(f"🔍 Iniciando processamento com modelo **{modelo_escolhido.upper()}**...")
    with st.spinner("Processando PDFs, aguarde..."):
        try:
            df = processar_pdfs(
            pdf_paths,
            _progress_callback=update_progress,
            api_key=api_key_ia,
            provider=modelo_escolhido
        )

            progress_bar.progress(100)

            if not df.empty:
                st.success(f"✅ {len(df)} notas fiscais processadas com sucesso!")

                # =============== MÉTRICAS ===============
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total de Notas", len(df))
                with col2:
                    st.metric("Com Valor Total", df['valor_total_num'].notna().sum())
                with col3:
                    st.metric("Emitentes Identificados", df['emitente_doc'].notna().sum())
                with col4:
                    st.metric("IA Aplicada", df['extracao_ia'].sum() if 'extracao_ia' in df else 0)

                st.markdown("---")

                # =============== TABELA DE RESULTADOS ===============
                st.subheader("📊 Resultados Extraídos")
                st.dataframe(
                    df[
                        ["arquivo", "numero_nf", "serie", "data_emissao",
                         "emitente_nome", "dest_nome", "valor_total_num"]
                        + ([ "cfop", "ncm", "valor_icms", "parecer_ia" ] if "cfop" in df.columns else [])
                    ],
                    height=500,
                    use_container_width=True
                )

                # =============== DOWNLOADS ===============
                st.markdown("### 📥 Exportar Resultados")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                excel_data = exportar_para_excel_com_itens(df)
                csv_data = df.to_csv(index=False, encoding="utf-8-sig")

                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        label="📊 Baixar Excel",
                        data=excel_data,
                        file_name=f"notas_fiscais_{timestamp}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                with col2:
                    st.download_button(
                        label="📋 Baixar CSV",
                        data=csv_data,
                        file_name=f"notas_fiscais_{timestamp}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                # =============== ANÁLISE VISUAL ===============
                st.markdown("---")
                st.subheader("📈 Análise Visual")

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Top 5 Emitentes**")
                    top_emit = df['emitente_nome'].value_counts().head(5)
                    st.bar_chart(top_emit)

                with col2:
                    st.markdown("**Distribuição dos Valores (R$)**")
                    if (df['valor_total_num'] > 0).any():
                        import plotly.express as px
                        fig = px.histogram(df[df['valor_total_num'] > 0],
                                           x='valor_total_num', nbins=20)
                        st.plotly_chart(fig)
                    else:
                        st.info("Sem valores válidos para exibir.")

            else:
                st.warning("⚠️ Nenhuma nota fiscal foi identificada nos PDFs enviados.")

        except Exception as e:
            st.error(f"❌ Erro ao processar arquivos: {str(e)}")

    # Limpeza de temporários
    for f in pdf_paths:
        try: os.remove(f)
        except Exception: pass
    try:
        os.rmdir(temp_dir)
    except Exception:
        pass

else:
    st.info("👆 Envie um ou mais arquivos PDF para começar a extração de dados.")

# =================== RODAPÉ ===================
st.markdown("---")
st.markdown("""
<div style="text-align:center; color:#6b7280; font-size:13px;">
Desenvolvido com ❤️ por <b>Manu Ribeiro</b> • Extrator Inteligente v2.0<br>
<small>Compatível com HuggingFace, OpenAI e Gemini</small>
</div>
""", unsafe_allow_html=True)
