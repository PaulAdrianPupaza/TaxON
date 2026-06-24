# GitHub Setup — Taxon

Guía de qué crear en GitHub para tener issues, discusiones arquitectónicas y el roadmap visible y organizado.

---

## 1. Labels (etiquetas)

Crear estas etiquetas en **Settings → Labels**:

### Por tipo
| Nombre | Color | Uso |
|---|---|---|
| `type: feature` | `#0075ca` | Nueva funcionalidad |
| `type: fix` | `#d73a4a` | Corrección de bug |
| `type: chore` | `#e4e669` | Infra, CI, dependencias, refactor sin impacto funcional |
| `type: architecture` | `#5319e7` | Decisiones de diseño, ADRs, discusión técnica |
| `type: security` | `#b60205` | Seguridad, RGPD, autenticación |
| `type: legal-fiscal` | `#f9d0c4` | Casuística fiscal española, modelos AEAT |

### Por capa
| Nombre | Color |
|---|---|
| `layer: backend` | `#1d76db` |
| `layer: extraction-svc` | `#0e8a16` |
| `layer: frontend` | `#e99695` |
| `layer: infra` | `#c2e0c6` |
| `layer: data-model` | `#bfd4f2` |

### Por estado
| Nombre | Color | Uso |
|---|---|---|
| `status: needs-discussion` | `#cc317c` | Requiere consenso antes de implementar |
| `status: blocked` | `#b60205` | Bloqueado por otro issue o decisión pendiente |
| `status: ready` | `#0e8a16` | Especificación cerrada, listo para implementar |
| `status: in-progress` | `#0075ca` | En desarrollo activo |

---

## 2. Milestones

Crear estos milestones en **Issues → Milestones**:

| Nombre | Descripción |
|---|---|
| `MVP Core` | Pipeline completo: subida → extracción → dashboard. Sin pagos ni exportación. |
| `MVP Completo` | Añade pagos (Stripe), exportación Excel/PDF y borradores 303/130. |
| `Post-MVP` | Integraciones avanzadas, fine-tuning, posible presentación AEAT directa. |

---

## 3. Issues a crear ahora

Copiar y crear cada uno de estos issues en el repositorio. Son los bloques de trabajo del MVP.

---

### 🏗️ Arquitectura / Decisiones pendientes

#### `[ARCH] Definir esquema JSON de extracción con LineaFactura[]`
- **Labels:** `type: architecture`, `layer: extraction-svc`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** Definir el schema Pydantic completo que el servicio Python espera de Gemini. Debe soportar múltiples líneas por factura, indicadores de confianza por campo, y campos opcionales (retención, NIF receptor).
  Resultado: un archivo `docs/extraction-schema.json` y su Pydantic model equivalente.

---

#### `[ARCH] Diseño del catálogo de categorías de gasto`
- **Labels:** `type: architecture`, `layer: data-model`, `status: needs-discussion`
- **Milestone:** `MVP Core`
- **Descripción:** Definir la tabla `CategoriaGasto` en BD con sus porcentajes de deducibilidad IVA e IRPF por defecto. Preguntas abiertas:
  - ¿Qué categorías entran en el MVP?
  - ¿El porcentaje es único o varía por régimen fiscal del usuario?
  - ¿Las categorías son editables por el usuario o solo por admin?

---

#### `[ARCH] Estrategia de invalidación de PeriodoFiscal`
- **Labels:** `type: architecture`, `layer: data-model`, `layer: backend`, `status: needs-discussion`
- **Milestone:** `MVP Core`
- **Descripción:** Al modificar una `LineaFactura` o registrar una `CorreccionCampo`, hay que invalidar y recalcular el `PeriodoFiscal` del trimestre afectado. Definir:
  - ¿El recálculo es síncrono en la misma transacción o asíncrono vía evento?
  - ¿Qué campos de `PeriodoFiscal` se calculan y cómo (suma de bases, IVA soportado, IVA repercutido, IRPF retenido)?

---

#### `[ARCH] Definir el límite de documentos en el plan free`
- **Labels:** `type: architecture`, `type: feature`, `status: needs-discussion`
- **Milestone:** `MVP Completo`
- **Descripción:** El modelo de negocio define un límite de documentos/mes para el plan free, pero el número no está fijado. Hay que decidirlo antes de implementar el middleware de throttling. Considerar: ¿el límite se aplica por documentos subidos, por documentos procesados con éxito, o por documentos con resultado validado?

---

### 🔧 Backend

#### `[FEATURE] Entidades base y migraciones Flyway`
- **Labels:** `type: feature`, `layer: backend`, `layer: data-model`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** Crear las migraciones SQL iniciales para: `usuarios`, `documentos`, `facturas`, `lineas_factura`, `categorias_gasto`, `periodos_fiscales`, `borradores_modelo`, `correcciones_campo`. Incluir columnas de auditoría y soft delete.

#### `[FEATURE] Auth JWT (usuario + servicio)`
- **Labels:** `type: feature`, `layer: backend`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** Implementar autenticación JWT para usuarios (login/refresh) y JWT de servicio con claim `role: service` para el endpoint de callback interno.

#### `[FEATURE] Endpoint callback de resultado de extracción`
- **Labels:** `type: feature`, `layer: backend`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** `POST /internal/documents/{id}/result` — recibe el resultado estructurado del servicio Python, valida el JWT de servicio, persiste `LineaFactura[]` y `CorreccionCampo[]` si aplica, actualiza el estado del `Documento` e invalida el `PeriodoFiscal`.

