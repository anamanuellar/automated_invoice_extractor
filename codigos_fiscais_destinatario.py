"""
Análise de Notas Fiscais - Perspectiva do DESTINATÁRIO
=======================================================

Módulo especializado em analisar NFs do ponto de vista de quem vai RECEBER e CONTABILIZAR

Principais funcionalidades:
- Validar direito a crédito de ICMS
- Validar direito a crédito de PIS/COFINS
- Sugerir lançamento contábil
- Verificar conformidade com regime tributário
- Calcular impacto fiscal da operação

Autor: Sistema de Extrator de Notas Fiscais
"""

from typing import Dict, List, Optional, Any
from codigos_fiscais import CFOP, NCM, CSOSN, OCST, RegimeTributario


# =============== ANÁLISE COMO DESTINATÁRIO ===============

# =============== ANÁLISE COMO DESTINATÁRIO ===============

def analisar_nf_como_destinatario(
    cfop: str,
    ncm: str,
    csosn_ou_cst_recebido: str,
    regime_destinatario: str,
    regime_emitente: str,
    uf_origem: str,
    valor_total: float
) -> Dict[str, Any]:
    """
    Analisa a nota fiscal do ponto de vista do destinatário (empresa que recebe).
    Retorna informações sobre conformidade fiscal, créditos e possíveis alertas.
    
    Ajuste: Adicionada lógica para validação e cálculo de crédito mínimo.
    """
    # AJUSTE: Adicionar PISCOFINS
    from codigos_fiscais import CFOP, NCM, OCST, CSOSN, PISCOFINS 

    # 1. Normalizar Regimes
    regime_dest = RegimeTributario.normalize(regime_destinatario)
    regime_emit = RegimeTributario.normalize(regime_emitente)
    
    # Inicializar resultado
    resultado = {
        "regime_destinatario": regime_dest,
        "regime_emitente": regime_emit,
        "conformidade": True,
        "credito_icms": {"direito": False, "valor": 0.0, "motivo": "N/A"},
        "credito_pis": {"direito": False, "valor": 0.0, "motivo": "N/A"},
        "credito_cofins": {"direito": False, "valor": 0.0, "motivo": "N/A"},
        "lançamento_contabil": {}, 
        "avisos": [],
        "alertas": [],
        "status": "OK"
    }
    
    # 2. Validação de Códigos Fiscais
    cfop_info = CFOP.buscar(cfop)
    if not cfop_info:
        resultado["conformidade"] = False
        resultado["alertas"].append(f"❌ CFOP {cfop} inválido ou não encontrado na base de dados.")
        
    # Verifica se CST/CSOSN é compatível com o regime do emitente
    if regime_emit == 'simples':
        tributo_info = CSOSN.buscar(csosn_ou_cst_recebido)
        if not tributo_info:
            resultado["conformidade"] = False
            resultado["alertas"].append(f"❌ CSOSN {csosn_ou_cst_recebido} inválido para Simples Nacional.")
        
    else: # Regime Normal (Lucro Real/Presumido)
        tributo_info = OCST.buscar(csosn_ou_cst_recebido)
        if not tributo_info:
            resultado["conformidade"] = False
            # Ajuste: A mensagem anterior estava incorreta.
            resultado["alertas"].append(f"❌ O-CST {csosn_ou_cst_recebido} inválido para Regime Normal.")
            
    resultado["cfop_info"] = cfop_info
    resultado["tributo_info"] = tributo_info

    # 3. Lógica de Crédito (Simplificada - Foco no Destinatário Normal)
    
    # Crédito de ICMS (Regime Normal Destinatário)
    if regime_dest == 'normal':
        if regime_emit == 'simples' and csosn_ou_cst_recebido in ["101", "201", "900"]:
            resultado["credito_icms"]["motivo"] = "Possível crédito. Verificar valor da alíquota nas 'Informações Complementares' da NF."
        elif cfop_info and cfop_info.icms_aplica and tributo_info and tributo_info.codigo in ['00', '20', '90']: # Cobre ICMS cobrado
            resultado["credito_icms"]["motivo"] = "Possível crédito. Depende do destaque de ICMS na NF."
        else:
            resultado["credito_icms"]["motivo"] = "Sem destaque de ICMS na nota para aproveitamento de crédito."

    # Crédito de PIS/COFINS (Regime Normal Destinatário) - Simplificação
    if regime_dest == 'normal' and cfop_info and cfop_info.tipo == "Entrada":
        aliquotas = PISCOFINS.get_aliquota_pis_cofins(regime_dest)
        # Crédito de PIS/COFINS geralmente é permitido para entradas (CST 50 a 66), exceto Simples Nacional
        if regime_emit == 'normal' and tributo_info and tributo_info.codigo in ['50', '51', '52', '53', '54', '55', '56', '60', '61', '62', '63', '64', '65', '66']:
            resultado["credito_pis"]["direito"] = True
            resultado["credito_pis"]["valor"] = valor_total * aliquotas['pis'] / 100
            resultado["credito_pis"]["motivo"] = "Crédito presumido de PIS (Regime Normal)."
            
            resultado["credito_cofins"]["direito"] = True
            resultado["credito_cofins"]["valor"] = valor_total * aliquotas['cofins'] / 100
            resultado["credito_cofins"]["motivo"] = "Crédito presumido de COFINS (Regime Normal)."
        else:
             resultado["credito_pis"]["motivo"] = "Não há direito a crédito de PIS na maioria dos casos (verificar exceções)."
             resultado["credito_cofins"]["motivo"] = "Não há direito a crédito de COFINS na maioria dos casos (verificar exceções)."

    # Fallback/Avisos
    if not resultado["credito_icms"]["direito"] and regime_dest == 'normal' and not any(aviso in resultado["credito_icms"]["motivo"] for aviso in ["Verificar", "Possível"]):
         resultado["avisos"].append(f"⚠️ Sem direito a crédito de ICMS: {resultado['credito_icms']['motivo']}")
    if not resultado["credito_pis"]["direito"] and regime_dest == 'normal':
         resultado["avisos"].append(f"⚠️ Sem direito a crédito de PIS: {resultado['credito_pis']['motivo']}")
    if not resultado["credito_cofins"]["direito"] and regime_dest == 'normal':
         resultado["avisos"].append(f"⚠️ Sem direito a crédito de COFINS: {resultado['credito_cofins']['motivo']}")
         
    return resultado

