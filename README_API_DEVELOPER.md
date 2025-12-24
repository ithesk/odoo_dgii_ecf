# 🚀 Guía Rápida para Desarrolladores de API

> **Audiencia**: Desarrollador del microservicio dgii-ecf (Node.js)
> **Propósito**: Inicio rápido sin romper la integración existente
> **Tiempo de lectura**: 10 minutos

---

## 📌 Lo Esencial

### ¿Qué hace Odoo?

✅ Genera el **e-NCF** (ejemplo: `E310000000005`)
✅ Construye el **JSON** con los datos de la factura en formato DGII
✅ Envía el JSON al microservicio vía HTTP
✅ Guarda el **XML firmado** y el **trackID** que devuelves

### ¿Qué debe hacer tu microservicio?

✅ Recibir JSON de Odoo
✅ Convertir JSON → XML
✅ **Firmar** el XML con certificado .p12
✅ **Autenticar** con DGII (obtener token)
✅ **Enviar** XML firmado a DGII
✅ Devolver a Odoo: trackID + XML firmado + código de seguridad + QR

---

## 🔌 Endpoints Mínimos Requeridos

### 1. POST `/api/invoice/send`

**Para**: Facturas tipo 31, 33, 34, 41, 43, 44, 45, 46, 47

```javascript
app.post('/api/invoice/send', async (req, res) => {
  const { invoiceData, rnc, encf, environment } = req.body;

  try {
    // 1. Validar API key
    if (req.headers['x-api-key'] !== process.env.ODOO_API_KEY) {
      return res.status(401).json({
        success: false,
        error: 'API key inválida'
      });
    }

    // 2. Convertir JSON a XML
    const transformer = new Transformer();
    const xml = transformer.json2xml(invoiceData);

    // 3. Firmar XML
    const signature = new Signature(certs.key, certs.cert);
    const signedXml = signature.signXml(xml, 'ECF');

    // 4. Obtener código de seguridad
    const securityCode = getCodeSixDigitfromSignature(signedXml);

    // 5. Autenticar con DGII (si es necesario)
    const ecf = new ECF(certs, ENVIRONMENT[environment.toUpperCase()]);
    const tokenData = await ecf.authenticate();

    // 6. Enviar a DGII
    const response = await ecf.sendElectronicDocument(
      signedXml,
      `${rnc}${encf}.xml`
    );

    // 7. Generar QR
    const qrUrl = generateEcfQRCodeURL(
      rnc,
      invoiceData.ECF.Encabezado.Comprador.RNCComprador,
      encf,
      invoiceData.ECF.Encabezado.Totales.MontoTotal,
      invoiceData.ECF.Encabezado.Emisor.FechaEmision,
      getCurrentFormattedDateTime(),
      securityCode,
      ENVIRONMENT[environment.toUpperCase()]
    );

    // 8. Responder a Odoo
    res.json({
      success: true,
      data: {
        trackId: response.trackId,
        codigo: response.codigo || '0',
        estado: response.estado || 'Pendiente',
        rnc: rnc,
        encf: encf,
        fechaRecepcion: response.fechaRecepcion || new Date().toISOString(),
        signedXml: signedXml,
        securityCode: securityCode,
        qrCodeUrl: qrUrl,
        mensajes: response.mensajes || []
      }
    });

  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});
```

---

### 2. POST `/api/invoice/send-summary`

**Para**: Facturas tipo 32 (Consumo < 250K)