#### `[FEATURE] Endpoint de estado de documento (para polling)`
- **Labels:** `type: feature`, `layer: backend`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** `GET /api/documentos/{id}/status` — devuelve el estado actual del documento: `pendiente`, `procesado`, `revision_manual`, `error`. Usado por el frontend para el polling.

---

### 🐍 Servicio de extracción

#### `[FEATURE] Consumidor RabbitMQ + orquestador de extracción`
- **Labels:** `type: feature`, `layer: extraction-svc`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** Implementar el consumidor del exchange `taxon.extraction`. El orquestador llama a: preprocesado → Gemini → validación Pydantic → (si falla) Tesseract → callback REST al backend. Idempotente: si el documento ya está en `procesado`, hacer `ack` sin procesar.

#### `[FEATURE] Preprocesado OpenCV`
- **Labels:** `type: feature`, `layer: extraction-svc`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** Módulo de preprocesado: deskew (corrección de perspectiva), recorte de márgenes y mejora de contraste. Input: imagen raw. Output: imagen procesada lista para Gemini.

#### `[FEATURE] Manejo explícito del rate limit de Gemini`
- **Labels:** `type: feature`, `layer: extraction-svc`, `type: fix`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** Capturar el error 429 de la API de Gemini. Loguear con `document_id`. Enviar al backend un resultado con estado `error_rate_limit` para que marque el documento como `revision_manual`. No reintentar automáticamente.

---

### 🎨 Frontend

#### `[FEATURE] PWA: manifest y service worker`
- **Labels:** `type: feature`, `layer: frontend`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** Configurar la app React como PWA instalable. Manifest con nombre, iconos y `display: standalone`. Service worker que cachea solo assets estáticos. Captura desde cámara nativa en móvil.

#### `[FEATURE] Hook useDocumentStatus (polling)`
- **Labels:** `type: feature`, `layer: frontend`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** Custom hook que hace polling al endpoint de estado del documento cada 3 segundos mientras el estado sea `pendiente`. Se detiene automáticamente al recibir `procesado` o `revision_manual`.

#### `[FEATURE] Formulario de corrección manual`
- **Labels:** `type: feature`, `layer: frontend`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** Componente de edición de campos extraídos. Muestra el valor original de la IA como referencia visual. Al guardar, llama al endpoint de corrección que registra `CorreccionCampo`.

---

### 🔐 Seguridad

#### `[SECURITY] URLs pre-firmadas para imágenes en S3/R2`
- **Labels:** `type: security`, `layer: backend`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** El backend nunca devuelve la URL directa de la imagen. Implementar generación de URLs pre-firmadas con expiración de 15 minutos para el endpoint de visualización de documentos.

#### `[SECURITY] Enmascarado de NIF en logs`
- **Labels:** `type: security`, `layer: backend`, `layer: extraction-svc`, `status: ready`
- **Milestone:** `MVP Core`
- **Descripción:** Revisar todos los puntos de logging y asegurar que los NIFs no aparecen en texto plano. Implementar función de enmascarado reutilizable.

---

## 4. Discussions — temas arquitectónicos abiertos

Activar **GitHub Discussions** en Settings y crear estas discusiones en la categoría `💡 Ideas / Architecture`:

---

### `[DISCUSIÓN] ¿Cómo detectamos duplicados de forma robusta?`
El sistema detecta duplicados por `numero_factura` + `nif_emisor`, pero ¿qué hacemos con facturas sin número (tickets)? ¿Comparamos por hash de imagen? ¿Por importe + fecha + emisor? Definir la estrategia antes de implementar.

---

### `[DISCUSIÓN] ¿Cómo construimos y evolucionamos el prompt de Gemini?`
El prompt es la pieza más frágil del sistema. Preguntas abiertas:
- ¿Usamos structured output (JSON mode) de la API o instruimos en el prompt?
- ¿Cómo versionamos el prompt junto con los cambios del schema?
- ¿Cómo medimos si un cambio en el prompt mejora o empeora la extracción?

---

### `[DISCUSIÓN] Estrategia de fine-tuning a largo plazo`
Los datos de `CorreccionCampo` son el activo más valioso del sistema. Discutir:
- ¿Cuántas correcciones necesitamos para que sea útil hacer fine-tuning?
- ¿Fine-tuning sobre Gemini Flash o sobre un modelo abierto más pequeño?
- ¿Qué pipeline de evaluación usaríamos?

---

### `[DISCUSIÓN] ¿Ofrecemos API para gestorías en fase 2?`
Varias gestorías podrían querer integrar Taxon directamente en sus herramientas. Discutir si la exportación de fase 2 es una descarga de archivo o una API con autenticación por API key para terceros.

---

### `[DISCUSIÓN] Plan de migración a producción en la UE (Gemini billing)`
El tier gratuito de Gemini no es válido para usuarios finales en la UE. Definir cuándo y cómo activamos el billing, y si cambiamos Flash-Lite a Flash o al revés al entrar en producción.

---

## 5. Projects (tablero Kanban)

Crear un **GitHub Project** vinculado al repositorio con las siguientes columnas:

| Columna | Criterio de entrada |
|---|---|
| `📋 Backlog` | Issue creado, sin milestone asignado o en milestones futuros |
| `🔍 Needs Discussion` | Issues con label `status: needs-discussion` |
| `✅ Ready` | Especificación cerrada, label `status: ready` |
| `🚧 In Progress` | PR abierto que referencia el issue |
| `✔️ Done` | PR mergeado, issue cerrado con `Closes #N` |

Vincular todos los issues del apartado 3 al proyecto al crearlos.
