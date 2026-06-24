"""
Pydantic models para la extracción de documentos fiscales vía Gemini.
Estos modelos son la fuente de verdad del schema — extraction-schema.json
se genera/valida a partir de ellos.

Umbrales de confianza configurables en config.py:
  CONFIANZA_MINIMA_PROCESADO = 0.6   → por debajo → revision_manual
  CONFIANZA_CAMPO_BAJA       = 0.5   → campo marcado como dudoso
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ── Enumeraciones ────────────────────────────────────────────────────────────

class TipoDocumento(str, Enum):
    FACTURA             = "factura"
    TICKET_SIMPLIFICADO = "ticket_simplificado"


class EstadoCampo(str, Enum):
    PRESENTE  = "presente"
    ILEGIBLE  = "ilegible"
    AUSENTE   = "ausente"


class TipoIVA(float, Enum):
    SUPERREDUCIDO = 0
    REDUCIDO_4    = 4
    REDUCIDO_10   = 10
    GENERAL       = 21


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
    nombre:           Optional[str]   = None
    nombre_confianza: float           = Field(0.0, ge=0.0, le=1.0)
    nif:              Optional[str]   = None
    nif_confianza:    float           = Field(0.0, ge=0.0, le=1.0)
    nif_estado:       EstadoCampo     = EstadoCampo.AUSENTE
    direccion:        Optional[str]   = None


class GrupoIVA(BaseModel):
    """Un tramo de IVA dentro de un documento (puede haber varios por factura)."""
    tipo_iva:       TipoIVA
    base_imponible: Optional[float] = None
    cuota_iva:      Optional[float] = None
    confianza:      float           = Field(0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def coherencia_aritmetica(self) -> "GrupoIVA":
        """Verifica que base * tipo_iva% ≈ cuota_iva (tolerancia 0.02€)."""
        if self.base_imponible is not None and self.cuota_iva is not None:
            esperado = round(self.base_imponible * self.tipo_iva / 100, 2)
            if abs(esperado - self.cuota_iva) > 0.02:
                # No lanzar excepción — bajar la confianza para que el backend decida
                object.__setattr__(self, "confianza", min(self.confianza, 0.4))
        return self


class Cabecera(BaseModel):
    """Datos de cabecera del documento extraídos por Gemini."""
    emisor:   ParteDocumento
    receptor: Optional[ParteDocumento] = None  # Ausente en tickets simplificados

    numero_factura:           Optional[str]  = None
    numero_factura_confianza: float          = Field(0.0, ge=0.0, le=1.0)
    numero_factura_estado:    EstadoCampo    = EstadoCampo.AUSENTE

    fecha_emision:           Optional[str]  = None  # ISO 8601: YYYY-MM-DD
    fecha_emision_confianza: float          = Field(0.0, ge=0.0, le=1.0)
    fecha_emision_estado:    EstadoCampo    = EstadoCampo.AUSENTE

    concepto_general:           Optional[str]  = None
    concepto_general_confianza: float          = Field(0.0, ge=0.0, le=1.0)

    retencion_irpf_porcentaje: Optional[float] = None  # ej: 15.0, 7.0, 2.0
    retencion_irpf_cuota:      Optional[float] = None
    retencion_irpf_confianza:  float           = Field(0.0, ge=0.0, le=1.0)

    total_factura:           Optional[float] = None
    total_factura_confianza: float           = Field(0.0, ge=0.0, le=1.0)
    total_factura_estado:    EstadoCampo     = EstadoCampo.AUSENTE

    categoria_sugerida:           Optional[CategoriaGasto] = None
    categoria_sugerida_confianza: float                    = Field(0.0, ge=0.0, le=1.0)


# ── Modelo raíz ──────────────────────────────────────────────────────────────

class ExtraccionDocumento(BaseModel):
    """
    Modelo raíz de la respuesta de extracción de Gemini.
    El servicio Python valida la respuesta del modelo contra este schema.
    """
    tipo_documento:    TipoDocumento
    confianza_global:  float      = Field(..., ge=0.0, le=1.0)
    cabecera:          Cabecera
    grupos_iva:        list[GrupoIVA] = Field(..., min_length=1)
    notas_extraccion:  Optional[str]  = None

    @model_validator(mode="after")
    def coherencia_total_vs_grupos(self) -> "ExtraccionDocumento":
        """
        Verifica que la suma de cuotas_iva de los grupos + bases_imponibles
        sea coherente con el total_factura de la cabecera (tolerancia 0.05€).
        Si no coincide, reduce la confianza_global.
        """
        total = self.cabecera.total_factura
        if total is None:
            return self

        suma_bases  = sum(g.base_imponible or 0 for g in self.grupos_iva)
        suma_cuotas = sum(g.cuota_iva      or 0 for g in self.grupos_iva)
        retencion   = self.cabecera.retencion_irpf_cuota or 0
        calculado   = round(suma_bases + suma_cuotas - retencion, 2)

        if abs(calculado - total) > 0.05:
            nueva_confianza = min(self.confianza_global, 0.45)
            object.__setattr__(self, "confianza_global", nueva_confianza)

        return self

    def requiere_revision(self, umbral: float = 0.6) -> bool:
        """True si la confianza global está por debajo del umbral configurado."""
        return self.confianza_global < umbral