```javascript
app.post('/api/invoice/send-summary', async (req, res) => {
  const { invoiceData, rnc, encf, environment } = req.body;

  try {
    // Validar API key
    if (req.headers['x-api-key'] !== process.env.ODOO_API_KEY) {
      return res.status(401).json({ success: false, error: 'API key inválida' });
    }

    // 1. Convertir JSON a XML
    const transformer = new Transformer();
    const ecfXml = transformer.json2xml(invoiceData);

    // 2. Firmar XML del ECF
    const signature = new Signature(certs.key, certs.cert);
    const signedEcfXml = signature.signXml(ecfXml, 'ECF');

    // 3. Convertir ECF32 a RFCE
    const { xml: rfceXml, securityCode } = convertECF32ToRFCE(signedEcfXml);

    // 4. Autenticar y enviar
    const ecf = new ECF(certs, ENVIRONMENT[environment.toUpperCase()]);
    await ecf.authenticate();
    const response = await ecf.sendSummary(rfceXml, `${rnc}${encf}.xml`);

    // 5. Responder
    res.json({
      success: true,
      data: {
        trackId: response.trackId,
        codigo: response.codigo || '0',
        estado: response.estado || 'Pendiente',
        signedEcfXml: signedEcfXml,
        signedRfceXml: rfceXml,
        securityCode: securityCode,
        mensajes: response.mensajes || []
      }
    });

  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});
```

---

### 3. GET `/api/invoice/status/:trackId`

**Para**: Consultar estado de un documento

```javascript
app.get('/api/invoice/status/:trackId', async (req, res) => {
  const { trackId } = req.params;

  try {
    // Validar API key
    if (req.headers['x-api-key'] !== process.env.ODOO_API_KEY) {
      return res.status(401).json({ success: false, error: 'API key inválida' });
    }

    // Consultar en DGII
    const ecf = new ECF(certs, ENVIRONMENT.TEST); // Usar environment apropiado
    await ecf.authenticate();
    const status = await ecf.statusTrackId(trackId);

    res.json({
      success: true,
      data: {
        trackId: trackId,
        codigo: status.codigo,
        estado: status.estado,
        rnc: status.rnc,
        encf: status.encf,
        secuenciaUtilizada: status.secuenciaUtilizada,
        fechaRecepcion: status.fechaRecepcion,
        mensajes: status.mensajes || []
      }
    });

  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});
```

---

## 🎯 Estructura de Response CRÍTICA

### ✅ Response Exitoso (OBLIGATORIO)

```json
{
  "success": true,
  "data": {
    "trackId": "d2b6e27c-3908-46f3-afaa-2207b9501b4b",
    "codigo": "1",
    "estado": "Aceptado",
    "signedXml": "<ECF>...</ECF>",
    "securityCode": "ABC123",
    "qrCodeUrl": "https://dgii.gov.do/..."
  }
}
```

### ❌ Response de Error (OBLIGATORIO)

```json
{
  "success": false,
  "error": "Descripción del error en español"
}
```

---

## ⚠️ Campos que NO Debes Modificar

Odoo genera estos valores y **NO deben ser modificados** por el microservicio:

| Campo | Ejemplo | Razón |
|-------|---------|-------|
| `eNCF` | `E310000000005` | Generado por rangos de Odoo |
| `TipoeCF` | `31` | Determinado por lógica de negocio |
| `RNCEmisor` | `130862346` | RNC de la empresa en Odoo |
| `RNCComprador` | `123456789` | RNC del cliente |
| `MontoTotal` | `11800.00` | Calculado por Odoo |
| `FechaEmision` | `12-12-2025` | Fecha de la factura |

**Tu trabajo**: Tomar este JSON, convertirlo a XML, firmarlo, y enviarlo a DGII **tal cual**.

---

## 🔒 Autenticación

### Header que recibirás de Odoo

```http
POST /api/invoice/send HTTP/1.1
Content-Type: application/json
x-api-key: tu-api-key-secreta
```

### Validación en tu código

```javascript
// Middleware de autenticación
app.use((req, res, next) => {
  const apiKey = req.headers['x-api-key'];

  // Si configuraste API key en Odoo, valídala
  if (process.env.ODOO_API_KEY && apiKey !== process.env.ODOO_API_KEY) {
    return res.status(401).json({
      success: false,
      error: 'API key inválida o faltante'
    });
  }

  next();
});
```

---

## ⏱️ Performance

### Timeouts de Odoo

