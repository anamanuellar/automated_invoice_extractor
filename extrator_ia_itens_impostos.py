"""
MÓDULO DE EXTRAÇÃO COM IA GENERATIVA
=====================================

Usa Google Gemini para extrair:
- Itens de produtos/serviços
- Impostos (ICMS, IPI, PIS, COFINS)
- Códigos fiscais (CFOP, NCM, CSOSN/O-CST)

Mantém extração regex para dados simples (NF, série, data, CNPJ)
Delega para IA apenas o complexo (itens e impostos)

Autor: Sistema Financeiro IA
Data: 2025
"""

from typing import Dict, List, Optional, Any, Tuple, Callable
import json
import re
from datetime import datetime

# Type stubs para evitar erros de "possibly unbound"
configure: Optional[Callable[..., None]] = None
GenerativeModel: Optional[type] = None
GEMINI_DISPONIVEL: bool = False

try:
    from google.generativeai.client import configure
    from google.generativeai.generative_models import GenerativeModel
    GEMINI_DISPONIVEL = True
except ImportError:
    GEMINI_DISPONIVEL = False


class ExtractorIA:
    """Extrator com IA Generativa para itens e impostos de NF"""
    
    def __init__(self, api_key: str):
        """
        Inicializa o extrator com Gemini
        
        Args:
            api_key: Chave da API Google Gemini
        """
        try:
            if not GEMINI_DISPONIVEL:
                raise ImportError("google-generativeai não está instalado")
            
            if configure is None or GenerativeModel is None:
                raise ImportError("google-generativeai não pôde ser importado")
            
            configure(api_key=api_key)  # type: ignore
            self.model: Optional[Any] = GenerativeModel('gemini-pro')  # type: ignore
            self.status: str = "CONECTADO ✅"
        except Exception as e:
            self.status = f"ERRO: {str(e)}"
            self.model = None
    
    # ============ EXTRAÇÃO DE ITENS COM IA =============
    
    def extrair_itens_com_ia(self, texto_nf: str) -> List[Dict[str, Any]]:
        """
        Extrai itens (produtos/serviços) da NF usando IA
        
        Args:
            texto_nf: Texto completo da nota fiscal
            
        Returns:
            Lista com dicts contendo: codigo, descricao, ncm, cfop, 
            quantidade, valor_unitario, valor_total, aliquota_icms, aliquota_ipi
        """
        if not self.model:
            return []
        
        prompt = f"""
Analise o seguinte texto de Nota Fiscal e extraia TODOS os itens (produtos ou serviços).

Para CADA item, extraia:
1. Código do produto (se houver)
2. Descrição completa
3. NCM (8 dígitos, ex: 87039000)
4. CFOP (4 dígitos, ex: 5100)
5. Quantidade
6. Valor unitário
7. Valor total do item
8. Alíquota ICMS (%)
9. Alíquota IPI (%)
10. CSOSN ou O-CST (se Simples Nacional ou Normal)

IMPORTANTE:
- Se não encontrar NCM, tente inferir pela descrição
- Se não encontrar CFOP, assume 5100 (venda)
- Se não encontrar CSOSN/CST, deixe vazio
- Alíquotas: coloque 0 se isento/não incidente
- Mantenha o mesmo padrão de formatação

TEXTO DA NOTA FISCAL:
{texto_nf}

RESPONDA EM JSON PURO (sem markdown, sem ```):
[
  {{
    "codigo": "string",
    "descricao": "string",
    "ncm": "string (8 dígitos)",
    "cfop": "string (4 dígitos)",
    "quantidade": number,
    "valor_unitario": number,
    "valor_total": number,
    "aliquota_icms": number (0-100),
    "aliquota_ipi": number (0-100),
    "csosn_ou_cst": "string"
  }}
]

Se não houver itens, retorne: []
"""
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Remove markdown code blocks se existirem
            response_text = re.sub(r'^```json\n?', '', response_text)
            response_text = re.sub(r'\n?```$', '', response_text)
            
            items = json.loads(response_text)
            
            # Validação e limpeza
            items_limpos = []
            for item in items:
                item_limpo = self._validar_item(item)
                if item_limpo:
                    items_limpos.append(item_limpo)
            
            return items_limpos
        
        except Exception as e:
            print(f"Erro ao extrair itens com IA: {e}")
            return []
    
    def _validar_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Valida e limpa dados do item"""
        try:
            # Garante tipos corretos
            item_limpo = {
                "codigo": str(item.get("codigo", "")).strip() or None,
                "descricao": str(item.get("descricao", "")).strip(),
                "ncm": str(item.get("ncm", "")).strip() or None,
                "cfop": str(item.get("cfop", "5100")).strip(),  # Default 5100
                "quantidade": float(item.get("quantidade", 1)),
                "valor_unitario": float(item.get("valor_unitario", 0)),
                "valor_total": float(item.get("valor_total", 0)),
                "aliquota_icms": float(item.get("aliquota_icms", 0)),
                "aliquota_ipi": float(item.get("aliquota_ipi", 0)),
                "csosn_ou_cst": str(item.get("csosn_ou_cst", "")).strip() or None,
            }
            
            # Validação mínima
            if not item_limpo["descricao"] or item_limpo["valor_total"] <= 0:
                return None
            
            return item_limpo
        
        except Exception:
            return None
    
    # ============ EXTRAÇÃO DE IMPOSTOS COM IA =============
    
    def extrair_impostos_com_ia(self, texto_nf: str) -> Dict[str, Any]:
        """
        Extrai informações de impostos da NF usando IA
        
        Returns:
            Dict com: valor_icms, valor_ipi, valor_pis, valor_cofins,
            base_calculo_icms, base_calculo_pis_cofins, regime_tributario
        """
        if not self.model:
            return {}
        
        prompt = f"""
