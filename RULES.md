# Reglas de implementación — Taxon

> Estas reglas son vinculantes para cualquier contribución al proyecto. El objetivo es que cada pieza del sistema sea robusta, limpia, escalable y fácil de modificar sin tener que entender el sistema entero.

---

## 1. Principios generales

### 1.1 Una responsabilidad por clase/módulo
Cada clase, servicio o módulo hace **una sola cosa**. Si el nombre necesita "y" para describirse, hay que dividirlo.

### 1.2 Abierto a extensión, cerrado a modificación
Añadir una nueva categoría de gasto, un nuevo tipo de retención o un nuevo modelo fiscal **no debe requerir modificar código existente**. Se deben usar tablas en BD, enumeraciones extensibles y estrategias/plugins donde corresponda.

### 1.3 Fail loudly
Los errores no se silencian. Si algo falla, se loguea con contexto suficiente (ID del documento, campo afectado, valor recibido) y se propaga correctamente. Nunca `catch (Exception e) {}` vacío.

### 1.4 Sin magia implícita
El comportamiento del sistema debe poderse leer en el código, no deducirse de convenciones ocultas. Los valores por defecto relevantes (porcentaje de deducibilidad, umbrales de confianza) van en constantes o en configuración, no hardcodeados en mitad de una función.

### 1.5 Inmutabilidad por defecto
Los objetos de dominio son inmutables salvo que haya razón explícita para lo contrario. Preferir `record` en Java y dataclasses/Pydantic en Python.

---

## 2. Backend — Java / Spring Boot

### Estructura de paquetes

```
com.taxon
  ├── api/            # Controllers REST (entrada/salida: DTOs únicamente)
  ├── domain/         # Entidades, value objects, lógica de negocio pura
  ├── application/    # Casos de uso / servicios de aplicación
  ├── infrastructure/ # JPA repositories, RabbitMQ, S3, Stripe, JWT
  └── config/         # Beans de Spring, configuración de seguridad
```

### Reglas

- **Los controllers no contienen lógica.** Solo validan la entrada, delegan al caso de uso y mapean la salida. Si un controller tiene más de 20 líneas de código real, algo está mal.
- **Los repositorios no contienen lógica de negocio.** Solo consultas. Las reglas fiscales van en el dominio.
- **DTOs separados de entidades.** Nunca exponer una entidad JPA directamente en la API. Usar record DTOs para request/response.
- **Validación de entrada con Bean Validation** (`@Valid`, `@NotNull`, `@Pattern`) en los DTOs de request. No validar manualmente en el controller.
- **Transacciones explícitas** (`@Transactional`) solo en la capa de aplicación, nunca en controllers ni repositorios.
- **Configuración por entorno** con `application-{profile}.yml`. Los secretos (JWT secret, Stripe key, RabbitMQ password) solo se leen de variables de entorno. Nunca en el repositorio.
- **El endpoint de callback interno** (`POST /internal/documents/{id}/result`) debe validar el JWT de servicio antes de persistir cualquier dato. El claim `role: service` es obligatorio.

### Convenciones de nombrado

| Elemento | Convención | Ejemplo |
|---|---|---|
| Entidades | PascalCase | `Documento`, `LineaFactura` |
| DTOs | sufijo `Request` / `Response` | `ExtraccionResultadoRequest` |
| Casos de uso | verbo + sustantivo | `ProcesarDocumentoUseCase` |
| Repositorios | sufijo `Repository` | `DocumentoRepository` |
| Endpoints | sustantivos en plural, kebab-case | `/api/documentos`, `/api/periodos-fiscales` |

---

## 3. Servicio de extracción — Python

### Estructura de módulos

```
extraction-svc/
  ├── main.py              # Punto de entrada: consumidor RabbitMQ
  ├── preprocessing/       # OpenCV: deskew, recorte, contraste
  ├── extraction/          # Llamada a Gemini, construcción del prompt
  │   └── prompts/         # Prompts como archivos de texto plano (.txt)
  ├── validation/          # Pydantic schemas, validación aritmética, NIF
  ├── fallback/            # Tesseract OCR y combinación de resultados
  ├── callback/            # Cliente REST que notifica al backend Java
  ├── models/              # Dataclasses / Pydantic models compartidos
  └── config.py            # Settings (pydantic-settings, desde env vars)
```

### Reglas

- **El prompt de Gemini es un archivo de texto plano** en `extraction/prompts/`, versionado en el repositorio. No construir el prompt concatenando strings en el código. Parametrizar con template (`string.Template` o Jinja2).
- **El schema JSON esperado de Gemini** se define como un Pydantic model. La validación nunca es manual: si el modelo devuelve un campo fuera del schema, Pydantic lo rechaza.
- **Confianza explícita.** Cada campo del resultado tiene un indicador de confianza: `"alta"` (campo presente y coherente), `"baja"` (campo presente pero no pasa validación), `"ausente"`. El backend decide si marcar para revisión.
- **El fallback OCR es un módulo independiente**, no un `if` dentro del flujo principal. Se llama desde el orquestador (`main.py`) de forma explícita.
- **Sin estado global.** Cada mensaje de la cola se procesa en una función pura que recibe el payload y devuelve el resultado.
- **Logging estructurado** (JSON) con `structlog`. Siempre incluir `document_id` en cada log del procesamiento.
- **Rate limit de Gemini manejado explícitamente:** capturar el error 429, loguearlo con el `document_id`, y enviar al backend un resultado con estado `error_rate_limit` para que lo marque como `revision_manual`. No reintentar automáticamente en el MVP.