```python
# Odoo cancelará la petición si tardas más de:
POST /invoice/send          → 15 segundos
POST /invoice/send-summary  → 15 segundos
GET /invoice/status/:id     → 10 segundos
```

### Recomendación

Si DGII está lento:

1. Responde rápido a Odoo con `codigo: "0"` (Pendiente)
2. Procesa en background
3. Odoo consultará el estado después con `/invoice/status/:trackId`

```javascript
// Ejemplo de respuesta rápida
res.json({
  success: true,
  data: {
    trackId: generatedTrackId,
    codigo: "0",  // Pendiente
    estado: "En proceso",
    signedXml: signedXml,
    securityCode: securityCode
  }
});

// Procesar en background
processInBackground(generatedTrackId, signedXml);
```

---

## 🐛 Manejo de Errores

### Errores que Odoo Espera

```javascript
// Error de validación
res.status(400).json({
  success: false,
  error: 'El campo "rnc" es requerido'
});

// Error de autenticación
res.status(401).json({
  success: false,
  error: 'API key inválida'
});

// Error de DGII
res.status(502).json({
  success: false,
  error: 'DGII no responde, intente más tarde'
});

// Error interno
res.status(500).json({
  success: false,
  error: 'Error al firmar XML: certificado expirado'
});
```

### Logging para Debug

```javascript
const winston = require('winston');

const logger = winston.createLogger({
  level: 'info',
  format: winston.format.json(),
  transports: [
    new winston.transports.File({ filename: 'error.log', level: 'error' }),
    new winston.transports.File({ filename: 'combined.log' })
  ]
});

// En cada endpoint
logger.info('Received invoice', { rnc, encf, environment });
logger.error('DGII error', { error: error.message, trackId });
```

---

## 🧪 Testing

### Test con cURL

```bash
# Enviar factura
curl -X POST http://localhost:3000/api/invoice/send \
  -H "Content-Type: application/json" \
  -H "x-api-key: tu-api-key" \
  -d '{
    "invoiceData": {
      "ECF": {
        "Encabezado": {
          "IdDoc": {"TipoeCF": 31, "eNCF": "E310000000005"},
          "Emisor": {"RNCEmisor": "130862346"},
          "Comprador": {"RNCComprador": "123456789"},
          "Totales": {"MontoTotal": 11800.00}
        }
      }
    },
    "rnc": "130862346",
    "encf": "E310000000005",
    "environment": "test"
  }'

# Consultar estado
curl -X GET http://localhost:3000/api/invoice/status/track-id-123 \
  -H "x-api-key: tu-api-key"
```

### Ejemplo de Payload Real de Odoo

Ver archivo completo: `API_INTEGRATION_GUIDE.md` → Sección "Test Case 1"

---

## 📦 Dependencias Necesarias

### package.json

```json
{
  "name": "dgii-microservice",
  "version": "1.0.0",
  "dependencies": {
    "dgii-ecf": "^1.6.8",
    "express": "^4.18.2",
    "cors": "^2.8.5",
    "dotenv": "^16.0.3",
    "winston": "^3.8.2"
  }
}
```

### .env

```bash
# Puerto
PORT=3000

# Seguridad
ODOO_API_KEY=my-secret-api-key-12345

# Certificado .p12
CERTIFICATE_PATH=/app/certificates/empresa.p12
CERTIFICATE_PASSWORD=password-del-certificado

# Ambiente DGII (si quieres forzar uno por defecto)
DEFAULT_ENVIRONMENT=test
```

---

## 🚦 Flujo Completo

