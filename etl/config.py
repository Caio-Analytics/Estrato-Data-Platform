"""Paths, dataset specs, and reference tables shared across the pipeline.

The project ingests two ANM/RAL datasets that share a lot of shape (same
UF/Classe/Substância dimensions, same "Ano base" grain) but differ in one
structural way that matters for how they're aggregated: Produção Bruta
reports every quantity in tonnes (implicit, baked into the column name),
while Produção Beneficiada reports each quantity in whatever unit the
product is actually sold in (t / kg / ct — a `Unidade de Medida - *` column
per quantity). `DatasetSpec.quantities_uniform_unit` records that
difference once, here, so Silver knows which quantity columns are safe to
sum across rows and which are not (see the comment in `silver.py`).
"""

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RECON_DIR = DATA_DIR / "recon"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"

OUTPUT_DIR = PROJECT_ROOT / "output"
DASHBOARD_HTML = OUTPUT_DIR / "dashboard.html"

DOCS_DIR = PROJECT_ROOT / "docs"
QUALITY_REPORT_MD = DOCS_DIR / "relatorio_qualidade_producao_bruta.md"

# ---------------------------------------------------------------------------
# Source format — confirmed against both raw files
# ---------------------------------------------------------------------------

SOURCE_ENCODING = "windows-1252"
SOURCE_SEPARATOR = ","
NULL_SENTINEL_UNIDADE = "-"  # "Unidade de Medida - Contido" uses this for "n/a"

# ---------------------------------------------------------------------------
# UF -> Região lookup (IBGE division)
# ---------------------------------------------------------------------------

UF_REGIAO = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte",
    "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste",
    "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}
VALID_UFS = set(UF_REGIAO.keys())

# ---------------------------------------------------------------------------
# Dataset specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetSpec:
    key: str  # short slug used for filenames: "producao_bruta"
    label: str  # display name: "Produção Bruta"
    raw_csv: Path
    label_transformacao: str  # what this dataset calls the "used on-site" destination

    col_ano: str = "Ano base"
    col_uf: str = "UF"
    col_classe: str = "Classe Substância"
    col_substancia: str = "Substância Mineral"

    col_qtd_producao: str = ""
    col_qtd_contido: str = "Quantidade Contido"
    col_unidade_contido: str = "Unidade de Medida - Contido"
    col_indicacao_contido: str = "Indicação Contido"

    col_qtd_venda: str = ""
    col_valor_venda: str = "Valor Venda (R$)"
    col_qtd_transformacao: str = ""
    col_valor_transformacao: str = ""
    col_qtd_transferencia: str = ""
    col_valor_transferencia: str = ""

    # unit columns — populated only for datasets where quantities aren't
    # implicitly tonnes (Beneficiada); empty tuple for Bruta.
    unit_columns: tuple = ()

    # True only when every physical-quantity column in this dataset is in
    # the same unit (tonnes) for every row, so summing them across rows is
    # numerically meaningful. False means: aggregate by R$ (unit-agnostic),
    # never by raw quantity, unless grouped by matching unit first.
    quantities_uniform_unit: bool = True

    raw_columns: tuple = field(default_factory=tuple)
    br_decimal_columns: tuple = field(default_factory=tuple)
    categorical_columns: tuple = field(default_factory=tuple)

    @property
    def bronze_parquet(self) -> Path:
        return BRONZE_DIR / f"{self.key}.parquet"

    @property
    def silver_parquet(self) -> Path:
        return SILVER_DIR / f"{self.key}.parquet"


_BRUTA_COL_QTD_PRODUCAO = "Quantidade Produção - Minério ROM (t)"
_BRUTA_COL_QTD_VENDA = "Quantidade Venda (t)"
_BRUTA_COL_QTD_TRANSFORMACAO = "Quantidade Transformação / Consumo / Utilização (t)"
_BRUTA_COL_VALOR_TRANSFORMACAO = "Valor Transformação / Consumo / Utilização nesta mina (R$)"
_BRUTA_COL_QTD_TRANSFERENCIA = "Quantidade Transferência para Transformação / Utilização / Consumo (t)"
_BRUTA_COL_VALOR_TRANSFERENCIA = "Valor Transferência para Transformação / Utilização / Consumo (R$)"

BRUTA = DatasetSpec(
    key="producao_bruta",
    label="Produção Bruta",
    raw_csv=RAW_DIR / "Producao_Bruta.csv",
    label_transformacao="Transformação/consumo (na mina)",
    col_qtd_producao=_BRUTA_COL_QTD_PRODUCAO,
    col_qtd_venda=_BRUTA_COL_QTD_VENDA,
    col_qtd_transformacao=_BRUTA_COL_QTD_TRANSFORMACAO,
    col_valor_transformacao=_BRUTA_COL_VALOR_TRANSFORMACAO,
    col_qtd_transferencia=_BRUTA_COL_QTD_TRANSFERENCIA,
    col_valor_transferencia=_BRUTA_COL_VALOR_TRANSFERENCIA,
    quantities_uniform_unit=True,
    raw_columns=(
        "Ano base", "UF", "Classe Substância", "Substância Mineral",
        _BRUTA_COL_QTD_PRODUCAO, "Quantidade Contido", "Unidade de Medida - Contido",
        "Indicação Contido", _BRUTA_COL_QTD_VENDA, "Valor Venda (R$)",
        _BRUTA_COL_QTD_TRANSFORMACAO, _BRUTA_COL_VALOR_TRANSFORMACAO,
        _BRUTA_COL_QTD_TRANSFERENCIA, _BRUTA_COL_VALOR_TRANSFERENCIA,
    ),
    br_decimal_columns=(
        _BRUTA_COL_QTD_PRODUCAO, "Quantidade Contido", _BRUTA_COL_QTD_VENDA,
        "Valor Venda (R$)", _BRUTA_COL_QTD_TRANSFORMACAO, _BRUTA_COL_VALOR_TRANSFORMACAO,
        _BRUTA_COL_QTD_TRANSFERENCIA, _BRUTA_COL_VALOR_TRANSFERENCIA,
    ),
    categorical_columns=(
        "UF", "Classe Substância", "Substância Mineral",
        "Unidade de Medida - Contido", "Indicação Contido",
    ),
)

