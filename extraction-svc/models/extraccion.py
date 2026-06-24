"""
Pydantic models para la extracción de documentos fiscales vía Gemini.
Estos modelos son la fuente de verdad del schema — extraction-schema.json
se genera/valida a partir de ellos.

Umbrales de confianza configurables en config.py:
  CONFIANZA_MINIMA_PROCESADO = 0.6   → por debajo → revision_manual
  CONFIANZA_CAMPO_BAJA       = 0.5   → campo marcado como dudoso

Tipos de documento soportados:
  - factura: factura completa estándar española
  - ticket_simplificado: sin NIF receptor ni número de factura
  - factura_rectificativa: abono o corrección; importes pueden ser negativos
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ── Enumeraciones ────────────────────────────────────────────────────────────

class TipoDocumento(str, Enum):
    FACTURA              = "factura"
    TICKET_SIMPLIFICADO  = "ticket_simplificado"
    FACTURA_RECTIFICATIVA = "factura_rectificativa"


class EstadoCampo(str, Enum):
    PRESENTE  = "presente"
    ILEGIBLE  = "ilegible"
    AUSENTE   = "ausente"


class TipoIVA(float, Enum):
    """
    Tipos de IVA vigentes en España.
    El 0% cubre tanto operaciones exentas como intracomunitarias
    (el backend distingue el motivo por pais_codigo del emisor).
    """
    EXENTO_O_INTRACOMUNITARIO = 0
    SUPERREDUCIDO             = 4
    REDUCIDO                  = 10
    GENERAL                   = 21


class Moneda(str, Enum):
    """
    Monedas más habituales en facturas recibidas por autónomos españoles.
    Se puede extender sin romper el schema — el backend convierte a EUR
    para los cálculos fiscales si moneda != EUR.
    """
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"
    CHF = "CHF"
    JPY = "JPY"
    CAD = "CAD"
    AUD = "AUD"
    SEK = "SEK"
    NOK = "NOK"
    DKK = "DKK"


class CategoriaGasto(str, Enum):
    SOFTWARE_SUSCRIPCIONES  = "software_suscripciones"
    MATERIAL_OFICINA        = "material_oficina"
    DIETAS_RESTAURACION     = "dietas_restauracion"
    VIAJES_TRANSPORTE       = "viajes_transporte"
    FORMACION               = "formacion"
    VEHICULOS               = "vehiculos"
    SUMINISTROS_HOGAR       = "suministros_hogar"
    SUMINISTROS_OFICINA     = "suministros_oficina"
    SEGUROS                 = "seguros"
    SERVICIOS_PROFESIONALES = "servicios_profesionales"
    PUBLICIDAD_MARKETING    = "publicidad_marketing"
    ALQUILER                = "alquiler"
    CUOTA_AUTONOMO_RETA     = "cuota_autonomo_reta"
    OTROS                   = "otros"


# ── Submodelos de cabecera ───────────────────────────────────────────────────

class ParteDocumento(BaseModel):
    """Datos de emisor o receptor del documento."""
    nombre:           Optional[str]  = None
    nombre_confianza: float          = Field(0.0, ge=0.0, le=1.0)
    nif:              Optional[str]  = None
    nif_confianza:    float          = Field(0.0, ge=0.0, le=1.0)
    nif_estado:       EstadoCampo    = EstadoCampo.AUSENTE
    direccion:        Optional[str]  = None
    pais_codigo:      Optional[str]  = Field(
        None,
        description=(
            "Código ISO 3166-1 alpha-2 del país del emisor (ES, DE, FR, US…). "
            "Permite al backend detectar operaciones intracomunitarias (IVA 0% + "
            "número de operador intracomunitario) o extracomunitarias."
        ),
        pattern=r"^[A-Z]{2}$",
    )


class GrupoIVA(BaseModel):
    """
    Un tramo de IVA dentro de un documento.
    Puede haber varios por factura (ej: líneas al 10% y al 21%).
    Los importes pueden ser negativos en facturas rectificativas (abonos).

    Recargo de Equivalencia (RE):
    Aplica cuando el receptor tributa en RE (comercio minorista).
    Los porcentajes vinculados al tipo de IVA son:
      IVA 21% → RE 5,2%
      IVA 10% → RE 1,4%
      IVA 4%  → RE 0,5%
      IVA 0%  → RE 0%
    """
    tipo_iva:       TipoIVA
    base_imponible: Optional[float] = None   # Negativo en rectificativas
    cuota_iva:      Optional[float] = None   # Negativo en rectificativas
    confianza:      float           = Field(0.0, ge=0.0, le=1.0)

    # Recargo de Equivalencia (opcional)
    recargo_equivalencia_porcentaje: Optional[float] = Field(
        None,
        description="Porcentaje de RE si aplica. Null si no tributa en RE.",
    )
    recargo_equivalencia_cuota: Optional[float] = Field(
        None,
        description="Importe del RE en la moneda del documento. Negativo en rectificativas.",
    )
    recargo_equivalencia_confianza: float = Field(0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def coherencia_aritmetica(self) -> "GrupoIVA":
        """
        Verifica que base * tipo_iva% ≈ cuota_iva (tolerancia 0.02€).
        Funciona tanto con importes positivos (facturas) como negativos (rectificativas).
        Si no cuadra → baja la confianza del grupo a ≤ 0.4.
        """
        if self.base_imponible is not None and self.cuota_iva is not None:
            esperado = round(self.base_imponible * self.tipo_iva / 100, 2)
            if abs(esperado - self.cuota_iva) > 0.02:
                object.__setattr__(self, "confianza", min(self.confianza, 0.4))
        return self

    @model_validator(mode="after")
    def coherencia_recargo_equivalencia(self) -> "GrupoIVA":
        """
        Si hay recargo_equivalencia_cuota, verifica que
        base * RE% ≈ cuota_RE (tolerancia 0.02€).
        """
        if (
            self.base_imponible is not None
            and self.recargo_equivalencia_porcentaje is not None
            and self.recargo_equivalencia_cuota is not None
        ):
            esperado_re = round(
                self.base_imponible * self.recargo_equivalencia_porcentaje / 100, 2
            )
            if abs(esperado_re - self.recargo_equivalencia_cuota) > 0.02:
                object.__setattr__(
                    self,
                    "recargo_equivalencia_confianza",
                    min(self.recargo_equivalencia_confianza, 0.4),
                )
        return self


class Cabecera(BaseModel):
    """Datos de cabecera del documento extraídos por Gemini."""
    emisor:   ParteDocumento
    receptor: Optional[ParteDocumento] = None  # Ausente en tickets simplificados

    numero_factura:           Optional[str]  = None
    numero_factura_confianza: float          = Field(0.0, ge=0.0, le=1.0)
    numero_factura_estado:    EstadoCampo    = EstadoCampo.AUSENTE

    numero_factura_original: Optional[str] = Field(
        None,
        description=(
            "Solo para factura_rectificativa: número de la factura original "
            "que se corrige o anula. Necesario para el Modelo 303."
        ),
    )

    fecha_emision:           Optional[str]  = None  # ISO 8601: YYYY-MM-DD
    fecha_emision_confianza: float          = Field(0.0, ge=0.0, le=1.0)
    fecha_emision_estado:    EstadoCampo    = EstadoCampo.AUSENTE

    moneda:           Moneda = Field(
        Moneda.EUR,
        description=(
            "Moneda del documento (ISO 4217). Si no se menciona en el documento, asumir EUR. "
            "El backend convierte a EUR para los cálculos fiscales cuando moneda != EUR."
        ),
    )
    moneda_confianza: float = Field(0.0, ge=0.0, le=1.0)

    concepto_general:           Optional[str]  = None
    concepto_general_confianza: float          = Field(0.0, ge=0.0, le=1.0)

    retencion_irpf_porcentaje: Optional[float] = Field(
        None,
        description=(
            "Porcentaje de retención IRPF tal como aparece en el documento, sin restricción "
            "de rango. Ejemplos habituales: 15% (profesionales), 7% (inicio actividad), "
            "19% (alquiler de local, Modelo 115), 2% (actividades agrícolas). "
            "El backend clasifica el tipo de retención por contexto."
        ),
    )
    retencion_irpf_cuota: Optional[float] = Field(
        None,
        description="Importe de la retención en la moneda del documento. Negativo en rectificativas.",
    )
    retencion_irpf_confianza: float = Field(0.0, ge=0.0, le=1.0)

    total_factura: Optional[float] = Field(
        None,
        description=(
            "Importe total del documento en la moneda indicada. "
            "Negativo en facturas rectificativas (abonos)."
        ),
    )
    total_factura_confianza: float       = Field(0.0, ge=0.0, le=1.0)
    total_factura_estado:    EstadoCampo = EstadoCampo.AUSENTE

    categoria_sugerida:           Optional[CategoriaGasto] = None
    categoria_sugerida_confianza: float                    = Field(0.0, ge=0.0, le=1.0)


# ── Modelo raíz ──────────────────────────────────────────────────────────────

class ExtraccionDocumento(BaseModel):
    """
    Modelo raíz de la respuesta de extracción de Gemini.
    El servicio Python valida la respuesta del modelo contra este schema.
    """
    tipo_documento:   TipoDocumento
    confianza_global: float          = Field(..., ge=0.0, le=1.0)
    cabecera:         Cabecera
    grupos_iva:       list[GrupoIVA] = Field(..., min_length=1)
    notas_extraccion: Optional[str]  = None

    @model_validator(mode="after")
    def coherencia_total_vs_grupos(self) -> "ExtraccionDocumento":
        """
        Verifica que:
          sum(base) + sum(cuota_iva) + sum(cuota_RE) - retencion ≈ total_factura

        Funciona con valores positivos (facturas) y negativos (rectificativas).
        Tolerancia: 0.05€ para cubrir redondeos en facturas multi-línea.
        Si no coincide → reduce confianza_global a ≤ 0.45.
        """
        total = self.cabecera.total_factura
        if total is None:
            return self

        suma_bases    = sum(g.base_imponible          or 0 for g in self.grupos_iva)
        suma_cuotas   = sum(g.cuota_iva               or 0 for g in self.grupos_iva)
        suma_re       = sum(g.recargo_equivalencia_cuota or 0 for g in self.grupos_iva)
        retencion     = self.cabecera.retencion_irpf_cuota or 0
        calculado     = round(suma_bases + suma_cuotas + suma_re - retencion, 2)

        if abs(calculado - total) > 0.05:
            nueva_confianza = min(self.confianza_global, 0.45)
            object.__setattr__(self, "confianza_global", nueva_confianza)

        return self

    @model_validator(mode="after")
    def moneda_no_eur_baja_confianza(self) -> "ExtraccionDocumento":
        """
        Si la moneda no es EUR, marcar confianza_global con un tope de 0.5
        para forzar revisión manual hasta que el backend implemente conversión de divisas.
        """
        if self.cabecera.moneda != Moneda.EUR:
            nueva_confianza = min(self.confianza_global, 0.5)
            object.__setattr__(self, "confianza_global", nueva_confianza)
        return self

    def requiere_revision(self, umbral: float = 0.6) -> bool:
        """True si la confianza global está por debajo del umbral configurado."""
        return self.confianza_global < umbral

    def es_rectificativa(self) -> bool:
        """Atajo para que el backend sepa si debe restar IVA en el Modelo 303."""
        return self.tipo_documento == TipoDocumento.FACTURA_RECTIFICATIVA

    def tiene_recargo_equivalencia(self) -> bool:
        """True si algún grupo de IVA incluye Recargo de Equivalencia."""
        return any(g.recargo_equivalencia_cuota is not None for g in self.grupos_iva)