```
┌────────┐                    ┌──────────────┐                  ┌──────┐
│  Odoo  │                    │ Microservicio│                  │ DGII │
└───┬────┘                    └──────┬───────┘                  └───┬──┘
    │                                │                              │
    │ POST /api/invoice/send         │                              │
    │ {invoiceData, rnc, encf}       │                              │
    ├───────────────────────────────>│                              │
    │                                │                              │
    │                                │ 1. Validar API key           │
    │                                │ 2. JSON → XML                │
    │                                │ 3. Firmar XML                │
    │                                │ 4. Autenticar con DGII       │
    │                                │                              │
    │                                │ POST /recepcion/api/ecf      │
    │                                ├─────────────────────────────>│
    │                                │                              │
    │                                │<─────────────────────────────┤
    │                                │ {trackId, codigo, estado}    │
    │                                │                              │
    │                                │ 5. Generar QR                │
    │                                │                              │
    │<───────────────────────────────┤                              │
    │ {success: true, data: {...}}   │                              │
    │                                │                              │
    │ 6. Guardar trackId, XML, QR    │                              │
    │                                │                              │
    │                                │                              │
    │ [15 minutos después - CRON]    │                              │
    │                                │                              │
    │ GET /api/invoice/status/xxx    │                              │
    ├───────────────────────────────>│                              │
    │                                │                              │
    │                                │ GET /consulta/status/xxx     │
    │                                ├─────────────────────────────>│
    │                                │                              │
    │                                │<─────────────────────────────┤
    │                                │ {codigo: "1", estado: "Aceptado"}
    │                                │                              │
    │<───────────────────────────────┤                              │
    │ {success: true, data: {...}}   │                              │
    │                                │                              │
    │ 7. Actualizar estado a "Aceptado"                             │
    │                                │                              │
```

---

## 📚 Documentación Completa

Para detalles exhaustivos, consulta:

📖 **API_INTEGRATION_GUIDE.md** - Documentación técnica completa
- Contratos detallados de todos los endpoints
- Casos de prueba completos
- Troubleshooting
- Campos de auditoría

📖 **contexto.md** - Plan de implementación original
- Análisis de la librería dgii-ecf
- Arquitectura propuesta
- Ejemplos de código

📖 **README.md** - Guía de usuario del módulo Odoo

---

## ✅ Checklist para Go Live

Antes de integrar con Odoo en producción:

- [ ] Todos los endpoints responden en < 10 segundos
- [ ] Validación de `x-api-key` implementada
- [ ] Certificado .p12 configurado correctamente
- [ ] Probado en ambiente TesteCF de DGII
- [ ] Logging completo implementado
- [ ] Manejo de errores con mensajes en español
- [ ] Response siempre con `Content-Type: application/json`
- [ ] Estructura `{success: true/false, ...}` consistente
- [ ] No modificas campos críticos del JSON de Odoo
- [ ] HTTPS configurado (producción)

---

## 🆘 Necesitas Ayuda?

### Recursos

1. **Librería dgii-ecf**: https://github.com/victors1681/dgii-ecf
2. **Video tutorial**: https://youtu.be/J_D2VBJscxI
3. **Documentación DGII**: https://dgii.gov.do

### Common Issues

**"Certificado expirado"**
→ Renovar certificado .p12 con DigiFirma

**"DGII retorna error 401"**
→ Verificar autenticación, regenerar token

**"XML inválido"**
→ Verificar que el JSON de Odoo se convierte correctamente

**"Odoo muestra timeout"**
→ Optimizar el flujo, responder rápido con estado "pendiente"

---

## 📝 Notas Finales

### Lo que SÍ debes hacer

✅ Recibir JSON de Odoo tal cual
✅ Convertir JSON → XML
✅ Firmar XML con .p12
✅ Enviar a DGII
✅ Devolver trackID + XML firmado + código QR
✅ Validar API key
✅ Loggear todo
✅ Responder rápido (< 10s)

### Lo que NO debes hacer

❌ Modificar valores del JSON (e-NCF, RNC, montos, fechas)
❌ Generar nuevos e-NCF (lo hace Odoo)
❌ Calcular totales (ya vienen calculados)
❌ Validar RNC (lo hace Odoo)
❌ Gestionar rangos (lo hace Odoo)
❌ Tardar > 15 segundos en responder
❌ Retornar HTML en vez de JSON

---

**¡Buena suerte con la implementación! 🚀**

Si tienes dudas, revisa `API_INTEGRATION_GUIDE.md` para casos más detallados.
