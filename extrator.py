import re
import PyPDF2
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import pdfplumber
import pandas as pd
from typing import Dict, Optional, Tuple

class ExtractorNF:
    """Extrator robusto de Notas Fiscais com suporte a múltiplos formatos"""
    
    def __init__(self):
        self.numero_nf = None
        self.serie = None
        self.data_emissao = None
        self.cnpj_emitente = None
        self.cnpj_destinatario = None
        self.valor_total = None
        
    def detectar_rotacao(self, texto: str) -> bool:
        """
        Detecta se o PDF está rotacionado verificando padrões invertidos
        Ex: "e-FN" em vez de "NF-e", ".odal" em vez de "valor"
        """
        # Padrões que indicam rotação
        padroes_invertidos = [
            r"e-FN",  # NF-e invertido
            r"\.odal",  # valor invertido
            r"oãçitsid",  # distribuição invertido
            r"etneme",  # emitente invertido
        ]
        
        for padrao in padroes_invertidos:
            if re.search(padrao, texto):
                return True
        return False
    
    def corrigir_rotacao_texto(self, texto: str) -> str:
        """Inverte o texto se detectar rotação"""
        linhas = texto.split('\n')
        linhas_invertidas = [linha[::-1] for linha in linhas]
        return '\n'.join(linhas_invertidas)
    
    def corrigir_rotacao_imagem(self, imagem: Image.Image) -> Image.Image:
        """Rotaciona imagem 180 graus se detectar padrões invertidos"""
        # Extrair texto para verificar
        texto_original = pytesseract.image_to_string(imagem, lang='por')
        
        if self.detectar_rotacao(texto_original):
            print("🔄 Rotação detectada! Corrigindo imagem...")
            return imagem.rotate(180, expand=False)
        
        return imagem
    
    def extrair_numero_nf_primeira_linha(self, linhas: list) -> Optional[str]:
        """
        Extrai número da NF mesmo que esteja em primeira linha
        Suporta formatos:
        - Nº.: 054.013.637
        - Nº: 054013637
        - N°: 637
        """
        for ln in linhas[:5]:  # Procura nas primeiras 5 linhas
            # Padrão 1: "Nº.: XXX.XXX.XXX" (com pontos)
            m = re.search(r"N[°ºO]\.\s*[:\-]?\s*(\d{3}\.\d{3}\.\d{3,6})", ln)
            if m:
                cand = m.group(1).replace(".", "")
                try:
                    val = int(cand)
                    numero = str(val % 1000000).lstrip('0') or "0"
                    print(f"✅ Número encontrado na primeira linha: {numero}")
                    return numero
                except:
                    pass
            
            # Padrão 2: "Nº XXX XXX XXX" (com espaços)
            m = re.search(r"N[°ºO]\s*(\d{3}\s+\d{3}\s+\d{3,6})", ln)
            if m:
                cand = m.group(1).replace(" ", "")
                try:
                    val = int(cand)
                    numero = str(val % 1000000).lstrip('0') or "0"
                    print(f"✅ Número encontrado na primeira linha: {numero}")
                    return numero
                except:
                    pass
            
            # Padrão 3: Simples "Nº 637"
            m = re.search(r"N[°ºO]\s*[:\-]?\s*(\d{1,6})(?:\D|$)", ln)
            if m:
                cand = m.group(1)
                try:
                    val = int(cand)
                    if 1 <= val <= 999999:
                        print(f"✅ Número encontrado na primeira linha: {val}")
                        return str(val)
                except:
                    pass
        
        return None
    
    def extrair_serie_primeira_linha(self, linhas: list) -> Optional[str]:
        """Extrai série mesmo que esteja nas primeiras linhas"""
        for ln in linhas[:5]:
            m = re.search(r"S[ÉE]RIE\s*[:\-]?\s*(\d+)", ln, re.I)
            if m:
                try:
                    val = int(m.group(1))
                    if 0 <= val <= 999:
                        print(f"✅ Série encontrada: {val}")
                        return str(val)
                except:
                    pass
        return None
    
    def extrair_de_pdf(self, caminho_pdf: str) -> Dict:
        """Extrai informações de PDF com tratamento de rotação"""
        dados = {}
        
        try:
            # Tentar com pdfplumber primeiro
            with pdfplumber.open(caminho_pdf) as pdf:
                pagina = pdf.pages[0]
                texto_pdfplumber = pagina.extract_text()
                
                # Verificar rotação
                if self.detectar_rotacao(texto_pdfplumber):
                    print(f"⚠️  Rotação detectada no PDF: {caminho_pdf}")
                    # Converter para imagem, corrigir e reextrair
                    imagens = convert_from_path(caminho_pdf, first_page=1, last_page=1)
                    imagem_corrigida = self.corrigir_rotacao_imagem(imagens[0])
                    texto_pdfplumber = pytesseract.image_to_string(imagem_corrigida, lang='por')
                
                linhas = texto_pdfplumber.split('\n')
                
                # Extrair campos
                self.numero_nf = self.extrair_numero_nf_primeira_linha(linhas) or self._extrair_numero_padrao(linhas)
                self.serie = self.extrair_serie_primeira_linha(linhas) or self._extrair_serie_padrao(linhas)
                
                dados['numero_nf'] = self.numero_nf
                dados['serie'] = self.serie
                dados['cnpj_emitente'] = self._extrair_cnpj_emitente(linhas)
                dados['cnpj_destinatario'] = self._extrair_cnpj_destinatario(linhas)
                dados['valor_total'] = self._extrair_valor_total(linhas)
                dados['data_emissao'] = self._extrair_data(linhas)
                
        except Exception as e:
            print(f"❌ Erro ao extrair de {caminho_pdf}: {str(e)}")
            dados['erro'] = str(e)
        
        return dados
    
    def _extrair_numero_padrao(self, linhas: list) -> Optional[str]:
        """Extrai número usando padrão original (alternativo)"""
        for ln in linhas:
            m = re.search(r"N[°ºO][^:\d]*[:\-]?\s*(\d+(?:\.\d+)*)", ln)
            if m:
                cand = m.group(1).replace(".", "")
                try:
                    val = int(cand)
                    if 1 <= val <= 999999:
                        return str(val)
                except:
                    pass
        return None
    
    def _extrair_serie_padrao(self, linhas: list) -> Optional[str]:
        """Extrai série usando padrão original (alternativo)"""
        for ln in linhas:
            m = re.search(r"SÉRIE.*?(\d+)", ln, re.I)
            if m:
                return m.group(1)
        return None
    
    def _extrair_cnpj_emitente(self, linhas: list) -> Optional[str]:
        """Extrai CNPJ do emitente"""
        for i, ln in enumerate(linhas):
            if "EMITENTE" in ln.upper() or "FORNECEDOR" in ln.upper():
                # Procura nos próximos 3 linhas
                for j in range(i+1, min(i+4, len(linhas))):
                    m = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", linhas[j])
                    if m:
                        return m.group(1)
        return None
    
    def _extrair_cnpj_destinatario(self, linhas: list) -> Optional[str]:
        """Extrai CNPJ do destinatário"""
        for i, ln in enumerate(linhas):
            if "DESTINAT" in ln.upper() or "CLIENTE" in ln.upper():
                for j in range(i+1, min(i+4, len(linhas))):
                    m = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", linhas[j])
                    if m:
                        return m.group(1)
        return None
    
    def _extrair_valor_total(self, linhas: list) -> Optional[float]:
        """Extrai valor total da NF"""
        for ln in linhas:
            if "VALOR TOTAL" in ln.upper() or "TOTAL" in ln.upper():
                m = re.search(r"R\$?\s*([\d.,]+)", ln)
                if m:
                    valor_str = m.group(1).replace(".", "").replace(",", ".")
                    try:
                        return float(valor_str)
                    except:
                        pass
        return None
    
    def _extrair_data(self, linhas: list) -> Optional[str]:
        """Extrai data de emissão"""
        # Padrão dd/mm/yyyy
        for ln in linhas[:20]:
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", ln)
            if m:
                return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        return None


# Exemplo de uso
if __name__ == "__main__":
    extrator = ExtractorNF()
    
    # Processar PDFs
    pdfs = [
        "NF_EBAZAR.pdf",
        "NF_DELL.pdf",
    ]
    
    resultados = []
    for pdf in pdfs:
        print(f"\n📄 Processando: {pdf}")
        print("-" * 50)
        dados = extrator.extrair_de_pdf(pdf)
        dados['arquivo'] = pdf
        resultados.append(dados)
        
        for chave, valor in dados.items():
            print(f"  {chave}: {valor}")
    
    # Salvar resultados
    df = pd.DataFrame(resultados)
    df.to_csv("resultados_extracao.csv", index=False)
    print("\n✅ Resultados salvos em 'resultados_extracao.csv'")