Analise a SEÇÃO DE CÁLCULO DE IMPOSTOS desta Nota Fiscal e extraia os valores:

VALORES A EXTRAIR:
1. Valor Total de ICMS
2. Valor Total de IPI
3. Valor Total de PIS
4. Valor Total de COFINS
5. Base de Cálculo do ICMS
6. Base de Cálculo de PIS/COFINS
7. Regime tributário do emitente (Simples Nacional, Lucro Real, Lucro Presumido, Normal)
8. Indicador de Presença de Substituição Tributária (ST)
9. ICMS Substituto (se houver)
10. ICMS Próprio

IMPORTANTE:
- Se valor não aparecer, coloque 0
- Regime: use exatamente um de: "simples", "lucro_real", "lucro_presumido", "normal"
- ST (Substituição Tributária): true/false
- Mantenha 2 casas decimais

TEXTO DA NOTA FISCAL:
{texto_nf}

RESPONDA EM JSON PURO (sem markdown):
{{
  "valor_icms": number,
  "valor_ipi": number,
  "valor_pis": number,
  "valor_cofins": number,
  "base_calculo_icms": number,
  "base_calculo_pis_cofins": number,
  "regime_tributario": "string (simples|lucro_real|lucro_presumido|normal)",
  "tem_substituicao_tributaria": boolean,
  "valor_icms_st": number,
  "valor_icms_proprio": number,
  "observacoes": "string"
}}
"""
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Remove markdown
            response_text = re.sub(r'^```json\n?', '', response_text)
            response_text = re.sub(r'\n?```$', '', response_text)
            
            impostos = json.loads(response_text)
            
            # Validação
            impostos_limpos = {
                "valor_icms": float(impostos.get("valor_icms", 0)),
                "valor_ipi": float(impostos.get("valor_ipi", 0)),
                "valor_pis": float(impostos.get("valor_pis", 0)),
                "valor_cofins": float(impostos.get("valor_cofins", 0)),
                "base_calculo_icms": float(impostos.get("base_calculo_icms", 0)),
                "base_calculo_pis_cofins": float(impostos.get("base_calculo_pis_cofins", 0)),
                "regime_tributario": str(impostos.get("regime_tributario", "normal")),
                "tem_substituicao_tributaria": bool(impostos.get("tem_substituicao_tributaria", False)),
                "valor_icms_st": float(impostos.get("valor_icms_st", 0)),
                "valor_icms_proprio": float(impostos.get("valor_icms_proprio", 0)),
                "observacoes": str(impostos.get("observacoes", "")),
            }
            
            return impostos_limpos
        
        except Exception as e:
            print(f"Erro ao extrair impostos com IA: {e}")
            return {}
    
    # ============ EXTRAÇÃO DE CÓDIGOS FISCAIS COM IA =============
    
    def extrair_codigos_fiscais_com_ia(self, texto_nf: str) -> Dict[str, Any]:
        """
        Extrai todos os códigos fiscais relevantes com IA
        
        Returns:
            Dict com: cfop_principal, ncm_items, csosn_simples, ocst_normal, regime
        """
        if not self.model:
            return {}
        
        prompt = f"""
