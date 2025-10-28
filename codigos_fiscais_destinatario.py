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
from codigos_fiscais import CFOP, NCM, CSOSN, OCST


# =============== ANÁLISE COMO DESTINATÁRIO ===============

def analisar_nf_como_destinatario(
    cfop: str,
    ncm: str,
    csosn_ou_cst_recebido: str,
    regime_destinatario: str,
    regime_emitente: str,
    uf_origem: str,
    valor_total: float,
    valor_icms: Optional[float] = None,
    valor_pis: Optional[float] = None,
    valor_cofins: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Analisa uma NF do ponto de vista de quem VAI RECEBER e CONTABILIZAR
    
    Perspectiva: DESTINATÁRIO (você que vai registrar a NF)
    
    Parâmetros:
    -----------
    cfop : str
        CFOP da operação (ex: "1100", "5100")
    ncm : str
        NCM do produto (ex: "27101100")
    csosn_ou_cst_recebido : str
        CSOSN (se Simples Nacional) ou O-CST (se Lucro Real)
    regime_destinatario : str
        Seu regime: "simples", "lucro_real", "lucro_presumido"
    regime_emitente : str
        Regime de quem emitiu a NF
    uf_origem : str
        UF do emitente (para alíquotas)
    valor_total : float
        Valor total da NF
    valor_icms : float, optional
        Valor de ICMS da NF
    valor_pis : float, optional
        Valor de PIS da NF
    valor_cofins : float, optional
        Valor de COFINS da NF
    
    Retorno:
    --------
    Dict com:
    - conformidade: Está em conformidade?
    - credito_icms: Tem direito a crédito de ICMS?
    - credito_pis: Tem direito a crédito de PIS?
    - credito_cofins: Tem direito a crédito de COFINS?
    - lançamento_contabil: Sugestão de como contabilizar
    - avisos: Alertas importantes
    - alertas: Erros críticos
    """

    resultado = {
        "status": "OK",
        "regime_destinatario": regime_destinatario,
        "regime_emitente": regime_emitente,
        "conformidade": True,
        "credito_icms": {
            "direito": False,
            "valor": 0.0,
            "motivo": "",
        },
        "credito_pis": {
            "direito": False,
            "valor": 0.0,
            "motivo": "",
        },
        "credito_cofins": {
            "direito": False,
            "valor": 0.0,
            "motivo": "",
        },
        "lançamento_contabil": {},
        "avisos": [],
        "alertas": [],
    }

    # ====== 1. VALIDAR CFOP ======
    cfop_info = CFOP.buscar(cfop)
    if not cfop_info:
        resultado["alertas"].append(f"❌ CFOP {cfop} inválido")
        resultado["conformidade"] = False
    else:
        if cfop_info.tipo != "Entrada":
            resultado["avisos"].append(
                f"⚠️ CFOP {cfop} é de {cfop_info.tipo}, "
                f"esperado Entrada para destinatário"
            )

    # ====== 2. VALIDAR NCM ======
    ncm_info = None
    if ncm:
        if not NCM.validar(ncm):
            resultado["alertas"].append(f"❌ NCM {ncm} tem formato inválido")
            resultado["conformidade"] = False
        else:
            ncm_info = NCM.buscar(ncm)
            if not ncm_info:
                resultado["avisos"].append(f"⚠️ NCM {ncm} não encontrado na base")

    # ====== 3. VALIDAR CÓDIGOS DO REGIME ======
    if regime_destinatario == "simples":
        csosn_info = CSOSN.buscar(csosn_ou_cst_recebido)
        if not csosn_info:
            resultado["alertas"].append(
                f"❌ CSOSN {csosn_ou_cst_recebido} inválido "
                f"para Simples Nacional"
            )
            resultado["conformidade"] = False

        # Verificar coerência com regime do emitente
        if regime_emitente == "simples":
            pass
        else:
            resultado["avisos"].append(
                f"⚠️ {regime_emitente.title()} vendendo para Simples Nacional - "
                f"Verifique alíquota ICMS separada"
            )

    else:  # lucro_real ou lucro_presumido
        ocst_info = OCST.buscar(csosn_ou_cst_recebido)
        if not ocst_info:
            resultado["alertas"].append(
                f"❌ O-CST {csosn_ou_cst_recebido} inválido "
                f"para regime normal"
            )
            resultado["conformidade"] = False

    # ====== 4. DIREITO A CRÉDITO DE ICMS ======
    direito_credito_icms = _calcular_credito_icms(
        regime_destinatario=regime_destinatario,
        regime_emitente=regime_emitente,
        csosn_ou_cst=csosn_ou_cst_recebido,
        cfop=cfop,
        valor_icms=valor_icms,
    )

    resultado["credito_icms"] = direito_credito_icms
    if not direito_credito_icms["direito"]:
        resultado["avisos"].append(
            f"⚠️ Sem direito a crédito de ICMS: {direito_credito_icms['motivo']}"
        )

    # ====== 5. DIREITO A CRÉDITO PIS/COFINS ======
    direito_credito_pis = _calcular_credito_pis(
        regime_destinatario=regime_destinatario,
        regime_emitente=regime_emitente,
        cfop=cfop,
        valor_pis=valor_pis,
    )

    resultado["credito_pis"] = direito_credito_pis

    direito_credito_cofins = _calcular_credito_cofins(
        regime_destinatario=regime_destinatario,
        regime_emitente=regime_emitente,
        cfop=cfop,
        valor_cofins=valor_cofins,
    )

    resultado["credito_cofins"] = direito_credito_cofins

    # ====== 6. SUGERIR LANÇAMENTO CONTÁBIL ======
    resultado["lançamento_contabil"] = _sugerir_lancamento_contabil(
        regime_destinatario=regime_destinatario,
        valor_total=valor_total,
        credito_icms=direito_credito_icms["valor"],
        credito_pis=direito_credito_pis["valor"],
        credito_cofins=direito_credito_cofins["valor"],
        cfop=cfop,
    )

    # ====== 7. VALIDAÇÃO FINAL ======
    if resultado["alertas"]:
        resultado["conformidade"] = False

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


# =============== EXEMPLO DE USO ===============

if __name__ == "__main__":
    # Exemplo 1: Simples recebendo de Lucro Real
    print("=" * 70)
    print("EXEMPLO 1: Simples Nacional recebendo de Lucro Real")
    print("=" * 70)

    analise1 = analisar_nf_como_destinatario(
        cfop="1100",
        ncm="62019000",
        csosn_ou_cst_recebido="101",  # CSOSN para Simples
        regime_destinatario="simples",
        regime_emitente="lucro_real",
        uf_origem="SP",
        valor_total=1000.00,
        valor_icms=180.00,
    )

    print(gerar_resumo_analise(analise1))

    # Exemplo 2: Lucro Real recebendo de Simples
    print("\n" + "=" * 70)
    print("EXEMPLO 2: Lucro Real recebendo de Simples Nacional")
    print("=" * 70)

    analise2 = analisar_nf_como_destinatario(
        cfop="1102",  # Compra para revenda
        ncm="27101100",  # Gasolina
        csosn_ou_cst_recebido="00",  # O-CST para Lucro Real
        regime_destinatario="lucro_real",
        regime_emitente="simples",
        uf_origem="RJ",
        valor_total=5000.00,
        valor_icms=900.00,
        valor_pis=82.50,
        valor_cofins=380.00,
    )

    print(gerar_resumo_analise(analise2))
