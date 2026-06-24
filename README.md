# Taxon — FacturaIA

Sistema para que autónomos en España suban fotos de sus facturas y otros documentos fiscales. El sistema extrae, clasifica y organiza la información para preparar declaraciones de la renta y modelos trimestrales (IVA, IRPF), generando un borrador listo para revisar, exportar o enviar a gestoría.

> Las decisiones de diseño de la arquitectura están cerradas. Este documento recoge qué hay que construir y cómo.

> **Estado:** MVP de verano. No presenta declaraciones ante la AEAT — genera borradores y exportaciones para revisión humana.

---

## Índice

- [Qué hay que construir](#qué-hay-que-construir)
- [Decisiones de arquitectura](#decisiones-de-arquitectura)
- [Stack fijado](#stack-fijado)
- [Modelo de datos](#modelo-de-datos)
- [Modelo de negocio](#modelo-de-negocio)
- [Roadmap del MVP](#roadmap-del-mvp)
- [Consideraciones legales y de seguridad](#consideraciones-legales-y-de-seguridad)
- [Estructura del repositorio](#estructura-del-repositorio)

---

## Qué hay que construir

### Entrada del sistema
- Facturas emitidas (ingresos)
- Facturas recibidas (gastos deducibles)
- Tickets/recibos simplificados (dietas, parking, suministros, etc.)
- Justificantes de gastos recurrentes (RETA, seguros, alquiler, gestoría, suministros hogar con % deducción)

### Campos a extraer por documento

| Campo | Descripción |
|---|---|
| `nif_emisor` / `nif_receptor` | NIF/CIF de ambas partes |
| `fecha_emision` | Fecha de la factura |
| `numero_factura` | Para detección de duplicados |
| `base_imponible` | Importe antes de impuestos |
| `tipo_iva` | 0% / 4% / 10% / 21% (puede haber múltiples por factura) |
| `cuota_iva` | Importe de IVA |
| `retencion_irpf` | Si aplica |
| `total_factura` | Importe total |
| `concepto` | Descripción del servicio/producto |

### Clasificación automática requerida
- Emitida vs. recibida
- Categoría de gasto (suministros, material, software, dietas, viajes, formación…)
- IVA deducible vs. no deducible (con % parcial en casos como vehículos)
- Trimestre fiscal correspondiente
- Detección de duplicados

### Validaciones fiscales
- Formato NIF/CIF válido
- Coherencia aritmética: `base_imponible + cuota_iva = total_factura`
- Avisos sobre categorías con mayor escrutinio (dietas, restauración, vehículos)
- Acumulados trimestrales para los modelos 130 (IRPF) y 303 (IVA)

### Outputs del sistema
- Dashboard por trimestre: ingresos, gastos, IVA, retenciones, documentos pendientes de revisión
- Borrador de modelos 130 y 303 con los acumulados del periodo
- Exportación para gestoría (Excel/PDF)
- Bandeja de revisión manual para documentos con baja confianza de extracción

---

## Decisiones de arquitectura

### Pipeline de extracción — flujo de mensajes

- **Java → Python:** mensaje en cola RabbitMQ ("documento pendiente de procesar").
- **Python → Java:** callback REST — el servicio Python hace un `POST` al backend Java con el resultado estructurado cuando termina.
- **Fallback de extracción:** si Gemini falla (timeout, error 429, campos vacíos) o la validación aritmética no pasa → se reintenta con Tesseract OCR. Si Tesseract tampoco produce un resultado de confianza → el documento se marca para **revisión manual** en el dashboard. No hay reintentos automáticos hacia Gemini en el MVP.
- **Notificación al frontend:** el backend Java mantiene el estado del documento en base de datos; el frontend hace **polling** al endpoint de estado del documento mientras está pendiente.

### Modelo de datos — decisiones cerradas

- **`LineaFactura[]`:** las facturas tienen líneas individuales, cada una con su propia `base_imponible`, `tipo_iva` y `cuota_iva`. Los campos de totales en `Factura` son sumarios calculados.
- **`PeriodoFiscal`:** tabla persistida. Se invalida y recalcula únicamente el trimestre afectado cuando el usuario modifica o corrige una factura.
- **`CorreccionCampo`:** entidad incluida desde el MVP. Registra campo a campo el valor original devuelto por la IA vs. el valor corregido por el usuario, junto con la referencia al documento. Es el dato de entrenamiento futuro.

### Clasificación y deducibilidad

- **Deducibilidad parcial (vehículos 50%, hogar %):** el sistema aplica automáticamente el porcentaje estándar según la categoría detectada. El usuario puede modificarlo en la vista de detalle del documento.
- **Catálogo de categorías:** tabla en base de datos (`CategoriaGasto`) con sus porcentajes de deducibilidad por defecto. Permite añadir categorías sin tocar código.
- **Retenciones especiales** (2% agrícola, 19%, intracomunitario sin retención): el campo `retencion_irpf` acepta cualquier porcentaje extraído. Los casos fuera del rango habitual (no 7%, no 15%) generan un aviso en la bandeja de revisión.

### Seguridad entre servicios

- El servicio Python se autentica ante el backend Java usando un **JWT de servicio** firmado con el mismo secret que los tokens de usuario, con claim `role: service`. El backend valida el token en el endpoint de callback antes de persistir el resultado.

### Frontend — captura móvil

- La aplicación se construye como **PWA instalable**, con acceso a cámara nativa del dispositivo.
- El preprocesado de imagen (deskew, contraste) se realiza **en servidor** con OpenCV. El cliente sube la imagen original.

---

## Stack fijado

| Capa | Tecnología |
|---|---|
| Backend principal | Java + Spring Boot |
| Servicio de extracción | Python |
| IA multimodal | Gemini Flash / Flash-Lite (Google AI Studio) |
| OCR de fallback | Tesseract (local) |
| Preprocesado de imagen | OpenCV |
| Base de datos | PostgreSQL |
| Cola de mensajes | RabbitMQ |
| Frontend | React |
| Almacenamiento de imágenes | S3 / Cloudflare R2 |
| Autenticación (usuario) | JWT + OAuth (Google) |
| Pagos | Stripe |

---

## Modelo de datos

Entidades principales:

- **Usuario** — datos fiscales, régimen (estimación directa/módulos), plan (free/premium)
- **Documento** — imagen original, tipo (factura emitida/recibida/ticket), estado de procesamiento (`pendiente` / `procesado` / `revision_manual`)
- **Factura** — campos sumario extraídos y validados, vinculada a un Documento
- **LineaFactura** — una o más por Factura; cada una con `base_imponible`, `tipo_iva`, `cuota_iva`
- **CategoriaGasto** — tabla en BD con categoría, porcentaje de deducibilidad IVA e IRPF por defecto
- **PeriodoFiscal** — tabla persistida; se invalida y recalcula por trimestre al modificar una factura
- **BorradorModelo** — snapshot generado para un modelo (130, 303, 100) en un periodo concreto
- **CorreccionCampo** — campo corregido, valor original (IA), valor corregido (usuario), referencia a Documento

---

## Modelo de negocio

| Free | Premium |
|---|---|
| Límite de documentos/mes *(número a definir antes de lanzar)* | Documentos ilimitados |
| Dashboard básico | Generación de borrador de modelos 130 / 303 / 100 |
| — | Exportación Excel/PDF |
| — | Alertas de gastos deducibles no registrados |
| — | Integración/exportación para gestorías |

**Integración AEAT:** fuera de scope para el MVP. El producto genera el borrador; la presentación la realiza el usuario o su gestor con su certificado. Posible fase 2.

---

## Roadmap del MVP

- [ ] Esquema JSON de extracción con soporte a `LineaFactura[]` y catálogo de categorías de gasto en BD
- [ ] Backend Spring Boot: entidades base, auth JWT (usuario + servicio), endpoints CRUD de documentos/facturas
- [ ] Endpoint de callback `POST /internal/documents/{id}/result` — recibe resultado del servicio Python (autenticado con JWT de servicio)
- [ ] Servicio Python: preprocesado OpenCV + llamada a Gemini + validación Pydantic
- [ ] Fallback a Tesseract si Gemini falla o validación no pasa → si sigue sin confianza: marcar `revision_manual`
- [ ] Cola de mensajes RabbitMQ entre backend y servicio de extracción
- [ ] Polling de estado desde el frontend al endpoint de documento
- [ ] Lógica de deducibilidad automática por categoría + campo editable por el usuario
- [ ] Registro de `CorreccionCampo` al guardar cambios manuales
- [ ] Invalidación y recálculo de `PeriodoFiscal` al modificar facturas
- [ ] PWA: manifest, service worker, captura desde cámara nativa
- [ ] Dashboard por trimestre + bandeja de revisión manual
- [ ] Generación de borrador de modelos 303 y 130 a partir de `PeriodoFiscal`
- [ ] Exportación Excel/PDF
- [ ] Flujo de pago premium (Stripe)

---

## Consideraciones legales y de seguridad

- Cifrado en tránsito y en reposo para imágenes y base de datos (RGPD/LOPDGDD).
- El producto es una herramienta de organización y pre-cálculo — no asesoría fiscal ni presentación oficial. Debe quedar claro en el producto.
- Siempre debe haber una vía de revisión y corrección manual antes de cualquier exportación.
- Verifactu (Orden HAC/1177/2023): fuera de scope mientras el sistema no emita facturas, solo las procese.

---

## Estructura del repositorio

```
/backend         → Spring Boot (API REST, auth, persistencia, lógica fiscal)
/extraction-svc  → Python (preprocesado, IA multimodal, OCR fallback, validación)
/frontend        → React (dashboard, subida de documentos, revisión)
/docs            → Esquemas de extracción, catálogo de categorías, notas AEAT
```
