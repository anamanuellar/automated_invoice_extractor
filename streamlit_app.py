import streamlit as st
import pandas as pd
from datetime import datetime
import tempfile
import os
from extrator import processar_pdfs, exportar_para_excel_com_itens
from extrator_ia_itens_impostos import ExtractorIA

# ✨ NOVA: Importar análise fiscal + financeira
try:
    from analise_fiscal_financeira import gerar_analise_financeira_completa
    ANALISE_DISPONIVEL = True
except ImportError:
    ANALISE_DISPONIVEL = False
    gerar_analise_financeira_completa = None

# ========================= CONFIGURAÇÃO BÁSICA =========================
st.set_page_config(
    page_title="📄 Extrator Inteligente de Notas Fiscais",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main { padding: 1.5rem; }
    h1, h2, h3 { color: #1f77b4; }
    .stMetric { text-align: center; }
    div[data-testid="stMetricValue"] {
        font-size: 1.6rem;
        color: #004b8d;
    }
</style>
""", unsafe_allow_html=True)

# ========================= CABEÇALHO =========================
st.title("📄 Extrator Inteligente de Notas Fiscais")
st.caption("Extraia informações de DANFEs em PDF, analise valores e exporte seus resultados.")
st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Status", "🟢 Pronto", help="Sistema operacional OK")
with col2:
    st.metric("Versão", "2.0", help="Versão atual da aplicação")
with col3:
    st.metric("IA Integrada", "✅ Ativa", help="Suporte a Gemini, OpenAI e HuggingFace")

st.divider()

# ========================= SIDEBAR =========================
with st.sidebar:
    st.header("⚙️ Configurações")
    
    enriquecer_cnpj = st.toggle(
        "Enriquecer dados via CNPJ",
        value=True,
        help="Busca razão social através de APIs públicas (BrasilAPI/ReceitaWS)"
    )
    
    enriquecer_fiscal = st.toggle(
        "Enriquecer com Análise Fiscal (IE, Simples Nacional)",
        value=True,
        help="Consulta ReceitaWS para IE status, regime tributário, optante Simples Nacional"
    )

    usar_ia = st.toggle(
        "Ativar Análise com IA",
        value=True,
        help="Permite a extração de itens e impostos com modelos generativos"
    )

    api_key_ia = st.text_input(
        "🔑 Chave de API (Gemini ou OpenAI)",
        type="password",
        help="Informe sua chave de API para ativar recursos de IA"
    )

    st.markdown("---")
    st.subheader("ℹ️ Sobre")
    st.markdown("""
    **Funcionalidades principais:**
    - Extração automática de campos via Regex e OCR
    - Enriquecimento de CNPJs via API
    - 🌟 **Análise Fiscal: IE, Simples Nacional, Regime**
    - IA opcional para extrair itens e impostos
    - Exportação para Excel e CSV
    """)

# ========================= UPLOAD DE ARQUIVOS =========================
st.subheader("📤 Envie seus arquivos PDF de DANFE")
uploaded_files = st.file_uploader(
    "Selecione um ou mais arquivos PDF",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    temp_dir = tempfile.mkdtemp()
    pdf_paths = []

    for f in uploaded_files:
        path = os.path.join(temp_dir, f.name)
        with open(path, "wb") as out:
            out.write(f.getbuffer())
        pdf_paths.append(path)

    # Exibição de progresso
    st.info("⏳ Processando arquivos...")

    progress = st.progress(0)
    messages = st.empty()

    def update_progress(msg):
        messages.info(msg)

    # Execução da extração
    df_result_ia = processar_pdfs(
        pdf_paths,
        _progress_callback=update_progress,
        api_key_gemini=api_key_ia if usar_ia else None
    )

    progress.progress(100)

    if not df_result_ia.empty:
        st.success(f"✅ {len(df_result_ia)} notas fiscais processadas com sucesso!")
        st.divider()

        # ========================= TABELA DE RESULTADOS =========================
        st.markdown("### 📋 Dados extraídos")
        colunas_visiveis = [
            "arquivo", "numero_nf", "serie", "data_emissao",
            "emitente_nome", "emitente_doc",
            "dest_nome", "dest_doc",
            "valor_total", "status"
        ]

        df_view = df_result_ia[[c for c in colunas_visiveis if c in df_result_ia.columns]]
        st.dataframe(df_view, use_container_width=True, height=450)

        # ========================= EXPORTAÇÕES =========================
        st.divider()
        st.subheader("📥 Exportar resultados")

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="💾 Exportar para Excel",
                data=exportar_para_excel_com_itens(df_result_ia),
                file_name=f"notas_fiscais_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with col2:
            st.download_button(
                label="📄 Exportar para CSV",
                data=df_result_ia.to_csv(index=False).encode("utf-8"),
                file_name=f"notas_fiscais_{datetime.now():%Y%m%d_%H%M%S}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        # ========================= ANÁLISES VISUAIS =========================
        st.divider()
        st.markdown("### 📊 Análises Gráficas")

        df_result_ia["valor_total_num"] = pd.to_numeric(df_result_ia.get("valor_total_num", 0), errors="coerce")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Top 5 Emitentes (por valor total)**")
            if "emitente_nome" in df_result_ia.columns:
                top_emit = (
                    df_result_ia.groupby("emitente_nome")["valor_total_num"]
                    .sum()
                    .nlargest(5)
                    .reset_index()
                )
                st.bar_chart(top_emit.set_index("emitente_nome"))

        with col2:
            st.markdown("**Tendência Mensal (por data de emissão)**")
            if "data_emissao" in df_result_ia.columns:
                df_result_ia["data_emissao"] = pd.to_datetime(df_result_ia["data_emissao"], errors="coerce")
                trend = (
                    df_result_ia.groupby(df_result_ia["data_emissao"].dt.to_period("M"))["valor_total_num"]
                    .sum()
                    .reset_index()
                )
                trend["data_emissao"] = trend["data_emissao"].astype(str)
                st.line_chart(trend.set_index("data_emissao"))

        # ========================= ANÁLISE FISCAL + FINANCEIRA =========================
        st.divider()
        st.subheader("📊 Análise Fiscal + Financeira Completa")
        
        st.markdown("""
        Análise integrada com:
        - 💰 Métricas financeiras (total, média, concentração)
        - 🏢 Análise por fornecedor
        - ⚠️ Alertas de compatibilidade fiscal
        - 📋 Regime tributário do destinatário
        """)
        
        # Input: Regime do destinatário
        regime_destinatario = st.selectbox(
            "Qual é o regime tributário da HOTEIS DESIGN S.A.?",
            ["Simples Nacional", "Lucro Real", "Lucro Presumido", "Isento de IE"],
            help="Selecione o regime tributário da sua empresa"
        )
        
        if st.button("Gerar Análise Completa 📈", use_container_width=True):
            if ANALISE_DISPONIVEL and gerar_analise_financeira_completa is not None:
                try:
                    analise_completa = gerar_analise_financeira_completa(df_result_ia, regime_destinatario)
                    st.text(analise_completa)
                    
                    # Botão para download
                    st.download_button(
                        label="📥 Baixar Análise em Texto",
                        data=analise_completa,
                        file_name=f"analise_fiscal_financeira_{datetime.now():%Y%m%d_%H%M%S}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar análise: {e}")
            else:
                st.warning("Módulo de análise fiscal não disponível. Instale: analise_fiscal_financeira.py")

        # ========================= ANÁLISE COMPLETA DE IA =========================
        st.divider()
        st.subheader("🤖 Análise Completa com IA")

        st.markdown("""
        Gere insights automáticos sobre as notas fiscais, com foco em:
        - Padrões de fornecedores
        - Tendências de valores
        - Possíveis anomalias fiscais
        """)

        if st.button("Executar análise completa com IA 🚀", use_container_width=True):
            st.info("🧠 Analisando dados via IA... (pode levar alguns segundos)")

            try:
                from extrator_ia_itens_impostos import ExtractorIA
                if api_key_ia:
                    model = ExtractorIA(api_key_ia)
                    analise_texto = f"""
                    Forneça uma análise executiva sobre os dados fiscais abaixo:
                    {df_result_ia.head(10).to_string(index=False)}
                    """
                    resultado = model.analisar_texto(analise_texto)
                    st.markdown("### 💡 Resultado da Análise:")
                    st.write(resultado)
                else:
                    st.warning("Insira sua chave de API na barra lateral para executar a análise.")
            except Exception as e:
                st.error(f"Erro ao executar análise de IA: {e}")

    else:
        st.warning("Nenhuma nota fiscal pôde ser processada.")
else:
    st.info("👆 Envie um ou mais PDFs de DANFE para iniciar a extração.")

# ========================= RODAPÉ =========================
st.markdown("""
---
<div style="text-align:center; color:gray; font-size:13px;">
💼 Extrator de Notas Fiscais Inteligente v2.0 — Desenvolvido com ❤️ por Manu Ribeiro
</div>
""", unsafe_allow_html=True)