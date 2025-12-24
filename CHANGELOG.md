# Changelog - odoo_dgii_ecf

## [19.0.1.2.0] - 2025-12-12

### ✨ Added - Integración con microservicio dgii-ecf
- Campos en facturas para `dgii_track_id`, estado DGII, XML firmado, código de seguridad y QR.
- Acción **Enviar a DGII** consumiendo `/invoice/send` o `/invoice/send-summary` según tipo e-CF.
- Construcción de payload JSON desde la factura (items, totales, encabezado).
- Cron `DGII: Actualizar Estados de e-CF` para refrescar estados vía `/invoice/status/{trackId}`.
- Búsquedas y vistas actualizadas con estado/trackID y filtros de aceptación DGII.
- Parámetros de sistema para URL/API key/ambiente del microservicio.
- Vista de Ajustes (res.config.settings) para configurar URL, API Key y ambiente sin editar parámetros técnicos.
- Nuevos campos de auditoría: mensaje DGII y respuesta JSON completa almacenados en la factura.
- Helpers para aprobaciones comerciales y anulaciones (payload externos) usando endpoints del microservicio.

## [19.0.1.1.1] - 2025-12-11

### 🔧 Fixed - Corrección Formato e-NCF

**CAMBIO CRÍTICO**: Formato del e-NCF corregido según normativa oficial DGII.

#### Formato Anterior (INCORRECTO)
```
E + TipoECF(2) + Establecimiento(3) + PuntoEmision(3) + Secuencia(8) = 17 caracteres
Ejemplo: E3100100100000005
```

#### Formato Correcto (IMPLEMENTADO)
```
E + TipoECF(2) + Secuencial(10) = 13 caracteres
Ejemplo: E310000000005
```

#### Cambios Realizados

1. **account_move.py**:
   - Corregido método `_generate_encf()` para generar formato de 13 caracteres
   - Eliminado establecimiento y punto de emisión del e-NCF
   - Validación de longitud exacta de 13 caracteres
   - Secuencial ahora usa 10 dígitos (`{seq:010d}`)

2. **Documentación**:
   - `README.md` actualizado con formato correcto
   - `IMPLEMENTATION_SUMMARY.md` corregido
   - Nuevo archivo `FORMATO_ENCF.md` con explicación detallada

3. **Aclaración Importante**:
   - El establecimiento y punto de emisión **NO** van en el e-NCF generado
   - Se usan solo para identificar el rango de secuencias autorizado
   - Esto permite múltiples rangos por tipo de comprobante

#### Migración

Si ya generó e-NCF con el formato anterior:
- Los e-NCF existentes son inválidos según normativa DGII
- Se recomienda anularlos y regenerar con el formato correcto
- El sistema ahora genera automáticamente el formato de 13 caracteres

---

## [19.0.1.1.0] - 2025-12-11

### ✨ Added - Soporte de Múltiples Tipos de Secuencia por Diario

#### Nuevo Modelo: `dgii.ecf.tipo`
- Catálogo maestro de tipos de comprobantes fiscales electrónicos
- 10 tipos precargados automáticamente (31-47)
- Clasificación por uso: venta, compra, notas de crédito/débito
- Campo `requiere_rnc` para validaciones automáticas
- Vistas completas (lista, formulario)
- Menú en Contabilidad → Configuración → Tipos e-CF

#### Mejoras en `account.journal`
- **Campo nuevo**: `dgii_tipo_ecf_ids` (Many2many) - Permite seleccionar múltiples tipos
- **Campo legacy**: `dgii_tipo_ecf` (Selection) - Mantenido por compatibilidad
- **Método nuevo**: `get_tipo_ecf_for_invoice(invoice)` - Selección inteligente automática
- **Método actualizado**: `get_available_ecf_range(tipo_ecf)` - Acepta tipo específico como parámetro

#### Selección Inteligente Automática
El sistema ahora selecciona automáticamente el tipo de comprobante correcto según:
- Cliente **CON RNC** → Tipo 31 (Factura de Crédito Fiscal Electrónica)
- Cliente **SIN RNC** → Tipo 32 (Factura de Consumo Electrónica)
- **Nota de Crédito** (out_refund/in_refund) → Tipo 34
- **Nota de Débito** → Tipo 33
- **Facturas de Compra** → Tipo 41

#### Mejoras en `account.move`
- Método `_generate_encf()` actualizado para usar selección inteligente
- Validación de RNC según requisitos del tipo de comprobante
- Soporte para múltiples tipos en el mismo diario

#### Vistas Actualizadas
- Vista de diario: Widget `many2many_tags` para selección de tipos
- Información visual de cómo funciona la selección automática
- Vista mejorada de rangos asociados con más detalles

#### Seguridad
- Permisos para modelo `dgii.ecf.tipo`
- Lectura para todos los usuarios
- Edición solo para gestores de contabilidad

### 📝 Changed
- Documentación actualizada (README.md, IMPLEMENTATION_SUMMARY.md)
- Manifiesto actualizado con nuevo modelo y vistas
- Archivo de seguridad con nuevos permisos

### 🔄 Compatibilidad
- ✅ **Retrocompatible** con configuraciones existentes
- ✅ Campo legacy `dgii_tipo_ecf` sigue funcionando
- ✅ No requiere migración de datos
- ✅ Diarios con configuración antigua siguen funcionando

### 📊 Casos de Uso Soportados

#### Diario de Ventas
Configurar tipos: 31, 32, 33, 34
- Facturas a clientes con RNC → Automáticamente tipo 31
- Facturas a consumidor final → Automáticamente tipo 32
- Notas de crédito → Automáticamente tipo 34
- Notas de débito → Automáticamente tipo 33

#### Diario Gubernamental
Configurar tipos: 45, 33, 34
- Facturas a gobierno → Tipo 45
- Ajustes → Tipos 33/34 según corresponda

#### Diario de Exportación
Configurar tipos: 46, 33, 34
- Facturas de exportación → Tipo 46
- Ajustes → Tipos 33/34

#### Diario de Compras
Configurar tipos: 41, 43, 33, 34
- Compras regulares → Tipo 41
- Gastos menores → Tipo 43
- Ajustes → Tipos 33/34

---

## [19.0.1.0.0] - 2025-12-10

### ✨ Added - Implementación Inicial

#### Modelos
- `dgii.ecf.sequence.range` - Gestión de rangos de secuencias
- Extensión de `account.journal` - Configuración DGII
- Extensión de `account.move` - Generación de e-NCF
- Extensión de `res.partner` - Validación RNC

#### Funcionalidades
- Generación automática de e-NCF al confirmar factura
- Validación de RNC mediante API de Megaplus
- Control de vencimiento de rangos (cron job)
- Locking concurrente para evitar duplicados
- 10 tipos de comprobantes según normativa DGII

#### Vistas
- Vistas completas para rangos (lista, formulario, kanban, búsqueda)
- Extensión de vistas de diario
- Extensión de vistas de factura
- Extensión de vistas de contacto

#### Seguridad
- Permisos por grupo (invoice, user, manager)
- Validaciones de integridad de datos
- Constraint de unicidad de e-NCF

#### Documentación
- README completo con guía de instalación y configuración
- IMPLEMENTATION_SUMMARY con detalles técnicos
- Comentarios en código en español
