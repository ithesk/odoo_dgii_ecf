# DGII - Facturación Electrónica República Dominicana

Módulo de Odoo 19 para la gestión completa de facturación electrónica según normativa DGII de República Dominicana.

## Características Principales

### 🧾 Gestión de e-NCF (Comprobantes Fiscales Electrónicos)

- **10 tipos de comprobantes** según normativa DGII
- **Múltiples tipos por diario** - Un diario puede emitir varios tipos de comprobantes
- **Selección inteligente automática** - El sistema elige el tipo correcto según el contexto
- Generación automática de e-NCF en formato: **`E310000000005`** (13 caracteres)
  - **E** = Serie electrónica (1 carácter)
  - **31** = Tipo de comprobante (2 dígitos)
  - **0000000005** = Secuencial (10 dígitos)
- Validación de rangos autorizados
- Control de vencimiento y agotamiento

### 📊 Rangos de Secuencias

- Gestión completa de rangos autorizados por DGII
- Validaciones automáticas (solapamiento, vencimiento, agotamiento)
- Locking para evitar duplicados en ambientes concurrentes
- Alertas de vencimiento próximo
- Estadísticas de uso en tiempo real

### 🔍 Validación de RNC

- Integración con API de Megaplus (https://rnc.megaplus.com.do)
- Autocompletado de datos del contribuyente
- Verificación de estado en DGII
- Detección de facturadores electrónicos

### ✅ Validaciones Integradas

Antes de generar e-NCF:
- ✓ Factura confirmada (posted)
- ✓ Tipo e-CF configurado en diario
- ✓ Establecimiento y punto de emisión válidos (3 dígitos)
- ✓ Cliente con RNC/Cédula
- ✓ Rango activo y disponible
- ✓ Fecha de vencimiento vigente

## Tipos de e-CF Soportados

| Código | Descripción |
|--------|-------------|
| 31 | Factura de Crédito Fiscal Electrónica |
| 32 | Factura de Consumo Electrónica |
| 33 | Nota de Débito Electrónica |
| 34 | Nota de Crédito Electrónica |
| 41 | Comprobante Electrónico de Compras |
| 43 | Comprobante Electrónico para Gastos Menores |
| 44 | Comprobante Electrónico para Regímenes Especiales |
| 45 | Comprobante Electrónico Gubernamental |
| 46 | Comprobante Electrónico para Exportaciones |
| 47 | Comprobante Electrónico para Pagos al Exterior |

## Instalación

1. Copiar el módulo en la carpeta `addons` de Odoo
2. Actualizar la lista de aplicaciones
3. Instalar "DGII - Facturación Electrónica RD"
4. Configurar Ajustes → DGII e-CF con URL base, API Key y ambiente

## Configuración

### 1. Configurar Diario Contable

Ir a: **Contabilidad → Configuración → Diarios**

En la pestaña "DGII - Facturación Electrónica":
- Seleccionar **Tipos e-CF** (puede seleccionar múltiples tipos)
  - Ejemplo para diario de ventas: 31 (Crédito Fiscal), 32 (Consumo), 33 (Nota Débito), 34 (Nota Crédito)
  - Ejemplo para diario gubernamental: 45 (Gubernamental), 33 (Nota Débito), 34 (Nota Crédito)
- Ingresar **Establecimiento** (3 dígitos, ej: 005)
- Ingresar **Punto de Emisión** (3 dígitos, ej: 001)

**Selección Automática de Tipo:**
El sistema seleccionará automáticamente el tipo correcto al facturar:
- Cliente **con RNC** → Tipo 31 (Factura de Crédito Fiscal)
- Cliente **sin RNC** → Tipo 32 (Factura de Consumo)
- Nota de Crédito → Tipo 34
- Nota de Débito → Tipo 33

### 2. Crear Rango de Secuencias

Ir a: **DGII República Dominicana → Configuración → Rangos e-NCF**

Crear un nuevo rango:
- **Nombre**: Descripción del rango
- **Tipo e-CF**: Debe coincidir con el diario
- **Establecimiento**: 3 dígitos (ej: 005)
- **Punto de Emisión**: 3 dígitos (ej: 001)
- **Secuencia Desde**: Número inicial autorizado
- **Secuencia Hasta**: Número final autorizado
- **Fecha Vencimiento**: Fecha de expiración del rango
- **Diarios**: Seleccionar los diarios que pueden usar este rango

Hacer clic en **Activar**

### 3. Validar RNC de Clientes

En el formulario de contacto:
1. Ingresar el RNC en el campo **VAT**
2. Hacer clic en **Validar RNC / Autocompletar**
3. Los datos se completarán automáticamente desde DGII

## Uso

### Generar e-NCF Automáticamente

Al confirmar una factura, el e-NCF se genera automáticamente si:
- El diario tiene configuración DGII completa
- Existe un rango activo y válido
- El cliente tiene RNC

### Generar e-NCF Manualmente

Si la factura no tiene e-NCF:
1. Abrir la factura confirmada
2. Hacer clic en **Generar e-NCF**

### Enviar a DGII

*(Pendiente de implementación según especificaciones de API DGII)*

1. Factura debe tener e-NCF generado
2. Hacer clic en **Enviar a DGII**

## Estructura Técnica

```
odoo_dgii_ecf/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── dgii_ecf_sequence_range.py    # Modelo de rangos e-NCF
│   ├── account_journal.py             # Extensión de diarios
│   ├── account_move.py                # Extensión de facturas
│   └── res_partner.py                 # Extensión de contactos
├── views/
│   ├── dgii_ecf_sequence_range_views.xml
│   ├── account_journal_views.xml
│   ├── account_move_views.xml
│   └── res_partner_views.xml
├── data/
│   └── ir_cron.xml                    # Cron job para vencimientos
├── security/
│   └── ir.model.access.csv            # Permisos de acceso
└── static/
    └── description/
        └── icon.png
```

## Seguridad y Permisos

- **Usuarios de Facturación**: Lectura de rangos
- **Contadores**: Lectura, escritura y creación de rangos
- **Gestores Contables**: Control total (incluye eliminación)

## Cron Jobs

### Verificar Rangos Vencidos
- **Frecuencia**: Diario
- **Función**: Marca rangos vencidos automáticamente
- **Hora**: Se ejecuta según configuración del sistema

### Actualizar Estados DGII
- Cron `DGII: Actualizar Estados de e-CF` cada 15 minutos para facturas con trackID.
- Botón **Consultar Estado DGII** en la factura refresca de inmediato.

## Notas Técnicas

### Formato e-NCF

```
E + TipoECF(2) + Secuencial(10)
```

**Ejemplo**: `E310000000005`
- E: Prefijo electrónico
- 31: Factura de Crédito Fiscal
- 0000000005: Secuencia (10 dígitos con padding)

### Integración con el microservicio dgii-ecf

- Configurar desde Ajustes → DGII e-CF:
  - URL base del microservicio, ej. `http://localhost:3000/api`
  - API Key (opcional)
  - Ambiente: `test` | `cert` | `prod`
- Botones en factura:
  - **Generar e-NCF**: genera el comprobante si está posteada.
  - **Enviar a DGII**: firma/envía vía microservicio y guarda `trackId`, estado, XML firmado, código de seguridad y QR.
  - **Consultar Estado**: refresca el estado con DGII usando el `trackId`.
- Cron automático `DGII: Actualizar Estados de e-CF` cada 15 minutos para facturas pendientes.
- Se almacena mensaje DGII y respuesta JSON para auditoría.

### Locking Concurrente

El módulo implementa locking pesimista (`FOR UPDATE NOWAIT`) en la obtención de secuencias para evitar duplicados en entornos multi-usuario.

### API de Validación RNC

URL: `https://rnc.megaplus.com.do/api/consulta?rnc=<RNC>`

Campos mapeados:
- Nombre comercial
- Actividad económica
- Régimen de pagos
- Estado en DGII
- Administración local
- Facturador electrónico

## Pendientes de Implementación

- [ ] Ajustar payloads específicos RFCE/ACECF/ANECF según contrato final del microservicio
- [ ] Firma digital de e-NCF (delegada al microservicio)  VER EL MICROSERVICIO   https://github.com/ithesk/l10n_do_e_cf_tests
- [ ] Generación de XML según esquema DGII (delegada al microservicio)
- [ ] Reportes estadísticos DGII

## Soporte

Para soporte técnico o reportar errores, contactar al equipo de desarrollo.

## Licencia

LGPL-3

## Autor

itheskdev- 2025
