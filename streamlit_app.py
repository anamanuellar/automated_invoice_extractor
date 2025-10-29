import streamlit as st
import pandas as pd
import io, json, tempfile, os
from datetime import datetime
from pathlib import Path
from extrator import processar_pdfs, exportar_para_excel_com_itens
from codigos_fiscais_destinatario import gerar_resumo_analise, analisar_nf_como_destinatario
from ia_simples import add_ia_to_streamlit
from openpyxl.styles import Font, PatternFill, Alignment

# ======================== NOVA FUNÇÃO ========================
def tornar_arrow_compatível(df: pd.DataFrame) -> pd.DataFrame:
    """
    Corrige colunas incompatíveis com Arrow (PyArrow/Streamlit).
    Converte objetos e dicts em strings JSON, preservando legibilidade.
    """
    df_corrigido = df.copy()
    for col in df_corrigido.columns:
        # detecta objetos não-serializáveis
        if df_corrigido[col].apply(
            lambda x: isinstance(x, (dict, list, object))
            and not isinstance(x, (str, int, float, bool, type(None)))
        ).any():
            if st.session_state.get("debug", False):
                st.warning(f"⚠️ Coluna '{col}' contém objetos não serializáveis — convertendo para JSON.")
            df_corrigido[col] = df_corrigido[col].apply(
                lambda x: json.dumps(x, ensure_ascii=False, indent=2)
                if not isinstance(x, (str, int, float, bool, type(None)))
                else x
            )
    return df_corrigido


# ======================== CONFIG STREAMLIT ========================
st.set_page_config(
    page_title="📄 Extrator Automático de Notas Fiscais",
    page_icon="📑",
    layout="wide"
)

st.title("📄 Extrator Automático de Notas Fiscais")
st.markdown("---")

# ======================== UPLOAD DE ARQUIVOS ========================
uploaded_files = st.file_uploader(
    "Selecione um ou mais arquivos PDF de NFs",
    type="pdf",
    accept_multiple_files=True,
    help="Você pode enviar vários arquivos de uma vez"
)

if uploaded_files:
    temp_dir = tempfile.mkdtemp()
    pdf_paths = []
    for file in uploaded_files:
        file_path = os.path.join(temp_dir, file.name)
        with open(file_path, "wb") as f:
            f.write(file.getbuffer())
        pdf_paths.append(file_path)

    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(msg):
        status_text.text(msg)

    with st.spinner("🔄 Processando PDFs..."):
        df = processar_pdfs(pdf_paths, _progress_callback=update_progress)
        progress_bar.progress(100)

    if not df.empty:
        st.success(f"✅ {len(df)} nota(s) processada(s) com sucesso!")

        # --- TORNA O DATAFRAME ARROW-COMPATÍVEL ---
        df_arrow = tornar_arrow_compatível(df)

        # --- FILTROS BÁSICOS ---
        st.subheader("📊 Dados Extraídos")
        col1, col2 = st.columns(2)
        with col1:
            filtro_nf = st.text_input("Filtrar por número de NF:")
        with col2:
            filtro_emitente = st.text_input("Filtrar por nome do emitente:")

        df_filtrado = df_arrow.copy()
        if filtro_nf:
            df_filtrado = df_filtrado[df_filtrado["numero_nf"].astype(str).str.contains(filtro_nf, na=False)]
        if filtro_emitente:
            df_filtrado = df_filtrado[
                df_filtrado["emitente_nome"].astype(str).str.contains(filtro_emitente, na=False, case=False)
            ]

        # --- EXIBE A TABELA ---
        st.dataframe(
            df_filtrado,
            use_container_width=True,
            height=400
        )

        # --- GERAR RESUMO DE ANÁLISE ---
        st.divider()
        with st.expander("🧾 Gerar Resumo da Análise Fiscal"):
            if st.button("Gerar Resumo"):
                try:
                    linha = df_filtrado.iloc[0].to_dict()
                    analise_nf = analisar_nf_como_destinatario(
                        cfop=str(linha.get("cfop", "")),
                        ncm=str(linha.get("ncm", "")),
                        csosn_ou_cst_recebido=str(linha.get("csosn", linha.get("ocst", ""))),
                        regime_destinatario=str(linha.get("regime_dest", "normal")),
                        regime_emitente=str(linha.get("regime_emit", "normal")),
                        uf_origem=str(linha.get("uf_origem", "BA")),
                        valor_total=float(linha.get("valor_total_num", 0.0))
)

                    resumo = gerar_resumo_analise(analise_nf)
                    st.text(resumo)
                except Exception as e:
                    st.error(f"Erro ao gerar resumo: {e}")

        # --- EXPORTAR RESULTADOS ---
        st.divider()
        st.subheader("📥 Exportar Resultados")

        excel_data = exportar_para_excel_com_itens(df_arrow)
        csv_data = df_arrow.to_csv(index=False, encoding="utf-8-sig")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📊 Baixar Excel",
                data=excel_data,
                file_name=f"notas_fiscais_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with col2:
            st.download_button(
                label="📋 Baixar CSV",
                data=csv_data,
                file_name=f"notas_fiscais_{timestamp}.csv",
                mime="text/csv",
            )

        # --- SEÇÃO DE IA ---
        st.divider()
        st.subheader("🤖 Análises com IA")
        add_ia_to_streamlit(df_filtrado)

    else:
        st.warning("Nenhuma nota fiscal válida foi extraída.")

    # --- LIMPEZA ---
    for file in pdf_paths:
        try:
            os.remove(file)
        except:
            pass
    os.rmdir(temp_dir)

else:
    st.info("👆 Envie um ou mais arquivos PDF para começar a extração.")