_BEN_COL_QTD_PRODUCAO = "Quantidade Produção"
_BEN_COL_UNIDADE_PRODUCAO = "Unidade de Medida - Produção"
_BEN_COL_QTD_VENDA = "Quantidade Venda"
_BEN_COL_UNIDADE_VENDA = "Unidade de Medida - Venda"
_BEN_COL_QTD_TRANSFORMACAO = "Quantidade Consumo/Utilização na Usina"
_BEN_COL_UNIDADE_TRANSFORMACAO = "Unidade de Medida - Consumo/Utilização na Usina"
_BEN_COL_VALOR_TRANSFORMACAO = "Valor Consumo / Utilização na Usina (R$)"
_BEN_COL_QTD_TRANSFERENCIA = "Quantidade Transferência para Transformação / Utilização / Consumo"
_BEN_COL_UNIDADE_TRANSFERENCIA = "Unidade de Medida - Transferência para Transformação / Utilização / Consumo"
_BEN_COL_VALOR_TRANSFERENCIA = "Valor Transferência para Transformação / Utilização / Consumo (R$)"

BENEFICIADA = DatasetSpec(
    key="producao_beneficiada",
    label="Produção Beneficiada",
    raw_csv=RAW_DIR / "Producao_Beneficiada.csv",
    label_transformacao="Consumo/utilização na usina",
    col_qtd_producao=_BEN_COL_QTD_PRODUCAO,
    col_qtd_venda=_BEN_COL_QTD_VENDA,
    col_qtd_transformacao=_BEN_COL_QTD_TRANSFORMACAO,
    col_valor_transformacao=_BEN_COL_VALOR_TRANSFORMACAO,
    col_qtd_transferencia=_BEN_COL_QTD_TRANSFERENCIA,
    col_valor_transferencia=_BEN_COL_VALOR_TRANSFERENCIA,
    unit_columns=(
        _BEN_COL_UNIDADE_PRODUCAO, _BEN_COL_UNIDADE_VENDA,
        _BEN_COL_UNIDADE_TRANSFORMACAO, _BEN_COL_UNIDADE_TRANSFERENCIA,
    ),
    quantities_uniform_unit=False,
    raw_columns=(
        "Ano base", "UF", "Classe Substância", "Substância Mineral",
        _BEN_COL_QTD_PRODUCAO, _BEN_COL_UNIDADE_PRODUCAO,
        "Quantidade Contido", "Unidade de Medida - Contido", "Indicação Contido",
        _BEN_COL_QTD_VENDA, _BEN_COL_UNIDADE_VENDA, "Valor Venda (R$)",
        _BEN_COL_QTD_TRANSFORMACAO, _BEN_COL_UNIDADE_TRANSFORMACAO, _BEN_COL_VALOR_TRANSFORMACAO,
        _BEN_COL_QTD_TRANSFERENCIA, _BEN_COL_UNIDADE_TRANSFERENCIA, _BEN_COL_VALOR_TRANSFERENCIA,
    ),
    br_decimal_columns=(
        _BEN_COL_QTD_PRODUCAO, "Quantidade Contido", _BEN_COL_QTD_VENDA, "Valor Venda (R$)",
        _BEN_COL_QTD_TRANSFORMACAO, _BEN_COL_VALOR_TRANSFORMACAO,
        _BEN_COL_QTD_TRANSFERENCIA, _BEN_COL_VALOR_TRANSFERENCIA,
    ),
    categorical_columns=(
        "UF", "Classe Substância", "Substância Mineral",
        "Unidade de Medida - Contido", "Indicação Contido",
        _BEN_COL_UNIDADE_PRODUCAO, _BEN_COL_UNIDADE_VENDA,
        _BEN_COL_UNIDADE_TRANSFORMACAO, _BEN_COL_UNIDADE_TRANSFERENCIA,
    ),
)

DATASETS = {"bruta": BRUTA, "beneficiada": BENEFICIADA}

# Backward-compatible module-level aliases (kept so scripts that only ever
# cared about the Bruta column names don't need a spec threaded through).
COL_ANO = BRUTA.col_ano
COL_UF = BRUTA.col_uf
COL_CLASSE = BRUTA.col_classe
COL_SUBSTANCIA = BRUTA.col_substancia