### Convenciones de nombrado

- Funciones: `snake_case`, verbo en infinitivo (`extraer_campos`, `validar_nif`)
- Módulos: sustantivo en singular (`extraction`, `validation`)
- Constantes: `UPPER_SNAKE_CASE` en `config.py`

---

## 4. Modelo de datos

- **Migraciones con Flyway.** Cada cambio de esquema es un script SQL versionado en `backend/src/main/resources/db/migration/`. Nunca usar `ddl-auto=update` fuera de local.
- **Columnas de auditoría obligatorias** en todas las tablas: `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`.
- **Soft delete** para documentos y facturas: columna `deleted_at TIMESTAMPTZ NULL`. Nunca borrar datos fiscales definitivamente.
- **UUIDs como primary keys** en todas las tablas. No auto-increment entero.
- **`PeriodoFiscal`:** al modificar una `LineaFactura` o `CorreccionCampo`, se invalida el `PeriodoFiscal` del trimestre afectado y se recalcula en la misma transacción.
- **`CorreccionCampo`:** campos obligatorios: `documento_id`, `nombre_campo`, `valor_original` (texto), `valor_corregido` (texto), `corregido_por` (user_id), `corregido_at`.

---

## 5. Cola de mensajes — RabbitMQ

- **Un exchange por dominio.** Exchange: `taxon.extraction`.
- **Dead Letter Exchange (DLX) configurado desde el inicio**, aunque en el MVP no se reencole automáticamente. Los mensajes fallidos deben ser inspeccionables.
- **El mensaje incluye siempre:** `document_id`, `user_id`, `s3_key` de la imagen, `timestamp_encolado`.
- **Idempotencia:** el servicio Python debe tolerar recibir el mismo `document_id` dos veces. Si el documento ya está en estado `procesado`, ignorar el mensaje y confirmar (`ack`).

---

## 6. Frontend — React / PWA

- **Un componente por archivo.** Componentes en `PascalCase.tsx`, hooks en `use-nombre.ts`.
- **Sin lógica de negocio en componentes.** La lógica va en custom hooks o en `/services`. Los componentes solo renderizan y llaman a hooks.
- **El polling de estado** de un documento se implementa como un hook (`useDocumentStatus`) que hace fetch cada N segundos mientras el estado sea `pendiente`, y se detiene automáticamente al recibir `procesado` o `revision_manual`.
- **Sin `useEffect` con dependencias vacías** para inicializar datos. Usar React Query para data fetching.
- **Los formularios de corrección manual** muestran el valor original de la IA como placeholder. El usuario nunca escribe desde cero.
- **PWA:** el service worker solo cachea assets estáticos. Los datos fiscales no se almacenan en el cliente.

---

## 7. Seguridad

- **JWT de usuario:** expiración corta (15 min) + refresh token de larga duración.
- **JWT de servicio:** expiración larga (30 días), rotación manual. Solo válido para `/internal/*`.
- **Imágenes en S3/R2:** nunca exponer la URL directa. Generar URLs pre-firmadas con expiración corta (15 min).
- **NIF/CIF en logs:** nunca loguear NIFs completos. Enmascarar o no loguear.
- **Variables de entorno:** `.env.example` en el repositorio con nombres pero sin valores. El `.env` real en `.gitignore`.

---

## 8. Testing

- **Cada caso de uso de aplicación tiene su test unitario.** Sin Spring ni base de datos: el repositorio se mockea.
- **El servicio Python tiene tests unitarios por módulo** con fixtures de imágenes de prueba en `tests/fixtures/`.
- **Tests de integración** para endpoints críticos (subida de documento, callback de resultado, corrección manual) con Testcontainers (PostgreSQL + RabbitMQ).
- **Los tests no se saltan** (`@Disabled`, `pytest.mark.skip`) sin un comentario explicando por qué y un issue asociado.

---

## 9. Git y pull requests

- **Rama principal:** `main`. Siempre en estado desplegable.
- **Ramas de trabajo:** `feature/`, `fix/`, `chore/` + descripción en kebab-case.
  - Ej: `feature/linea-factura-model`, `fix/gemini-rate-limit-handling`
- **Cada PR referencia el issue que resuelve** (`Closes #N`) y tiene evidencia de que los tests pasan.
- **Sin código comentado** en los commits finales.
- **Commits en inglés**, modo imperativo, conciso.
  - Ej: `Add CorreccionCampo entity and migration`, `Fix NIF validation for NIE format`