Analise esta Nota Fiscal e extraia TODOS os códigos fiscais relevantes:

1. CFOP (Código Fiscal de Operação):
   - Principal (mais frequente): 4 dígitos
   - Significado em português

2. NCM (Nomenclatura Comum MERCOSUL):
   - Para cada produto: 8 dígitos
   - Descrição

3. CSOSN (Simples Nacional):
   - Se Simples: 3 dígitos
   - Descrição

4. O-CST (Regime Normal):
   - Se Normal: 2 dígitos
   - Descrição

5. PIS/COFINS:
   - Códigos de situação (CST PIS/COFINS)

6. ICMS:
   - Origem da Mercadoria (0-8)
   - Tributação do ICMS (00-90)

7. Regime Tributário do Emitente

TEXTO DA NOTA FISCAL:
{texto_nf}

RESPONDA EM JSON PURO:
{{
  "cfop_principal": {{
    "codigo": "string (4 dígitos)",
    "descricao": "string",
    "tipo": "string (Entrada|Saída|Transferência|Devolução)"
  }},
  "ncm_items": [
    {{
      "codigo": "string (8 dígitos)",
      "descricao": "string"
    }}
  ],
  "csosn_simples": {{
    "codigo": "string (3 dígitos)",
    "descricao": "string"
  }},
  "ocst_normal": {{
    "codigo": "string (2 dígitos)",
    "descricao": "string"
  }},
  "regime_tributario": "string (simples|lucro_real|lucro_presumido|normal)",
  "origem_mercadoria": number (0-8),
  "tributacao_icms": "string (00-90)",
  "cst_pis": "string (01-08)",
  "cst_cofins": "string (01-08)"
}}
"""
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Remove markdown
            response_text = re.sub(r'^```json\n?', '', response_text)
            response_text = re.sub(r'\n?```$', '', response_text)
            
            codigos = json.loads(response_text)
            return codigos
        
        except Exception as e:
            print(f"Erro ao extrair códigos com IA: {e}")
            return {}
    
    # ============ EXTRAÇÃO CONSOLIDADA =============
    
    def extrair_nf_completa(self, texto_nf: str) -> Dict[str, Any]:
        """
        Extração consolidada: usa IA para itens e impostos
        
        Returns:
            Dict com todos os dados da NF estruturados
        """
        resultado = {
            "itens": self.extrair_itens_com_ia(texto_nf),
            "impostos": self.extrair_impostos_com_ia(texto_nf),
            "codigos_fiscais": self.extrair_codigos_fiscais_com_ia(texto_nf),
            "timestamp": datetime.now().isoformat()
        }
        
        return resultado


# ============ FUNÇÕES AUXILIARES =============

def verificar_gemini_extractor(api_key: str) -> Tuple[bool, str]:
    """Verifica se a chave Gemini funciona para extração"""
    try:
        if not GEMINI_DISPONIVEL:
            return False, "google-generativeai não está instalado. Instale com: pip install google-generativeai"
        
        extractor: ExtractorIA = ExtractorIA(api_key)
        if "ERRO" in extractor.status:
            return False, extractor.status
        return True, extractor.status
    except Exception as e:
        return False, f"Erro: {str(e)}"


def testar_extractor_ia(api_key: str, texto_teste: str) -> Dict[str, Any]:
    """Testa o extractor com um texto de exemplo"""
    extractor = ExtractorIA(api_key)
    
    if "ERRO" in extractor.status:
        return {"status": "ERRO", "mensagem": extractor.status}
    
    resultado = extractor.extrair_nf_completa(texto_teste)
    resultado["status"] = "OK"
    
    return resultado