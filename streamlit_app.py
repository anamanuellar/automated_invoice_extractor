import streamlit as st
import pandas as pd
import tempfile
import os
from datetime import datetime
import plotly.express as px
from extrator import processar_pdfs, exportar_para_excel_com_itens, gerar_relatorio_pdf

# ================================
# CONFIGURAÇÕES INICIAIS
# ================================
st.set_page_config(
    page_title="Analisador Fiscal Inteligente",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
<style>
    .main {
        background-color: #f7f9fc;
        padding: 2rem;
    }
    h1, h2, h3 {
        color: #1a237e;
        font-family: 'Segoe UI', sans-serif;
    }
    .stButton>button {
        background-color: #3949ab;
        color: white;
        border-radius: 10px;
        font-weight: 600;
        padding: 0.6rem 1.2rem;
        transition: 0.2s;
    }
    .stButton>button:hover {
        background-color: #5c6bc0;
        transform: scale(1.03);
    }
</style>
""", unsafe_allow_html=True)

st.title("🧠 Analisador Fiscal Inteligente")
st.caption("Automação com IA para leitura e análise de Notas Fiscais Eletrônicas (DANFEs)")

st.divider()

# ================================
# SIDEBAR
# ================================
with st.sidebar:
    st.header("⚙️ Configurações")
    enriquecer_cnpj = st.toggle("🔍 Enriquecer dados via CNPJ (BrasilAPI)", value=True)
    api_key_ia = st.text_input("🔑 Chave da API de IA (opcional)", type="password")
    st.markdown("---")
    st.markdown("💡 **Dica:** Preencha a chave da IA para habilitar a análise completa de itens e impostos.")
    st.markdown("🌐 IA compatível: Gemini, OpenAI, Hugging Face")

# ================================
# UPLOAD DE ARQUIVOS
# ================================
st.subheader("📤 Envie seus arquivos PDF de Notas Fiscais")

uploaded_files = st.file_uploader(
    "Selecione um ou mais arquivos DANFE (PDF)",
    type="pdf",
    accept_multiple_files=True,
    help="Você pode enviar múltiplos arquivos PDF de uma vez."
)

# Inicialização
df_result = pd.DataFrame()

# ================================
# PROCESSAMENTO DE PDFs
# ================================
if uploaded_files:
    temp_dir = tempfile.mkdtemp()
    pdf_paths = []

    for uploaded_file in uploaded_files:
        file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        pdf_paths.append(file_path)

    st.divider()
    st.subheader("🔍 Etapa 1 — Extração de Dados")
    progress_bar = st.progress(0)
    status = st.empty()

    def update_progress(msg):
        status.info(msg)

    with st.spinner("Extraindo informações das notas..."):
        df_result = processar_pdfs(
            pdf_paths,
            _progress_callback=update_progress,
            api_key_gemini=api_key_ia if api_key_ia else None
        )
        progress_bar.progress(100)
        st.success(f"✅ {len(df_result)} notas processadas com sucesso!")

    # ================================
    # EXIBIÇÃO DE RESULTADOS
    # ================================
    if not df_result.empty:
        # Combinar nome + CNPJ para visualização
        df_result["Emitente"] = df_result.apply(
            lambda x: f"{x.get('emitente_nome','')} ({x.get('emitente_doc','')})" if x.get('emitente_doc') else x.get('emitente_nome',''),
            axis=1
        )
        df_result["Destinatário"] = df_result.apply(
            lambda x: f"{x.get('dest_nome','')} ({x.get('dest_doc','')})" if x.get('dest_doc') else x.get('dest_nome',''),
            axis=1
        )

        # Selecionar colunas principais
        cols = [
            "arquivo", "numero_nf", "serie", "data_emissao",
            "Emitente", "Destinatário", "valor_total_num"
        ]
        st.divider()
        st.subheader("📋 Notas Fiscais Extraídas")
        st.dataframe(df_result[cols], use_container_width=True)

        # ================================
        # ANÁLISE COM IA (BOTÃO)
        # ================================
        st.divider()
        st.subheader("🤖 Etapa 2 — Análise Completa com IA")
        if st.button("🚀 Executar Análise Avançada com IA"):
            with st.spinner("A IA está analisando itens e impostos..."):
                df_result_ia = processar_pdfs(
                    pdf_paths,
                    _progress_callback=update_progress,
                    api_key_gemini=api_key_ia if api_key_ia else None
                )
            st.success("✅ Análise da IA concluída!")
            st.dataframe(df_result_ia, use_container_width=True)

        # ================================
        # VISUALIZAÇÕES GRÁFICAS
        # ================================
        st.divider()
        st.subheader("📈 Etapa 3 — Visualizações Interativas")

        col1, col2 = st.columns(2)

        with col1:
            top_emitentes = (
                df_result.groupby("Emitente")["valor_total_num"]
                .sum()
                .reset_index()
                .sort_values("valor_total_num", ascending=False)
                .head(10)
            )
            fig1 = px.bar(
                top_emitentes,
                x="Emitente",
                y="valor_total_num",
                title="🏆 Top 10 Emitentes por Valor Total",
                color="valor_total_num",
                color_continuous_scale="Blues",
            )
            fig1.update_layout(
                xaxis_title="Emitente",
                yaxis_title="Valor Total (R$)",
                template="plotly_white",
                height=400
            )
            st.plotly_chart(fig1, use_container_width=True)

        with col2:
            df_sorted = df_result.dropna(subset=["data_emissao", "valor_total_num"]).copy()
            df_sorted["data_emissao"] = pd.to_datetime(df_sorted["data_emissao"], errors="coerce")
            fig2 = px.line(
                df_sorted.sort_values("data_emissao"),
                x="data_emissao",
                y="valor_total_num",
                title="📅 Tendência de Valores por Data de Emissão",
                markers=True,
                line_shape="spline",
                color_discrete_sequence=["#f28e2b"]
            )
            fig2.update_layout(
                xaxis_title="Data de Emissão",
                yaxis_title="Valor Total (R$)",
                template="plotly_white",
                height=400
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.divider()
        st.subheader("📊 Distribuição de Valores por Destinatário")
        fig3 = px.pie(
            df_result,
            names="Destinatário",
            values="valor_total_num",
            title="Participação por Destinatário",
            color_discrete_sequence=px.colors.sequential.Blues
        )
        fig3.update_traces(textinfo="percent+label")
        st.plotly_chart(fig3, use_container_width=True)

        # ================================
        # EXPORTAÇÃO
        # ================================
        st.divider()
        st.subheader("📥 Exportar Resultados")
        excel_data = exportar_para_excel_com_itens(df_result)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📊 Baixar Excel Consolidado",
                data=excel_data,
                file_name=f"analise_notas_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with col2:
            if st.button("📄 Gerar Relatório PDF"):
                gerar_relatorio_pdf(df_result)
else:
    st.info("👆 Envie um ou mais arquivos PDF para começar a análise.")

st.markdown("""
---
<div style="text-align:center; color:gray; font-size:12px;">
Feito com ❤️ por Manu Ribeiro | Automação Financeira Inteligente
</div>
""", unsafe_allow_html=True)