# =============== CÁLCULO DE CRÉDITOS ===============

def _calcular_credito_icms(
    regime_destinatario: str,
    regime_emitente: str,
    csosn_ou_cst: str,
    cfop: str,
    valor_icms: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calcula se destinatário tem direito a crédito de ICMS
    
    Regras:
    - Simples Nacional: NUNCA tem crédito de ICMS
    - Lucro Real/Presumido: TEM crédito se operação normal
    """

    resultado = {
        "direito": False,
        "valor": 0.0,
        "motivo": "",
    }

    if not valor_icms or valor_icms <= 0:
        resultado["motivo"] = "Sem ICMS na nota"
        return resultado

    # ❌ SIMPLES NACIONAL não tem crédito de ICMS
    if regime_destinatario == "simples":
        resultado["motivo"] = "Simples Nacional não aproveita crédito de ICMS"
        return resultado

    # ✅ LUCRO REAL/PRESUMIDO tem crédito em operações normais
    if regime_destinatario in ["lucro_real", "lucro_presumido"]:
        # Verificar tipo de operação (CFOP)
        cfop_info = CFOP.buscar(cfop)
        if cfop_info and cfop_info.icms_aplica:
            # Verificar código de situação
            ocst_info = OCST.buscar(csosn_ou_cst)
            if ocst_info and ocst_info.credito_icms:
                resultado["direito"] = True
                resultado["valor"] = valor_icms
                resultado["motivo"] = "Crédito permitido para regime normal"
                return resultado
            else:
                resultado["motivo"] = (
                    f"O-CST {csosn_ou_cst} não permite crédito de ICMS "
                    f"(ex: isento, diferido, ST)"
                )
                return resultado
        else:
            resultado["motivo"] = "CFOP não aplica ICMS"
            return resultado

    resultado["motivo"] = "Regime não identificado"
    return resultado


def _calcular_credito_pis(
    regime_destinatario: str,
    regime_emitente: str,
    cfop: str,
    valor_pis: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calcula se destinatário tem direito a crédito de PIS
    
    Regras:
    - Simples Nacional: Não tem crédito de PIS (já está tudo na alíquota)
    - Lucro Real: TEM crédito de PIS em operações de entrada
    - Lucro Presumido: NÃO tem crédito de PIS
    """

    resultado = {
        "direito": False,
        "valor": 0.0,
        "motivo": "",
    }

    if not valor_pis or valor_pis <= 0:
        resultado["motivo"] = "Sem PIS na nota"
        return resultado

    # ✅ Apenas LUCRO REAL tem crédito de PIS
    if regime_destinatario == "lucro_real":
        cfop_info = CFOP.buscar(cfop)
        if cfop_info and cfop_info.tipo == "Entrada":
            resultado["direito"] = True
            resultado["valor"] = valor_pis
            resultado["motivo"] = "Crédito de PIS permitido em Lucro Real (entrada)"
            return resultado
        else:
            resultado["motivo"] = "PIS em Lucro Real só tem crédito em entradas"
            return resultado

    # ❌ Simples e Lucro Presumido não têm
    resultado["motivo"] = (
        f"PIS: {regime_destinatario.title()} não aproveita crédito"
    )
    return resultado


def _calcular_credito_cofins(
    regime_destinatario: str,
    regime_emitente: str,
    cfop: str,
    valor_cofins: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calcula se destinatário tem direito a crédito de COFINS
    
    Regras:
    - Simples Nacional: Não tem crédito de COFINS (já está tudo na alíquota)
    - Lucro Real: TEM crédito de COFINS em operações de entrada
    - Lucro Presumido: NÃO tem crédito de COFINS
    """

    resultado = {
        "direito": False,
        "valor": 0.0,
        "motivo": "",
    }

    if not valor_cofins or valor_cofins <= 0:
        resultado["motivo"] = "Sem COFINS na nota"
        return resultado

    # ✅ Apenas LUCRO REAL tem crédito de COFINS
    if regime_destinatario == "lucro_real":
        cfop_info = CFOP.buscar(cfop)
        if cfop_info and cfop_info.tipo == "Entrada":
            resultado["direito"] = True
            resultado["valor"] = valor_cofins
            resultado["motivo"] = "Crédito de COFINS permitido em Lucro Real (entrada)"
            return resultado
        else:
            resultado["motivo"] = "COFINS em Lucro Real só tem crédito em entradas"
            return resultado

    # ❌ Simples e Lucro Presumido não têm
    resultado["motivo"] = (
        f"COFINS: {regime_destinatario.title()} não aproveita crédito"
    )
    return resultado


# =============== LANÇAMENTO CONTÁBIL ===============

def _sugerir_lancamento_contabil(
    regime_destinatario: str,
    valor_total: float,
    credito_icms: float = 0.0,
    credito_pis: float = 0.0,
    credito_cofins: float = 0.0,
    cfop: str = "1100",
) -> Dict[str, Any]:
    """
    Sugere como contabilizar a NF conforme regime do destinatário
    
    Simples Nacional:
    - ICMS já vem incluso no valor (não destaca)
    
    Lucro Real/Presumido:
    - Destaca ICMS a recuperar
    - Destaca PIS/COFINS a recuperar
    """

    lancamento = {
        "regime": regime_destinatario,
        "tipo_operacao": "",
        "debitos": [],
        "creditos": [],
        "resumo": "",
        "observacoes": [],
    }

    cfop_info = CFOP.buscar(cfop)
    if cfop_info:
        lancamento["tipo_operacao"] = cfop_info.descricao

    if regime_destinatario == "simples":
        # ===== SIMPLES NACIONAL =====
        # Tudo junto, ICMS já incluso
        lancamento["debitos"].append({
            "conta": "1.1.1.2.001 - Estoque de Mercadorias",
            "valor": valor_total,
            "descricao": f"Mercadoria recebida ({cfop_info.descricao if cfop_info else 'CFOP'})"
        })

        lancamento["creditos"].append({
            "conta": "2.1.1.001 - Fornecedores a Pagar",
            "valor": valor_total,
            "descricao": "Fornecedor"
        })

        lancamento["resumo"] = f"Compra de R$ {valor_total:.2f} (ICMS incluso)"
        
        lancamento["observacoes"] = [
            "✓ Em Simples Nacional, o ICMS já vem incluso no valor",
            "✓ Não há destaque de créditos de impostos",
            "✓ O imposto é recolhido mensalmente via DAS"
        ]

    elif regime_destinatario in ["lucro_real", "lucro_presumido"]:
        # ===== LUCRO REAL/PRESUMIDO =====
        # Destaca impostos
        valor_base = valor_total - credito_icms - credito_pis - credito_cofins

        lancamento["debitos"].append({
            "conta": "1.1.1.2.001 - Estoque de Mercadorias",
            "valor": valor_base,
            "descricao": f"Custo da mercadoria (sem impostos)",
        })

        total_debitado = valor_base

        if credito_icms > 0:
            lancamento["debitos"].append({
                "conta": "1.1.2.1.001 - ICMS a Recuperar",
                "valor": credito_icms,
                "descricao": "Crédito de ICMS"
            })
            total_debitado += credito_icms

        if credito_pis > 0:
            lancamento["debitos"].append({
                "conta": "1.1.2.1.002 - PIS a Recuperar",
                "valor": credito_pis,
                "descricao": "Crédito de PIS"
            })
            total_debitado += credito_pis

        if credito_cofins > 0:
            lancamento["debitos"].append({
                "conta": "1.1.2.1.003 - COFINS a Recuperar",
                "valor": credito_cofins,
                "descricao": "Crédito de COFINS"
            })
            total_debitado += credito_cofins

        lancamento["creditos"].append({
            "conta": "2.1.1.001 - Fornecedores a Pagar",
            "valor": valor_total,
            "descricao": "Fornecedor"
        })

        # Montagem do resumo
        creditos_str = []
        if credito_icms > 0:
            creditos_str.append(f"ICMS R$ {credito_icms:.2f}")
        if credito_pis > 0:
            creditos_str.append(f"PIS R$ {credito_pis:.2f}")
        if credito_cofins > 0:
            creditos_str.append(f"COFINS R$ {credito_cofins:.2f}")

        creditos_texto = ", ".join(creditos_str) if creditos_str else "nenhum"
        lancamento["resumo"] = (
            f"Compra de R$ {valor_total:.2f} "
            f"(custo R$ {valor_base:.2f} + créditos: {creditos_texto})"
        )

        regime_texto = "Lucro Real" if regime_destinatario == "lucro_real" else "Lucro Presumido"
        lancamento["observacoes"] = [
            f"✓ Em {regime_texto}, os impostos são destacados",
            f"✓ Créditos de impostos: {creditos_texto}",
            f"✓ Custo real da mercadoria: R$ {valor_base:.2f}",
        ]

    return lancamento


# =============== RESUMO DE ANÁLISE ===============

def gerar_resumo_analise(analise: Dict[str, Any]) -> str:
    """
    Gera um resumo textual da análise para apresentação
    """

    resume = f"""
╔════════════════════════════════════════════════════════════════╗
║         ANÁLISE DE NOTA FISCAL - PERSPECTIVA DESTINATÁRIO      ║
╚════════════════════════════════════════════════════════════════╝

📊 DADOS BÁSICOS
├─ Seu Regime: {analise['regime_destinatario'].upper()}
├─ Regime do Emitente: {analise['regime_emitente'].upper()}
└─ Conformidade: {'✅ OK' if analise['conformidade'] else '❌ PROBLEMAS'}

💰 DIREITOS A CRÉDITOS
├─ ICMS: {'✅ ' + f"R$ {analise['credito_icms']['valor']:.2f}" if analise['credito_icms']['direito'] else '❌ Sem direito'}
│  └─ Motivo: {analise['credito_icms']['motivo']}
├─ PIS:  {'✅ ' + f"R$ {analise['credito_pis']['valor']:.2f}" if analise['credito_pis']['direito'] else '❌ Sem direito'}
│  └─ Motivo: {analise['credito_pis']['motivo']}
└─ COFINS: {'✅ ' + f"R$ {analise['credito_cofins']['valor']:.2f}" if analise['credito_cofins']['direito'] else '❌ Sem direito'}
   └─ Motivo: {analise['credito_cofins']['motivo']}

⚠️  AVISOS ({len(analise['avisos'])})
"""

    for i, aviso in enumerate(analise['avisos'], 1):
        resume += f"├─ {i}. {aviso}\n"

    if analise['alertas']:
        resume += f"\n🚨 ALERTAS CRÍTICOS ({len(analise['alertas'])})\n"
        for i, alerta in enumerate(analise['alertas'], 1):
            resume += f"├─ {i}. {alerta}\n"

    lancamento = analise['lançamento_contabil']
    if lancamento:
        resume += f"""
📝 LANÇAMENTO CONTÁBIL SUGERIDO
├─ Tipo: {lancamento['tipo_operacao']}
├─ Resumo: {lancamento['resumo']}
└─ Observações:
"""
        for obs in lancamento['observacoes']:
            resume += f"   {obs}\n"

    resume += "╚════════════════════════════════════════════════════════════════╝\n"

    return resume


