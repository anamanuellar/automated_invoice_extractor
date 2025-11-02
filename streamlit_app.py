import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import tempfile
import os
import gc
from typing import Optional
from extrator import processar_pdfs, exportar_para_excel_com_itens
from extrator_ia_itens_impostos import ExtractorIA

# ✨ NOVA: Importar análise fiscal + financeira
try:
    from analise_fiscal_financeira import gerar_analise_completa as gerar_analise_financeira_completa
    ANALISE_DISPONIVEL = True
except ImportError:
    ANALISE_DISPONIVEL = False
    gerar_analise_financeira_completa = None

# ✨ NOVA: Importar biblioteca PDF (opcional)
PDF_DISPONIVEL = False
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    PDF_DISPONIVEL = True
except (ImportError, ModuleNotFoundError):
    PDF_DISPONIVEL = False
    # Fallback: ReportLab não disponível, PDF desabilitado
    pass

# ========================= LIMPEZA DE MEMÓRIA =========================
def limpar_cache():
    """Limpa cache e memória do Streamlit"""
    gc.collect()
    st.cache_data.clear()

# ========================= GERAÇÃO DE PDF =========================
def gerar_pdf_relatorio(df: pd.DataFrame, regime_destinatario: str, analise_texto: str) -> Optional[bytes]:
    """Gera relatório em PDF com análise fiscal"""
    if not PDF_DISPONIVEL:
        return None
    
    try:
        from io import BytesIO
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        styles = getSampleStyleSheet()
        
        # Estilos customizados
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1f77b4'),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        # Título
        story.append(Paragraph("📊 ANÁLISE FISCAL + FINANCEIRA", title_style))
        story.append(Paragraph("HOTEIS DESIGN S.A. - Notas de Entrada", styles['Heading3']))
        story.append(Spacer(1, 0.2*inch))
        
        # Informações gerais
        story.append(Paragraph(f"<b>Regime Tributário:</b> {regime_destinatario}", styles['Normal']))
        story.append(Paragraph(f"<b>Data do Relatório:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", styles['Normal']))
        story.append(Paragraph(f"<b>Total de NFs:</b> {len(df)}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Análise (primeiras 50 linhas)
        story.append(Paragraph("ANÁLISE DETALHADA", styles['Heading2']))
        
        for linha in analise_texto.split('\n')[:50]:
            if linha.strip():
                texto_seguro = linha[:100].replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(texto_seguro, styles['Normal']))
        
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        st.error(f"Erro ao gerar PDF: {e}")
        return None

# ========================= CONFIGURAÇÃO BÁSICA =========================
st.set_page_config(
    page_title="🔖 Extrator Inteligente de Notas Fiscais",
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
    .grafico-container {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid #1f77b4;
    }
</style>
""", unsafe_allow_html=True)

# ========================= CABEÇALHO =========================
st.title("🔖 Extrator Inteligente de Notas Fiscais")
st.caption("Extraia informações de DANFEs em PDF, analise valores e exporte seus resultados.")
st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Status", "🟢 Pronto", help="Sistema operacional OK")
with col2:
    st.metric("Versão", "2.3", help="Versão atual com gráficos melhorados")
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
        "🔐 Chave de API (Gemini ou OpenAI)",
        type="password",
        help="Informe sua chave de API para ativar recursos de IA"
    )
    
    # Botão de limpeza
    if st.button("🧹 Limpar Cache/Memória", use_container_width=True):
        limpar_cache()
        st.success("✅ Cache e memória limpos!")
        st.rerun()

    st.markdown("---")
    st.subheader("ℹ️ Sobre")
    st.markdown("""
    **Funcionalidades principais:**
    - Extração automática de campos via Regex e OCR
    - Enriquecimento de CNPJs via API
    - 🌟 **Análise Fiscal: IE, Simples Nacional, Regime**
    - IA opcional para extrair itens e impostos
    - 📊 Gráficos interativos com Plotly
    - 📄 Exportação para Excel, CSV e PDF
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

        col1, col2, col3 = st.columns(3)
        
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
        
        with col3:
            if PDF_DISPONIVEL:
                pdf_data = gerar_pdf_relatorio(df_result_ia, "Lucro Real", "Relatório em processamento")
                if pdf_data is not None:
                    st.download_button(
                        label="🔴 Exportar para PDF",
                        data=pdf_data,
                        file_name=f"relatorio_{datetime.now():%Y%m%d_%H%M%S}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                else:
                    st.button("🔴 Exportar para PDF", disabled=True, use_container_width=True, 
                             help="Erro ao gerar PDF")
            else:
                st.button("🔴 Exportar para PDF", disabled=True, use_container_width=True, 
                         help="Instale reportlab: pip install reportlab")

        # ========================= ANÁLISES VISUAIS MELHORADAS =========================
        st.divider()
        st.markdown("### 📊 Análises Gráficas")
        st.markdown("*Gráficos interativos com cores customizadas*")

        df_result_ia["valor_total_num"] = pd.to_numeric(df_result_ia.get("valor_total_num", 0), errors="coerce")

        # -------- GRÁFICO 1: TOP 5 EMITENTES --------
        st.markdown('<div class="grafico-container">', unsafe_allow_html=True)
        st.subheader("📈 Top 5 Emitentes (por valor total)")
        
        if "emitente_nome" in df_result_ia.columns:
            top_emit = (
                df_result_ia.groupby("emitente_nome")["valor_total_num"]
                .sum()
                .nlargest(5)
                .reset_index()
            )
            top_emit.columns = ["Emitente", "Valor"]
            
            # Cores: Azuis
            cores_azul = ["#1f77b4", "#2b8cc9", "#3b9ade", "#5badde", "#7bbbdd"]
            
            fig1 = px.bar(
                top_emit,
                x="Emitente",
                y="Valor",
                title="Top 5 Fornecedores por Valor de Compra",
                labels={"Valor": "Valor Total (R$)", "Emitente": "Fornecedor"},
                color_discrete_sequence=cores_azul,
                text="Valor"
            )
            fig1.update_traces(texttemplate='R$ %{text:,.0f}', textposition='outside')
            fig1.update_layout(
                height=400,
                showlegend=False,
                plot_bgcolor="#f8f9fa",
                paper_bgcolor="#ffffff",
                font=dict(size=11),
                margin=dict(l=50, r=50, t=80, b=80)
            )
            st.plotly_chart(fig1, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

        # -------- GRÁFICO 2: TENDÊNCIA MENSAL --------
        st.markdown('<div class="grafico-container">', unsafe_allow_html=True)
        st.subheader("📅 Tendência Mensal de Compras")
        
        if "data_emissao" in df_result_ia.columns:
            df_result_ia["data_emissao"] = pd.to_datetime(df_result_ia["data_emissao"], errors="coerce")
            trend = (
                df_result_ia.groupby(df_result_ia["data_emissao"].dt.to_period("M"))["valor_total_num"]
                .sum()
                .reset_index()
            )
            trend["data_emissao"] = trend["data_emissao"].astype(str)
            trend.columns = ["Período", "Valor"]
            
            # Cores: Verdes
            fig2 = px.line(
                trend,
                x="Período",
                y="Valor",
                title="Evolução de Compras por Mês",
                labels={"Valor": "Valor Total (R$)", "Período": "Mês"},
                markers=True,
                color_discrete_sequence=["#2ca02c"]
            )
            fig2.update_traces(marker=dict(size=8), line=dict(width=3))
            fig2.update_layout(
                height=400,
                showlegend=False,
                plot_bgcolor="#f8f9fa",
                paper_bgcolor="#ffffff",
                font=dict(size=11),
                margin=dict(l=50, r=50, t=80, b=80),
                hovermode="x unified"
            )
            st.plotly_chart(fig2, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

        # -------- GRÁFICO 3: DISTRIBUIÇÃO POR EMITENTE --------
        st.markdown('<div class="grafico-container">', unsafe_allow_html=True)
        st.subheader("🥧 Distribuição de Compras por Fornecedor")
        
        if "emitente_nome" in df_result_ia.columns:
            dist_emit = (
                df_result_ia.groupby("emitente_nome")["valor_total_num"]
                .sum()
                .reset_index()
            )
            dist_emit.columns = ["Fornecedor", "Valor"]
            
            # Cores: Arco-íris
            cores_arcoiris = px.colors.qualitative.Set3
            
            fig3 = px.pie(
                dist_emit,
                values="Valor",
                names="Fornecedor",
                title="Distribuição Percentual de Compras",
                color_discrete_sequence=cores_arcoiris
            )
            fig3.update_layout(
                height=450,
                font=dict(size=11),
                margin=dict(l=50, r=50, t=80, b=50)
            )
            st.plotly_chart(fig3, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

        # -------- GRÁFICO 4: QUANTIDADE DE NFS POR FORNECEDOR --------
        st.markdown('<div class="grafico-container">', unsafe_allow_html=True)
        st.subheader("📦 Quantidade de NFs por Fornecedor")
        
        if "emitente_nome" in df_result_ia.columns:
            qty_emit = (
                df_result_ia.groupby("emitente_nome").size()
                .reset_index(name="Quantidade")
                .sort_values("Quantidade", ascending=True)
            )
            qty_emit.columns = ["Emitente", "Quantidade"]
            
            # Cores: Laranjas
            cores_laranja = ["#ff7f0e", "#ff9e3c", "#ffb366", "#ffc28c", "#ffd1b3"]
            
            fig4 = px.bar(
                qty_emit,
                x="Quantidade",
                y="Emitente",
                orientation="h",
                title="Frequência de NFs por Fornecedor",
                labels={"Quantidade": "Quantidade de NFs", "Emitente": "Fornecedor"},
                color_discrete_sequence=cores_laranja,
                text="Quantidade"
            )
            fig4.update_traces(texttemplate='%{text}', textposition='outside')
            fig4.update_layout(
                height=400,
                showlegend=False,
                plot_bgcolor="#f8f9fa",
                paper_bgcolor="#ffffff",
                font=dict(size=11),
                margin=dict(l=150, r=50, t=80, b=50)
            )
            st.plotly_chart(fig4, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

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
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("Executar análise completa com IA 🚀", use_container_width=True):
                st.info("🧠 Analisando dados via IA... (pode levar alguns segundos)")

                try:
                    if api_key_ia:
                        model = ExtractorIA(api_key_ia)
                        analise_texto = f"""
                        Forneça uma análise executiva sobre os dados fiscais abaixo:
                        {df_result_ia.head(10).to_string(index=False)}
                        """
                        resultado = model.analisar_texto(analise_texto)
                        st.markdown("### 💡 Resultado da Análise IA:")
                        st.write(resultado)
                    else:
                        st.warning("Insira sua chave de API na barra lateral para executar a análise.")
                except Exception as e:
                    st.error(f"Erro ao executar análise de IA: {e}")
        
        with col_btn2:
            if st.button("Gerar Análise Fiscal 📈", use_container_width=True):
                if ANALISE_DISPONIVEL and gerar_analise_financeira_completa is not None:
                    try:
                        with st.spinner("⏳ Gerando análise fiscal..."):
                            analise_completa = gerar_analise_financeira_completa(df_result_ia, regime_destinatario)
                            
                            # Exibir análise
                            st.markdown("### 📊 Análise Fiscal + Financeira:")
                            st.text(analise_completa)
                            
                            # Botões de download
                            col_down1, col_down2 = st.columns(2)
                            
                            with col_down1:
                                st.download_button(
                                    label="📥 Baixar Análise em TXT",
                                    data=analise_completa,
                                    file_name=f"analise_fiscal_{datetime.now():%Y%m%d_%H%M%S}.txt",
                                    mime="text/plain",
                                    use_container_width=True,
                                )
                            
                            with col_down2:
                                if PDF_DISPONIVEL:
                                    pdf_data = gerar_pdf_relatorio(df_result_ia, regime_destinatario, analise_completa)
                                    if pdf_data:
                                        st.download_button(
                                            label="🔴 Baixar Análise em PDF",
                                            data=pdf_data,
                                            file_name=f"analise_fiscal_{datetime.now():%Y%m%d_%H%M%S}.pdf",
                                            mime="application/pdf",
                                            use_container_width=True,
                                        )
                    except Exception as e:
                        st.error(f"Erro ao gerar análise: {e}")
                else:
                    st.warning("Módulo de análise fiscal não disponível. Instale: analise_fiscal_financeira.py")

    else:
        st.warning("Nenhuma nota fiscal pôde ser processada.")
else:
    st.info("👆 Envie um ou mais PDFs de DANFE para iniciar a extração.")

# ========================= RODAPÉ =========================
st.markdown("""
---
<div style="text-align:center; color:gray; font-size:13px;">
💼 Extrator de Notas Fiscais Inteligente v2.3 – Desenvolvido por Ana Manuella Ribeiro e Letivan Filho
<br>
🚀 Com análise fiscal avançada, gráficos interativos e exportação em PDF
</div>
""", unsafe_allow_html=True)