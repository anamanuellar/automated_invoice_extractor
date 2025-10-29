"""
Biblioteca de Códigos Fiscais Brasileiros
==========================================

Módulo contendo:
- CFOP (Código Fiscal de Operação e Prestação)
- NCM (Nomenclatura Comum do MERCOSUL)
- CSOSN (Código de Situação da Operação - Simples Nacional)
- O-CST (Código de Situação Tributária - Régimen Normal)
- Alíquotas ICMS por Estado
- Regime Tributário

Autor: Sistema de Extrator de Notas Fiscais
Data: 2025
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import asdict, dataclass
from enum import Enum


DEBUG = True


# =============== ENUMS E CLASSES ===============

class RegimeTributario(Enum):
    """Regime Tributário Brasileiro"""
    # AJUSTE: Mudar para string minúscula para padronizar
    SIMPLES_NACIONAL = "simples" 
    LUCRO_PRESUMIDO = "presumido"
    LUCRO_REAL = "real"
    NORMAL = "normal" # Adicionar 'normal' como categoria principal para Presumido/Real

    @staticmethod
    def normalize(regime: str) -> str:
        """Normaliza a string de regime para 'simples' ou 'normal'."""
        if not regime:
            return 'normal' # Default para quem não for Simples
            
        regime_lower = regime.lower()
        if 'simples' in regime_lower or 'nacional' in regime_lower:
            return 'simples'
        if 'real' in regime_lower or 'presumido' in regime_lower or 'normal' in regime_lower:
            return 'normal' 
        return 'normal' # Engloba Lucro Real, Presumido e outros não Simples



@dataclass
class CFOPInfo:
    """Informações de CFOP"""
    codigo: str
    descricao: str
    tipo: str  # Entrada, Saída, Transferência, Devolução
    natureza: str  # NF, Complementar, Ajuste, Cancelamento
    icms_aplica: bool
    ipi_aplica: bool


@dataclass
class NCMInfo:
    """Informações de NCM"""
    codigo: str
    descricao: str
    aliquota_icms_padrao: float
    aliquota_ipi: float
    exigibilidade_tributo: str


@dataclass
class CSOSNInfo:
    """Informações de CSOSN (Simples Nacional)"""
    codigo: str
    descricao: str
    aplica_icms: bool
    aplica_pis: bool
    aplica_cofins: bool
    credito_icms: bool


@dataclass
class OCSTPInfo:
    """Informações de O-CST (Régimen Normal)"""
    codigo: str
    descricao: str
    aplica_icms: bool
    credito_icms: bool
    substitui_tributaria: bool


# =============== CFOP - CÓDIGO FISCAL DE OPERAÇÃO E PRESTAÇÃO ===============

class CFOP:
    """
    CFOP (Código Fiscal de Operação e Prestação)
    Classifica as operações econômicas
    """

    # CFOP Entrada (1xxx)
    ENTRADAS = {
        "1100": CFOPInfo(
            codigo="1100",
            descricao="Compra para revenda",
            tipo="Entrada",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "1101": CFOPInfo(
            codigo="1101",
            descricao="Compra para revenda - Cancelamento",
            tipo="Entrada",
            natureza="Cancelamento",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "1102": CFOPInfo(
            codigo="1102",
            descricao="Compra para revenda - Devolução",
            tipo="Entrada",
            natureza="Devolução",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "1111": CFOPInfo(
            codigo="1111",
            descricao="Compra para revenda - Tributada pelo ICMS",
            tipo="Entrada",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "1120": CFOPInfo(
            codigo="1120",
            descricao="Compra para industrialização",
            tipo="Entrada",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "1200": CFOPInfo(
            codigo="1200",
            descricao="Devolução de vendas de mercadoria produzida ou industrializada",
            tipo="Entrada",
            natureza="Devolução",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "1300": CFOPInfo(
            codigo="1300",
            descricao="Compra de Ativo Imobilizado",
            tipo="Entrada",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=False
        ),
        "1400": CFOPInfo(
            codigo="1400",
            descricao="Compra de matéria-prima para uso na industrialização",
            tipo="Entrada",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "1500": CFOPInfo(
            codigo="1500",
            descricao="Compra de material de embalagem",
            tipo="Entrada",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "1600": CFOPInfo(
            codigo="1600",
            descricao="Compra de material de uso e consumo",
            tipo="Entrada",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=False
        ),
        "1900": CFOPInfo(
            codigo="1900",
            descricao="Outra operação com entrada de mercadoria ou serviço",
            tipo="Entrada",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=True
        ),
    }

    # CFOP Saída (5xxx)
    SAIDAS = {
        "5100": CFOPInfo(
            codigo="5100",
            descricao="Venda de mercadoria produzida ou industrializada",
            tipo="Saída",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "5101": CFOPInfo(
            codigo="5101",
            descricao="Venda de produto industrializado - Cancelamento",
            tipo="Saída",
            natureza="Cancelamento",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "5102": CFOPInfo(
            codigo="5102",
            descricao="Venda de produto industrializado - Devolução",
            tipo="Saída",
            natureza="Devolução",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "5111": CFOPInfo(
            codigo="5111",
            descricao="Venda de produto industrializado - Tributada pelo ICMS",
            tipo="Saída",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "5120": CFOPInfo(
            codigo="5120",
            descricao="Venda para revenda",
            tipo="Saída",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "5200": CFOPInfo(
            codigo="5200",
            descricao="Devolução de compras",
            tipo="Saída",
            natureza="Devolução",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "5300": CFOPInfo(
            codigo="5300",
            descricao="Venda de Ativo Imobilizado",
            tipo="Saída",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=False
        ),
        "5500": CFOPInfo(
            codigo="5500",
            descricao="Venda de Ativo Circulante",
            tipo="Saída",
            natureza="NF",
            icms_aplica=False,
            ipi_aplica=False
        ),
        "5900": CFOPInfo(
            codigo="5900",
            descricao="Outra operação com saída de mercadoria ou serviço",
            tipo="Saída",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=True
        ),
    }

    # CFOP Transferência (6xxx)
    TRANSFERENCIAS = {
        "6100": CFOPInfo(
            codigo="6100",
            descricao="Transferência de produto industrializado",
            tipo="Transferência",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=False
        ),
        "6200": CFOPInfo(
            codigo="6200",
            descricao="Devolução de produto recebido em transferência",
            tipo="Transferência",
            natureza="Devolução",
            icms_aplica=True,
            ipi_aplica=False
        ),
    }

    # CFOP Devoluções (2xxx, 7xxx)
    DEVOLUCOES = {
        "2100": CFOPInfo(
            codigo="2100",
            descricao="Devolução de venda de mercadoria produzida ou industrializada",
            tipo="Devolução",
            natureza="Devolução",
            icms_aplica=True,
            ipi_aplica=True
        ),
        "7100": CFOPInfo(
            codigo="7100",
            descricao="Aquisição de serviço de transporte",
            tipo="Entrada",
            natureza="NF",
            icms_aplica=True,
            ipi_aplica=False
        ),
    }

    @staticmethod
    def buscar(codigo: str) -> Optional[CFOPInfo]:
        """Busca informação de CFOP pelo código"""
        todos = {**CFOP.ENTRADAS, **CFOP.SAIDAS, **CFOP.TRANSFERENCIAS, **CFOP.DEVOLUCOES}
        return todos.get(codigo)

    @staticmethod
    def listar_por_tipo(tipo: str) -> Dict[str, CFOPInfo]:
        """Lista CFOP por tipo (Entrada, Saída, etc)"""
        todos = {**CFOP.ENTRADAS, **CFOP.SAIDAS, **CFOP.TRANSFERENCIAS, **CFOP.DEVOLUCOES}
        return {k: v for k, v in todos.items() if v.tipo == tipo}


# =============== NCM - NOMENCLATURA COMUM DO MERCOSUL ===============

class NCM:
    """
    NCM (Nomenclatura Comum do MERCOSUL)
    Código de 8 dígitos que classifica produtos
    Estrutura: XX.XX.XX.XX (Seção.Capítulo.Posição.Subposição)
    """

    NCMS_COMUNS = {
        # Capítulo 01 - Animais vivos
        "01010000": NCMInfo(
            codigo="01010000",
            descricao="Cavalos, vivos",
            aliquota_icms_padrao=7.0,
            aliquota_ipi=0.0,
            exigibilidade_tributo="Tributo normal"
        ),

        # Capítulo 04 - Leite e lacticínios
        "04011000": NCMInfo(
            codigo="04011000",
            descricao="Leite de vaca fresco",
            aliquota_icms_padrao=12.0,
            aliquota_ipi=0.0,
            exigibilidade_tributo="Tributo normal"
        ),

        # Capítulo 07 - Vegetais
        "07010000": NCMInfo(
            codigo="07010000",
            descricao="Batatas frescas ou refrigeradas",
            aliquota_icms_padrao=12.0,
            aliquota_ipi=0.0,
            exigibilidade_tributo="Tributo normal"
        ),

        # Capítulo 15 - Gorduras e óleos
        "15179090": NCMInfo(
            codigo="15179090",
            descricao="Óleo de soja em bruto",
            aliquota_icms_padrao=7.0,
            aliquota_ipi=0.0,
            exigibilidade_tributo="Tributo normal"
        ),

        # Capítulo 27 - Combustíveis
        "27101100": NCMInfo(
            codigo="27101100",
            descricao="Gasolina comum",
            aliquota_icms_padrao=12.0,
            aliquota_ipi=0.0,
            exigibilidade_tributo="CIDE"
        ),
        "27101950": NCMInfo(
            codigo="27101950",
            descricao="Diesel",
            aliquota_icms_padrao=12.0,
            aliquota_ipi=0.0,
            exigibilidade_tributo="CIDE"
        ),

        # Capítulo 29 - Produtos Químicos Orgânicos
        "29051000": NCMInfo(
            codigo="29051000",
            descricao="Metanol (álcool metílico)",
            aliquota_icms_padrao=12.0,
            aliquota_ipi=0.0,
            exigibilidade_tributo="Tributo normal"
        ),

        # Capítulo 30 - Produtos Farmacêuticos
        "30021000": NCMInfo(
            codigo="30021000",
            descricao="Medicamentos com antibióticos",
            aliquota_icms_padrao=0.0,
            aliquota_ipi=0.0,
            exigibilidade_tributo="Imunidade"
        ),

        # Capítulo 48 - Papel e Papelão
        "48021010": NCMInfo(
            codigo="48021010",
            descricao="Papel de jornal",
            aliquota_icms_padrao=12.0,
            aliquota_ipi=0.0,
            exigibilidade_tributo="Tributo normal"
        ),

        # Capítulo 62 - Vestuário
        "62019000": NCMInfo(
            codigo="62019000",
            descricao="Vestuário de algodão",
            aliquota_icms_padrao=12.0,
            aliquota_ipi=25.0,
            exigibilidade_tributo="Tributo normal"
        ),

        # Capítulo 84 - Máquinas e aparelhos
        "84021000": NCMInfo(
            codigo="84021000",
            descricao="Caldeiras a vapor",
            aliquota_icms_padrao=7.0,
            aliquota_ipi=5.0,
            exigibilidade_tributo="Tributo normal"
        ),
        "84717050": NCMInfo(
            codigo="84717050",
            descricao="Máquinas para processamento de dados",
            aliquota_icms_padrao=0.0,
            aliquota_ipi=0.0,
            exigibilidade_tributo="Diferimento"
        ),

        # Capítulo 85 - Eletricidade e eletrônicos
        "85171100": NCMInfo(
            codigo="85171100",
            descricao="Telefones celulares",
            aliquota_icms_padrao=7.0,
            aliquota_ipi=30.0,
            exigibilidade_tributo="Tributo normal"
        ),
        "85176000": NCMInfo(
            codigo="85176000",
            descricao="Monitores e televisores",
            aliquota_icms_padrao=7.0,
            aliquota_ipi=15.0,
            exigibilidade_tributo="Tributo normal"
        ),

        # Capítulo 87 - Veículos automotores
        "87039000": NCMInfo(
            codigo="87039000",
            descricao="Partes e peças para veículos automotores",
            aliquota_icms_padrao=7.0,
            aliquota_ipi=20.0,
            exigibilidade_tributo="Tributo normal"
        ),

        # Capítulo 90 - Óptica e Precisão
        "90186010": NCMInfo(
            codigo="90186010",
            descricao="Equipamentos de diagnóstico",
            aliquota_icms_padrao=0.0,
            aliquota_ipi=0.0,
            exigibilidade_tributo="Imunidade"
        ),
    }

    @staticmethod
    def buscar(codigo: str) -> Optional[NCMInfo]:
        """Busca informação de NCM pelo código"""
        # Aceita com ou sem pontos (01.23.45.67 ou 01234567)
        codigo_limpo = codigo.replace(".", "")
        return NCM.NCMS_COMUNS.get(codigo_limpo)

    @staticmethod
    def formatar(codigo: str) -> str:
        """Formata NCM para XX.XX.XX.XX"""
        codigo_limpo = codigo.replace(".", "")
        if len(codigo_limpo) == 8:
            return f"{codigo_limpo[0:2]}.{codigo_limpo[2:4]}.{codigo_limpo[4:6]}.{codigo_limpo[6:8]}"
        return codigo

    @staticmethod
    def validar(codigo: str) -> bool:
        """Valida se NCM tem 8 dígitos"""
        codigo_limpo = codigo.replace(".", "")
        return len(codigo_limpo) == 8 and codigo_limpo.isdigit()


# =============== CSOSN - CÓDIGO DE SITUAÇÃO (SIMPLES NACIONAL) ===============

class CSOSN:
    """
    CSOSN (Código de Situação da Operação - Simples Nacional)
    Válido apenas para empresas no regime Simples Nacional
    """

    CODIGOS = {
        "101": CSOSNInfo(
            codigo="101",
            descricao="Tributada pelo Simples Nacional - ICMS normal",
            aplica_icms=True,
            aplica_pis=True,
            aplica_cofins=True,
            credito_icms=False
        ),
        "102": CSOSNInfo(
            codigo="102",
            descricao="Tributada pelo Simples Nacional - ICMS com ST",
            aplica_icms=True,
            aplica_pis=True,
            aplica_cofins=True,
            credito_icms=False
        ),
        "103": CSOSNInfo(
            codigo="103",
            descricao="Tributada pelo Simples Nacional - Regime de substituição tributária",
            aplica_icms=True,
            aplica_pis=True,
            aplica_cofins=True,
            credito_icms=False
        ),
        "201": CSOSNInfo(
            codigo="201",
            descricao="Tributada pelo Simples Nacional - ICMS normal (entrada)",
            aplica_icms=True,
            aplica_pis=True,
            aplica_cofins=True,
            credito_icms=True
        ),
        "202": CSOSNInfo(
            codigo="202",
            descricao="Tributada pelo Simples Nacional - ICMS com ST (entrada)",
            aplica_icms=True,
            aplica_pis=True,
            aplica_cofins=True,
            credito_icms=True
        ),
        "203": CSOSNInfo(
            codigo="203",
            descricao="Tributada pelo Simples Nacional - ST (entrada)",
            aplica_icms=True,
            aplica_pis=True,
            aplica_cofins=True,
            credito_icms=False
        ),
        "300": CSOSNInfo(
            codigo="300",
            descricao="Tributada pelo Simples Nacional - Imune",
            aplica_icms=False,
            aplica_pis=False,
            aplica_cofins=False,
            credito_icms=False
        ),
        "400": CSOSNInfo(
            codigo="400",
            descricao="Não tributada pelo Simples Nacional",
            aplica_icms=False,
            aplica_pis=False,
            aplica_cofins=False,
            credito_icms=False
        ),
        "500": CSOSNInfo(
            codigo="500",
            descricao="Excluída do Simples Nacional",
            aplica_icms=True,
            aplica_pis=True,
            aplica_cofins=True,
            credito_icms=True
        ),
        "900": CSOSNInfo(
            codigo="900",
            descricao="Outras operações",
            aplica_icms=True,
            aplica_pis=True,
            aplica_cofins=True,
            credito_icms=True
        ),
    }

    @staticmethod
    def buscar(codigo: str) -> Optional[CSOSNInfo]:
        """Busca informação de CSOSN pelo código"""
        return CSOSN.CODIGOS.get(str(codigo))

    @staticmethod
    def listar_entradas() -> Dict[str, CSOSNInfo]:
        """Lista apenas CSOSN de entrada (2xx)"""
        return {k: v for k, v in CSOSN.CODIGOS.items() if k.startswith("2")}

    @staticmethod
    def listar_saidas() -> Dict[str, CSOSNInfo]:
        """Lista apenas CSOSN de saída (1xx)"""
        return {k: v for k, v in CSOSN.CODIGOS.items() if k.startswith("1")}


# =============== O-CST - CÓDIGO DE SITUAÇÃO TRIBUTÁRIA (RÉGIMEN NORMAL) ===============

class OCST:
    """
    O-CST (Código de Situação Tributária - Régimen Normal)
    Válido para empresas no Lucro Real / Lucro Presumido
    """

    CODIGOS = {
        # Entrada
        "00": OCSTPInfo(
            codigo="00",
            descricao="Entrada com Crédito",
            aplica_icms=True,
            credito_icms=True,
            substitui_tributaria=False
        ),
        "10": OCSTPInfo(
            codigo="10",
            descricao="Tributada com Substituição Tributária",
            aplica_icms=True,
            credito_icms=False,
            substitui_tributaria=True
        ),
        "20": OCSTPInfo(
            codigo="20",
            descricao="Com redução de base de cálculo",
            aplica_icms=True,
            credito_icms=True,
            substitui_tributaria=False
        ),
        "30": OCSTPInfo(
            codigo="30",
            descricao="Isenta ou não tributada e com ST",
            aplica_icms=False,
            credito_icms=False,
            substitui_tributaria=True
        ),
        "40": OCSTPInfo(
            codigo="40",
            descricao="Isenta",
            aplica_icms=False,
            credito_icms=False,
            substitui_tributaria=False
        ),
        "41": OCSTPInfo(
            codigo="41",
            descricao="Não tributada",
            aplica_icms=False,
            credito_icms=False,
            substitui_tributaria=False
        ),
        "50": OCSTPInfo(
            codigo="50",
            descricao="Suspensão",
            aplica_icms=False,
            credito_icms=False,
            substitui_tributaria=False
        ),
        "60": OCSTPInfo(
            codigo="60",
            descricao="Diferimento",
            aplica_icms=True,
            credito_icms=False,
            substitui_tributaria=False
        ),
        "70": OCSTPInfo(
            codigo="70",
            descricao="Com redução de base - Substituição",
            aplica_icms=True,
            credito_icms=False,
            substitui_tributaria=True
        ),
        "90": OCSTPInfo(
            codigo="90",
            descricao="Outras",
            aplica_icms=True,
            credito_icms=True,
            substitui_tributaria=False
        ),
    }

    @staticmethod
    def buscar(codigo: str) -> Optional[OCSTPInfo]:
        """Busca informação de O-CST pelo código"""
        return OCST.CODIGOS.get(str(codigo))


# =============== ICMS - ALÍQUOTAS POR ESTADO ===============

class ICMS:
    """
    Alíquotas padrão de ICMS por estado
    Atualizado para 2025
    """

    ALIQUOTAS_ESTADOS = {
        "AC": 17.0,  # Acre
        "AL": 17.0,  # Alagoas
        "AP": 18.0,  # Amapá
        "AM": 18.0,  # Amazonas
        "BA": 18.0,  # Bahia
        "CE": 17.0,  # Ceará
        "DF": 18.0,  # Distrito Federal
        "ES": 17.0,  # Espírito Santo
        "GO": 14.0,  # Goiás
        "MA": 18.0,  # Maranhão
        "MT": 14.5,  # Mato Grosso
        "MS": 14.0,  # Mato Grosso do Sul
        "MG": 18.0,  # Minas Gerais
        "PA": 17.0,  # Pará
        "PB": 18.0,  # Paraíba
        "PR": 18.0,  # Paraná
        "PE": 17.0,  # Pernambuco
        "PI": 17.0,  # Piauí
        "RJ": 20.0,  # Rio de Janeiro
        "RN": 17.0,  # Rio Grande do Norte
        "RS": 18.0,  # Rio Grande do Sul
        "RO": 17.5,  # Rondônia
        "RR": 15.0,  # Roraima
        "SC": 17.0,  # Santa Catarina
        "SP": 18.0,  # São Paulo
        "SE": 17.0,  # Sergipe
        "TO": 14.0,  # Tocantins
    }

    # Alíquotas reduzidas para produtos selecionados
    ALIQUOTAS_REDUZIDAS = {
        "alimentos_basicos": 0.0,  # Isento
        "medicamentos": 0.0,  # Isento
        "energia_eletrica": 12.0,  # Reduzida
        "combustivel": 12.0,  # Reduzida
        "agricultura": 12.0,  # Reduzida
    }

    @staticmethod
    def buscar_estado(uf: str) -> Optional[float]:
        """Busca alíquota padrão de ICMS por estado"""
        return ICMS.ALIQUOTAS_ESTADOS.get(uf.upper())

    @staticmethod
    def listar_estados() -> Dict[str, float]:
        """Lista todos os estados com suas alíquotas"""
        return ICMS.ALIQUOTAS_ESTADOS.copy()


# =============== PIS/COFINS ===============

class PISCOFINS:
    """
    Alíquotas de PIS/COFINS
    """

    # Para regime normal
    ALIQUOTAS_NORMAL = {
        "pis": 1.65,
        "cofins": 7.6,
    }

    # Para Simples Nacional (por faixa de faturamento)
    ALIQUOTAS_SIMPLES = {
        # Anexo I - Comércio
        "comercio": {
            "faixa1": (0, 180000, 4.0, 4.0),  # até 180k: PIS 0.0%, COFINS 4.0%
            "faixa2": (180000, 360000, 0.0, 4.0),
            "faixa3": (360000, 540000, 0.0, 4.0),
            "faixa4": (540000, 720000, 0.0, 4.0),
            "faixa5": (720000, 900000, 0.0, 4.0),
            "faixa6": (900000, 1080000, 0.0, 4.0),
            "faixa7": (1080000, 1260000, 0.0, 4.0),
            "faixa8": (1260000, 1440000, 0.0, 4.0),
            "faixa9": (1440000, 1620000, 0.0, 4.0),
        },
    }

    @staticmethod
    def get_aliquota_pis_cofins(regime: str = "normal") -> Dict[str, float]:
        """Retorna alíquotas de PIS/COFINS conforme regime"""
        if regime == "normal":
            return PISCOFINS.ALIQUOTAS_NORMAL
        return {"pis": 0.0, "cofins": 0.0}


# =============== IMPORTAÇÃO/EXPORTAÇÃO ===============

class NaturezaOperacao:
    """
    Natureza das operações fiscais
    """

    NATUREZAS = {
        "01": {
            "descricao": "Venda a consumidor final",
            "icms_aplica": True,
            "ipi_aplica": True,
        },
        "02": {
            "descricao": "Venda para revenda",
            "icms_aplica": True,
            "ipi_aplica": True,
        },
        "03": {
            "descricao": "Venda para industrialização",
            "icms_aplica": True,
            "ipi_aplica": True,
        },
        "04": {
            "descricao": "Devolução",
            "icms_aplica": True,
            "ipi_aplica": True,
        },
        "05": {
            "descricao": "Amostra grátis",
            "icms_aplica": False,
            "ipi_aplica": False,
        },
        "06": {
            "descricao": "Devolução de entrada",
            "icms_aplica": True,
            "ipi_aplica": True,
        },
        "07": {
            "descricao": "Transferência",
            "icms_aplica": True,
            "ipi_aplica": False,
        },
    }

    @staticmethod
    def buscar(codigo: str) -> Optional[Dict[str, Any]]:
        """Busca natureza da operação"""
        return NaturezaOperacao.NATUREZAS.get(str(codigo))


# =============== FUNÇÃO AUXILIAR DE ANÁLISE ===============

def analisar_nf(
    cfop: str,
    ncm: str,
    csosn_ou_cst: str,
    uf_destino: str,
    regime: str = "simples"
) -> Dict[str, Any]:
    """
    Analisa uma operação fiscal e retorna informações consolidadas.
    Garante retorno seguro (sempre um dicionário, nunca None).
    """

    resultado = {
        "status": "OK",
        "cfop_info": None,
        "ncm_info": None,
        "tributo_info": None,
        "aliquota_icms": 0.0,
        "aliquota_ipi": 0.0,
        "aliquota_pis": 0.0,
        "aliquota_cofins": 0.0,
        "avisos": [],
    }

    try:
        # CFOP
        cfop_info = CFOP.buscar(cfop)
        if cfop_info:
            resultado["cfop_info"] = {
                "codigo": cfop_info.codigo,
                "descricao": cfop_info.descricao,
                "icms_aplica": cfop_info.icms_aplica,
                "ipi_aplica": cfop_info.ipi_aplica,
            }
        else:
            resultado["avisos"].append(f"CFOP {cfop} não encontrado")

        # NCM
        ncm_info = NCM.buscar(ncm)
        if ncm_info:
            resultado["ncm_info"] = {
                "codigo": NCM.formatar(ncm),
                "descricao": ncm_info.descricao,
                "aliquota_icms": ncm_info.aliquota_icms_padrao,
                "aliquota_ipi": ncm_info.aliquota_ipi,
            }
            resultado["aliquota_icms"] = ncm_info.aliquota_icms_padrao
            resultado["aliquota_ipi"] = ncm_info.aliquota_ipi
        else:
            resultado["avisos"].append(f"NCM {ncm} não encontrado na base")

        # Regime tributário
        if regime == "simples":
            csosn_info = CSOSN.buscar(csosn_ou_cst)
            if csosn_info:
                resultado["tributo_info"] = {
                    "codigo": csosn_info.codigo,
                    "descricao": csosn_info.descricao,
                    "aplica_icms": csosn_info.aplica_icms,
                    "credito_icms": csosn_info.credito_icms,
                }
                if not csosn_info.aplica_icms:
                    resultado["aliquota_icms"] = 0.0
        else:
            ocst_info = OCST.buscar(csosn_ou_cst)
            if ocst_info:
                resultado["tributo_info"] = {
                    "codigo": ocst_info.codigo,
                    "descricao": ocst_info.descricao,
                    "aplica_icms": ocst_info.aplica_icms,
                    "credito_icms": ocst_info.credito_icms,
                }
                if not ocst_info.aplica_icms:
                    resultado["aliquota_icms"] = 0.0

        # ICMS por Estado
        aliq_estado = ICMS.buscar_estado(uf_destino)
        if aliq_estado and resultado["aliquota_icms"] > 0:
            resultado["aliquota_icms"] = min(resultado["aliquota_icms"], aliq_estado)

        # PIS/COFINS
        piscofins = PISCOFINS.get_aliquota_pis_cofins(regime)
        resultado["aliquota_pis"] = piscofins.get("pis", 0.0)
        resultado["aliquota_cofins"] = piscofins.get("cofins", 0.0)

        return resultado

    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] Falha em analisar_nf (CFOP={cfop}, NCM={ncm}): {e}")
        return {"status": "ERRO", "avisos": [str(e)]}


# =============== EXEMPLOS DE USO ===============

if __name__ == "__main__":
    # Exemplo 1: Buscar CFOP
    print("=== CFOP ===")
    cfop_info = CFOP.buscar("5100")
    print(f"CFOP 5100: {cfop_info.descricao if cfop_info else 'Não encontrado'}")

    # Exemplo 2: Buscar NCM
    print("\n=== NCM ===")
    ncm_info = NCM.buscar("27101100")
    print(f"NCM 27101100: {ncm_info.descricao if ncm_info else 'Não encontrado'}")

    # Exemplo 3: Buscar CSOSN
    print("\n=== CSOSN ===")
    csosn_info = CSOSN.buscar("101")
    print(f"CSOSN 101: {csosn_info.descricao if csosn_info else 'Não encontrado'}")

    # Exemplo 4: Analisar operação
    print("\n=== ANÁLISE COMPLETA ===")
    analise = analisar_nf(
        cfop="5100",
        ncm="62019000",
        csosn_ou_cst="101",
        uf_destino="SP",
        regime="simples"
    )
    print(f"Análise: {analise['status']}")
    print(f"CFOP: {analise['cfop_info']['descricao']}")
    print(f"NCM: {analise['ncm_info']['descricao']}")
    print(f"ICMS: {analise['aliquota_icms']}%")
    print(f"IPI: {analise['aliquota_ipi']}%")
