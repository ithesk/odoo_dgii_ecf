# 📋 Plan de Implementación: Odoo + DGII-eCF

## Fecha: 2025-12-09

---

## 📚 Tabla de Contenidos

1. [Análisis de la Librería dgii-ecf](#análisis-de-la-librería-dgii-ecf)
2. [Funcionalidades Disponibles](#funcionalidades-disponibles)
3. [Arquitectura Propuesta](#arquitectura-propuesta)
4. [Endpoints del Microservicio](#endpoints-del-microservicio)
5. [Flujo de Integración con Odoo](#flujo-de-integración-con-odoo)
6. [Fases de Implementación](#fases-de-implementación)
7. [Decisiones Técnicas](#decisiones-técnicas)
8. [Próximos Pasos](#próximos-pasos)

---

## 🔍 Análisis de la Librería dgii-ecf

**Librería**: `dgii-ecf` v1.6.8
**Repositorio**: https://github.com/victors1681/dgii-ecf
**Propósito**: SDK completo para facturación electrónica en República Dominicana (DGII)

### Tecnologías
- Node.js >= 20.0.0
- TypeScript
- Dependencias principales:
  - `node-forge`: Manejo de certificados .p12
  - `@xmldom/xmldom`: Parsing de XML
  - `xml-crypto`: Firma digital XML
  - `axios`: Peticiones HTTP a DGII
  - `jsonwebtoken`: Autenticación JWT

---

## ✅ Funcionalidades Disponibles

### 🔐 1. Autenticación
- ✅ Autenticarse con DGII (ambientes: Test, Cert, Producción)
- ✅ Autenticarse con compradores autorizados (emisor-receptor)
- ✅ Generar y verificar tokens JWT
- ✅ Crear sistemas de autenticación personalizados

**Código ejemplo**:
```javascript
import ECF, { P12Reader, ENVIRONMENT } from 'dgii-ecf';

// Leer certificado .p12
const reader = new P12Reader('password_del_certificado');
const certs = reader.getKeyFromFile('/path/to/certificado.p12');

// Autenticar
const ecf = new ECF(certs, ENVIRONMENT.DEV);
const tokenData = await ecf.authenticate();
```

---

### 📝 2. Firma Digital de XML
- ✅ Firmar archivos XML con certificado .p12
- ✅ Leer y validar certificados .p12
- ✅ Validar firmas XML existentes
- ✅ Verificar fechas de expiración de certificados
- ✅ Extraer información del certificado desde Base64

**Código ejemplo**:
```javascript
import { Signature } from 'dgii-ecf';

const signature = new Signature(certs.key, certs.cert);
const signedXml = signature.signXml(xmlString, 'ECF');
```

---

### 📤 3. Envío de Documentos Electrónicos

| Tipo de Documento | Código | Método | Descripción |
|-------------------|--------|--------|-------------|
| Factura de Crédito Fiscal | ECF (31) | `sendElectronicDocument()` | Facturas normales |
| Factura de Consumo | ECF (32) | `sendSummary()` | Facturas < 250K (resumen RFCE) |
| Nota de Crédito | ACECF | `sendElectronicDocument()` | Anulaciones/devoluciones |
| Nota de Débito | ANECF | `sendElectronicDocument()` | Cargos adicionales |
| Aprobación Comercial | ACECF | `sendCommercialApproval()` | Confirmación de recepción |
| Anulación de Secuencias | ANECF | `voidENCF()` | Anular rangos de e-NCF |

**Código ejemplo**:
```javascript
// Enviar factura de crédito fiscal
const response = await ecf.sendElectronicDocument(
  signedXml,
  `${rnc}${encf}.xml`
);

// Respuesta incluye trackId para seguimiento
console.log(response.trackId); // "d2b6e27c-3908-46f3-afaa-2207b9501b4b"
```

---

### 🔍 4. Consultas y Rastreo

| Método | Descripción | Parámetros |
|--------|-------------|------------|
| `statusTrackId(trackId)` | Estado de un documento por trackID | trackId: string |
| `trackStatuses(rnc, encf)` | Todos los tracks de un e-NCF | rnc, encf: string |
| `inquiryStatus(...)` | Validar estado de un e-CF | rncEmisor, encf, rncComprador?, codigoSeguridad? |
| `getSummaryInvoiceInquiry(...)` | Consultar resumen RFCE (solo prod) | rnc_emisor, encf, cod_seguridad |
| `getCustomerDirectory(rnc)` | Directorio de clientes autorizados | rnc: string |

**Código ejemplo**:
```javascript
// Consultar estado por trackID
const status = await ecf.statusTrackId('d2b6e27c-3908-...');
console.log(status.estado); // "Aceptado" | "Rechazado" | "Pendiente"

// Consultar validez de factura
const inquiry = await ecf.inquiryStatus(
  '130862346', // RNC Emisor
  'E310005000201', // e-NCF
  '123456789', // RNC Comprador
  'ABC123' // Código de seguridad
);
```

---

### 🛠️ 5. Utilidades

```javascript
// Convertir JSON a XML
import { Transformer } from 'dgii-ecf';
const transformer = new Transformer();
const xml = transformer.json2xml(jsonFactura);

// Convertir ECF32 a RFCE (facturas < 250K)
import { convertECF32ToRFCE } from 'dgii-ecf';
const { xml, securityCode } = convertECF32ToRFCE(signedEcfXml);

// Generar código QR
import { generateFcQRCodeURL, generateEcfQRCodeURL } from 'dgii-ecf';
const qrUrl = generateEcfQRCodeURL(
  rncEmisor, rncComprador, encf,
  montoTotal, fechaEmision, fechaFirma,
  codigoSeguridad, ENVIRONMENT.PROD
);

// Extraer código de seguridad (primeros 6 dígitos del hash)
import { getCodeSixDigitfromSignature } from 'dgii-ecf';
const securityCode = getCodeSixDigitfromSignature(signedXml);

// Obtener fecha/hora actual en formato DGII
import { getCurrentFormattedDateTime } from 'dgii-ecf';
const timestamp = getCurrentFormattedDateTime(); // "09-12-2025 17:30:45"
```

---

### 🌐 6. Ambientes Disponibles

```javascript
import { ENVIRONMENT } from 'dgii-ecf';

// Desarrollo
const ecf = new ECF(certs, ENVIRONMENT.DEV);   // TesteCF
// URL base: https://ecf.dgii.gov.do/TesteCF/

// Certificación
const ecf = new ECF(certs, ENVIRONMENT.CERT);  // CerteCF
// URL base: https://ecf.dgii.gov.do/CerteCF/

// Producción
const ecf = new ECF(certs, ENVIRONMENT.PROD);  // eCF
// URL base: https://ecf.dgii.gov.do/eCF/
```

---

## 🏗️ Arquitectura Propuesta

```
┌─────────────────────────────────────────────────────────────────┐
│                         ODOO ERP                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Módulo: Facturación Electrónica DGII                   │    │
│  │ - Genera facturas desde ventas                          │    │
│  │ - Construye JSON con datos de factura                   │    │
│  │ - Envía petición HTTP al microservicio                 │    │
│  │ - Guarda trackID y XML firmado                          │    │
│  │ - Consulta estados periódicamente                       │    │
│  └────────────────────────────────────────────────────────┘    │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP REST API
                       │ (JSON Request/Response)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│           MICROSERVICIO NODE.JS (dgii-ecf)                      │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Express + TypeScript                                    │    │
│  │ - Endpoints REST para operaciones DGII                 │    │
│  │ - Autentica con DGII (genera token)                    │    │
│  │ - Convierte JSON → XML                                  │    │
│  │ - Firma XML con certificado .p12                       │    │
│  │ - Envía factura a DGII                                 │    │
│  │ - Consulta estados y trackIDs                          │    │
│  │ - Maneja aprobaciones comerciales                      │    │
│  │ - Genera códigos QR                                    │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Certificado .p12 almacenado de forma segura                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTPS
                       │ (XML firmado)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API DGII                                    │
│  - Recibe e-CF firmados digitalmente                            │
│  - Valida firma y certificado                                   │
│  - Retorna Track ID para seguimiento                            │
│  - Procesa documento (Aceptado/Rechazado)                       │
└─────────────────────────────────────────────────────────────────┘
```

### Ventajas de esta Arquitectura

1. **Separación de responsabilidades**: Odoo maneja lógica de negocio, microservicio maneja firma digital
2. **Seguridad**: Certificado .p12 nunca sale del microservicio
3. **Escalabilidad**: Múltiples instancias de Odoo pueden usar el mismo microservicio
4. **Mantenibilidad**: Actualizaciones de dgii-ecf no afectan Odoo
5. **Reutilización**: Otros sistemas pueden consumir el microservicio

---

## 📦 Endpoints del Microservicio

### **POST** `/api/auth/dgii`
**Descripción**: Autenticar con DGII y obtener token de acceso
**Body**:
```json
{
  "environment": "test" // "test" | "cert" | "prod"
}
```
**Response**:
```json
{
  "success": true,
  "data": {
    "token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expiresIn": 3600
  }
}
```

---

### **POST** `/api/invoice/sign`
**Descripción**: Firmar XML de factura (sin enviar a DGII)
**Body**:
```json
{
  "xmlData": "<ECF>...</ECF>",
  "documentType": "ECF" // ECF | ACECF | ANECF | RFCE | ARECF
}
```
**Response**:
```json
{
  "success": true,
  "data": {
    "signedXml": "<ECF>...<Signature>...</Signature></ECF>",
    "securityCode": "ABC123"
  }
}
```

---

### **POST** `/api/invoice/send`
**Descripción**: Firmar y enviar factura completa a DGII
**Body**:
```json
{
  "invoiceData": {
    "ECF": {
      "Encabezado": {
        "Version": 1.0,
        "IdDoc": {
          "TipoeCF": 31,
          "eNCF": "E310005000201",
          "FechaVencimientoSecuencia": "31-12-2025",
          "IndicadorEnvioDiferido": 0,
          "IndicadorMontoGravado": 1,
          "TipoIngresos": "01",
          "TipoPago": 1
        },
        "Emisor": {
          "RNCEmisor": "130862346",
          "RazonSocialEmisor": "MI EMPRESA SRL",
          "DireccionEmisor": "Calle Principal #123",
          "FechaEmision": "09-12-2025"
        },
        "Comprador": {
          "RNCComprador": "123456789",
          "RazonSocialComprador": "CLIENTE SRL"
        },
        "Totales": {
          "MontoTotal": 11800.00,
          "MontoGravadoTotal": 10000.00,
          "TotalITBIS": 1800.00
        }
      },
      "DetallesItems": {
        "Item": [
          {
            "NumeroLinea": 1,
            "IndicadorFacturacion": 1,
            "NombreItem": "Producto de prueba",
            "CantidadItem": 1,
            "PrecioUnitarioItem": 10000.00,
            "MontoItem": 10000.00
          }
        ]
      },
      "Subtotales": {
        "Subtotal": [
          {
            "NumeroSubtotal": 1,
            "DescripcionSubtotal": "Operaciones Gravadas",
            "MontoSubtotal": 10000.00
          }
        ]
      }
    }
  },
  "rnc": "130862346",
  "encf": "E310005000201",
  "environment": "test"
}
```
**Response**:
```json
{
  "success": true,
  "data": {
    "trackId": "d2b6e27c-3908-46f3-afaa-2207b9501b4b",
    "codigo": "1",
    "estado": "Aceptado",
    "rnc": "130862346",
    "encf": "E310005000201",
    "fechaRecepcion": "9/12/2025 5:06:57 PM",
    "signedXml": "<ECF>...</ECF>",
    "securityCode": "ABC123",
    "qrCodeUrl": "https://..."
  }
}
```

---

### **POST** `/api/invoice/send-summary`
**Descripción**: Enviar resumen de factura de consumo < 250K (RFCE)
**Body**:
```json
{
  "invoiceData": {
    "ECF": {
      // Estructura de ECF tipo 32
    }
  },
  "rnc": "130862346",
  "encf": "E320005000201",
  "environment": "test"
}
```
**Response**:
```json
{
  "success": true,
  "data": {
    "trackId": "...",
    "signedEcfXml": "...", // XML del ECF original firmado
    "signedRfceXml": "...", // XML del resumen RFCE firmado
    "securityCode": "ABC123"
  }
}
```

---

### **GET** `/api/invoice/status/:trackId`
**Descripción**: Consultar estado de un documento por trackID
**Response**:
```json
{
  "success": true,
  "data": {
    "trackId": "d2b6e27c-3908-46f3-afaa-2207b9501b4b",
    "codigo": "1",
    "estado": "Aceptado",
    "rnc": "130862346",
    "encf": "E310005000201",
    "secuenciaUtilizada": true,
    "fechaRecepcion": "9/12/2025 5:06:57 PM",
    "mensajes": [
      {
        "valor": "Documento aceptado correctamente",
        "codigo": 0
      }
    ]
  }
}
```

---

### **GET** `/api/invoice/tracks/:rnc/:encf`
**Descripción**: Obtener todos los trackIDs asociados a un e-NCF
**Response**:
```json
{
  "success": true,
  "data": [
    {
      "trackId": "d2b6e27c-3908-...",
      "fechaEnvio": "9/12/2025 5:00:00 PM",
      "estado": "Aceptado"
    },
    {
      "trackId": "a1c3e45d-7890-...",
      "fechaEnvio": "9/12/2025 4:30:00 PM",
      "estado": "Rechazado"
    }
  ]
}
```

---

### **POST** `/api/invoice/inquire`
**Descripción**: Consultar validez/estado de un e-CF
**Body**:
```json
{
  "rncEmisor": "130862346",
  "encf": "E310005000201",
  "rncComprador": "123456789",
  "securityCode": "ABC123"
}
```
**Response**:
```json
{
  "success": true,
  "data": {
    "valido": true,
    "estado": "Vigente",
    "fechaEmision": "09-12-2025",
    "montoTotal": 11800.00
  }
}
```

---

### **POST** `/api/approval/send`
**Descripción**: Enviar aprobación comercial (receptor confirma recepción)
**Body**:
```json
{
  "approvalData": {
    "ACECF": {
      "DetalleAprobacionComercial": {
        "Version": "1.0",
        "RNCEmisor": "131880738",
        "RNCComprador": "130862346",
        "eNCF": "E310000000007",
        "FechaEmision": "09-12-2025",
        "MontoTotal": 11800.00,
        "Estado": "1", // 1: Aceptado, 2: Rechazado
        "FechaHoraAprobacionComercial": "09-12-2025 17:30:45"
      }
    }
  },
  "fileName": "130862346E310000000007.xml"
}
```

---

### **POST** `/api/void/send`
**Descripción**: Anular rangos de secuencias (e-NCF) no utilizados
**Body**:
```json
{
  "voidData": {
    "ANECF": {
      "DetalleAnulacion": {
        "Version": "1.0",
        "RNCEmisor": "130862346",
        "TipoeCF": "31",
        "TablaRangoSecuencia": {
          "RangoSecuencia": [
            {
              "Desde": "E310005000100",
              "Hasta": "E310005000150"
            }
          ]
        }
      }
    }
  },
  "fileName": "130862346ANULACION.xml"
}
```

---

### **GET** `/api/customer/directory/:rnc`
**Descripción**: Obtener URLs de servicio de un cliente autorizado
**Response**:
```json
{
  "success": true,
  "data": [
    {
      "rnc": "123456789",
      "urls": [
        "https://cliente.com/fe/recepcion/api/ecf"
      ]
    }
  ]
}
```

---

### **GET** `/api/qr/generate`
**Descripción**: Generar código QR para factura
**Query params**:
- `rncEmisor`: RNC del emisor
- `rncComprador`: RNC del comprador (opcional para FC)
- `encf`: Número de e-NCF
- `amount`: Monto total
- `securityCode`: Código de seguridad
- `fechaEmision`: Fecha de emisión (para ECF)
- `fechaFirma`: Fecha de firma (para ECF)
- `environment`: test | cert | prod

**Response**:
```json
{
  "success": true,
  "data": {
    "qrCodeUrl": "https://dgii.gov.do/ecf/qr?data=..."
  }
}
```

---

### **GET** `/api/certificate/info`
**Descripción**: Obtener información del certificado .p12 actual
**Response**:
```json
{
  "success": true,
  "data": {
    "subject": "CN=EMPRESA SRL, OU=...",
    "issuer": "CN=DIGIFIRMA CA, O=...",
    "validFrom": "2024-01-01T00:00:00Z",
    "validTo": "2026-01-01T00:00:00Z",
    "serialNumber": "1234567890",
    "daysUntilExpiration": 365
  }
}
```

---

## 🔄 Flujo de Integración con Odoo

### Diagrama de Secuencia

```
Odoo                    Microservicio             DGII
  |                           |                     |
  |---(1) POST /auth/dgii---->|                     |
  |                           |---(2) GET seed----->|
  |                           |<--(3) seed XML------|
  |                           |---(4) Sign seed---->|
  |                           |<--(5) Token---------|
  |<--(6) Return token--------|                     |
  |                           |                     |
  |---(7) POST /invoice/send->|                     |
  |                           |--(8) Convert JSON-->|
  |                           |--(9) Sign XML------>|
  |                           |---(10) Send XML---->|
  |                           |<--(11) TrackID------|
  |<--(12) Return response----|                     |
  |                           |                     |
  |-(13) Save trackID in DB-->|                     |
  |                           |                     |
  |---(14) GET /status/xxx--->|                     |
  |                           |---(15) Query------->|
  |                           |<--(16) Status-------|
  |<--(17) Return status------|                     |
```

---

### Código Python para Odoo

```python
# -*- coding: utf-8 -*-
import requests
import json
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    # Campos adicionales para e-CF
    encf = fields.Char(string='e-NCF', readonly=True)
    dgii_track_id = fields.Char(string='DGII Track ID', readonly=True)
    dgii_estado = fields.Selection([
        ('draft', 'Borrador'),
        ('pending', 'Enviado - Pendiente'),
        ('accepted', 'Aceptado'),
        ('rejected', 'Rechazado'),
    ], string='Estado DGII', default='draft')
    dgii_signed_xml = fields.Text(string='XML Firmado', readonly=True)
    dgii_security_code = fields.Char(string='Código de Seguridad', readonly=True)
    dgii_qr_url = fields.Char(string='URL Código QR', readonly=True)

    # Configuración del microservicio
    MICROSERVICE_URL = 'http://localhost:3000/api'
    DGII_ENVIRONMENT = 'test'  # test | cert | prod

    def _get_dgii_invoice_data(self):
        """Construir JSON en formato DGII desde factura Odoo"""
        self.ensure_one()

        # Calcular totales
        subtotal_gravado = sum(
            line.price_subtotal
            for line in self.invoice_line_ids
            if line.tax_ids
        )
        total_itbis = sum(
            tax.amount
            for line in self.invoice_line_ids
            for tax in line.tax_ids
        )

        # Construir items
        items = []
        for idx, line in enumerate(self.invoice_line_ids, start=1):
            items.append({
                "NumeroLinea": idx,
                "IndicadorFacturacion": 1,
                "NombreItem": line.name,
                "CantidadItem": line.quantity,
                "PrecioUnitarioItem": line.price_unit,
                "MontoItem": line.price_subtotal,
            })

        # Estructura completa ECF
        invoice_data = {
            "ECF": {
                "Encabezado": {
                    "Version": 1.0,
                    "IdDoc": {
                        "TipoeCF": 31,  # 31: Crédito Fiscal, 32: Consumo
                        "eNCF": self.encf or self._generate_encf(),
                        "FechaVencimientoSecuencia": "31-12-2025",
                        "IndicadorEnvioDiferido": 0,
                        "IndicadorMontoGravado": 1,
                        "TipoIngresos": "01",
                        "TipoPago": 1,
                    },
                    "Emisor": {
                        "RNCEmisor": self.company_id.vat,
                        "RazonSocialEmisor": self.company_id.name,
                        "DireccionEmisor": self.company_id.street,
                        "FechaEmision": self.invoice_date.strftime("%d-%m-%Y"),
                        "CorreoEmisor": self.company_id.email,
                    },
                    "Comprador": {
                        "RNCComprador": self.partner_id.vat,
                        "RazonSocialComprador": self.partner_id.name,
                        "DireccionComprador": self.partner_id.street,
                    },
                    "Totales": {
                        "MontoTotal": self.amount_total,
                        "MontoGravadoTotal": subtotal_gravado,
                        "TotalITBIS": total_itbis,
                    }
                },
                "DetallesItems": {
                    "Item": items
                },
                "Subtotales": {
                    "Subtotal": [
                        {
                            "NumeroSubtotal": 1,
                            "DescripcionSubtotal": "Operaciones Gravadas",
                            "MontoSubtotal": subtotal_gravado,
                        }
                    ]
                }
            }
        }

        return invoice_data

    def action_send_to_dgii(self):
        """Enviar factura a DGII a través del microservicio"""
        self.ensure_one()

        if not self.encf:
            raise UserError('Debe generar un e-NCF antes de enviar a DGII')

        try:
            # 1. Construir datos de la factura
            invoice_data = self._get_dgii_invoice_data()

            # 2. Enviar al microservicio
            response = requests.post(
                f'{self.MICROSERVICE_URL}/invoice/send',
                json={
                    'invoiceData': invoice_data,
                    'rnc': self.company_id.vat,
                    'encf': self.encf,
                    'environment': self.DGII_ENVIRONMENT
                },
                timeout=30
            )

            response.raise_for_status()
            result = response.json()

            if result['success']:
                data = result['data']

                # 3. Guardar respuesta en Odoo
                self.write({
                    'dgii_track_id': data['trackId'],
                    'dgii_estado': 'pending' if data['codigo'] == '0' else 'accepted',
                    'dgii_signed_xml': data['signedXml'],
                    'dgii_security_code': data['securityCode'],
                    'dgii_qr_url': data.get('qrCodeUrl'),
                })

                _logger.info(f"Factura {self.name} enviada a DGII. TrackID: {data['trackId']}")

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Enviado a DGII',
                        'message': f"TrackID: {data['trackId']}",
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(f"Error: {result.get('error', 'Desconocido')}")

        except requests.RequestException as e:
            _logger.error(f"Error conectando con microservicio: {str(e)}")
            raise UserError(f'Error de conexión con el microservicio: {str(e)}')

    def action_check_dgii_status(self):
        """Consultar estado en DGII"""
        self.ensure_one()

        if not self.dgii_track_id:
            raise UserError('No hay trackID para consultar')

        try:
            response = requests.get(
                f'{self.MICROSERVICE_URL}/invoice/status/{self.dgii_track_id}',
                timeout=10
            )

            response.raise_for_status()
            result = response.json()

            if result['success']:
                data = result['data']

                # Mapear estados
                estado_map = {
                    '0': 'pending',
                    '1': 'accepted',
                    '2': 'rejected',
                }

                self.dgii_estado = estado_map.get(data['codigo'], 'pending')

                _logger.info(f"Estado actualizado para {self.name}: {data['estado']}")

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Estado DGII',
                        'message': f"Estado: {data['estado']}",
                        'type': 'success' if self.dgii_estado == 'accepted' else 'warning',
                    }
                }

        except requests.RequestException as e:
            raise UserError(f'Error consultando estado: {str(e)}')

    def _generate_encf(self):
        """Generar número de e-NCF secuencial"""
        # Implementar lógica de secuencia según tipo de comprobante
        # Formato: E + TipoCF (31/32) + Establecimiento (3) + Punto (3) + Secuencial (8)
        # Ejemplo: E310005000201
        pass

    # Cron job para actualizar estados automáticamente
    @api.model
    def _cron_update_dgii_status(self):
        """Actualizar estados de facturas pendientes en DGII"""
        pending_invoices = self.search([
            ('dgii_estado', 'in', ['pending']),
            ('dgii_track_id', '!=', False)
        ])

        for invoice in pending_invoices:
            try:
                invoice.action_check_dgii_status()
            except Exception as e:
                _logger.error(f"Error actualizando {invoice.name}: {str(e)}")
```

---

### Vista XML para Odoo

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Formulario de factura con campos DGII -->
    <record id="view_move_form_dgii" model="ir.ui.view">
        <field name="name">account.move.form.dgii</field>
        <field name="model">account.move</field>
        <field name="inherit_id" ref="account.view_move_form"/>
        <field name="arch" type="xml">
            <xpath expr="//header" position="inside">
                <button name="action_send_to_dgii"
                        string="Enviar a DGII"
                        type="object"
                        class="oe_highlight"
                        attrs="{'invisible': [('dgii_estado', '!=', 'draft')]}"/>
                <button name="action_check_dgii_status"
                        string="Consultar Estado"
                        type="object"
                        attrs="{'invisible': [('dgii_track_id', '=', False)]}"/>
                <field name="dgii_estado" widget="statusbar"/>
            </xpath>

            <xpath expr="//page[@name='other_info']" position="after">
                <page string="DGII - Facturación Electrónica">
                    <group>
                        <group>
                            <field name="encf" readonly="1"/>
                            <field name="dgii_track_id" readonly="1"/>
                            <field name="dgii_security_code" readonly="1"/>
                        </group>
                        <group>
                            <field name="dgii_estado"/>
                            <field name="dgii_qr_url" widget="url" readonly="1"/>
                        </group>
                    </group>
                    <group string="XML Firmado">
                        <field name="dgii_signed_xml" widget="text" readonly="1"/>
                    </group>
                </page>
            </xpath>
        </field>
    </record>

    <!-- Cron job para actualizar estados -->
    <record id="ir_cron_update_dgii_status" model="ir.cron">
        <field name="name">Actualizar Estados DGII</field>
        <field name="model_id" ref="account.model_account_move"/>
        <field name="state">code</field>
        <field name="code">model._cron_update_dgii_status()</field>
        <field name="interval_number">15</field>
        <field name="interval_type">minutes</field>
        <field name="numbercall">-1</field>
        <field name="active" eval="True"/>
    </record>
</odoo>
```

---

## 📅 Fases de Implementación

### **Fase 1: Setup del Microservicio** (2-3 días)

#### Tareas:
- [ ] Crear proyecto Node.js con Express + TypeScript
- [ ] Instalar dependencias: `dgii-ecf`, `express`, `cors`, `dotenv`
- [ ] Configurar estructura de carpetas (controllers, services, routes, utils)
- [ ] Implementar manejo de variables de entorno
- [ ] Crear endpoints básicos:
  - `POST /api/auth/dgii`
  - `POST /api/invoice/sign`
  - `POST /api/invoice/send`
  - `GET /api/invoice/status/:trackId`
- [ ] Implementar middleware de error handling
- [ ] Agregar logging con Winston o similar
- [ ] Crear Dockerfile
- [ ] Escribir README con documentación de API

#### Entregables:
- Microservicio funcional con endpoints básicos
- Documentación de API (Postman collection)
- Docker image

---

### **Fase 2: Integración con Odoo** (3-4 días)

#### Tareas:
- [ ] Crear módulo custom en Odoo: `odoo_dgii_ecf`
- [ ] Extender modelo `account.move` con campos DGII
- [ ] Implementar método `_get_dgii_invoice_data()` para mapeo
- [ ] Crear método `action_send_to_dgii()` con llamada HTTP
- [ ] Crear método `action_check_dgii_status()`
- [ ] Diseñar vistas XML para botones y campos
- [ ] Implementar generación de e-NCF secuencial
- [ ] Manejar errores y excepciones
- [ ] Agregar validaciones de datos
- [ ] Crear cron job para actualizar estados

#### Entregables:
- Módulo Odoo instalable
- Integración funcional Odoo ↔ Microservicio
- Documentación de usuario

---

### **Fase 3: Funcionalidades Avanzadas** (2-3 días)

#### Tareas:
- [ ] Implementar facturas de consumo < 250K (RFCE)
- [ ] Agregar notas de crédito/débito
- [ ] Implementar aprobaciones comerciales
- [ ] Generar códigos QR automáticamente
- [ ] Crear webhook para notificaciones de DGII (si disponible)
- [ ] Implementar consulta de directorio de clientes
- [ ] Agregar anulación de rangos de e-NCF
- [ ] Crear reportes en Odoo:
  - Facturas enviadas a DGII
  - Facturas rechazadas
  - Estadísticas de facturación
- [ ] Implementar retry automático en caso de error
- [ ] Agregar caché de tokens de autenticación

#### Entregables:
- Funcionalidades completas según normativa DGII
- Reportes de seguimiento
- Sistema resiliente con reintentos

---

### **Fase 4: Testing y Certificación** (2-3 días)

#### Tareas:
- [ ] Pruebas unitarias del microservicio (Jest)
- [ ] Pruebas de integración Odoo ↔ Microservicio
- [ ] Pruebas en ambiente TesteCF de DGII
- [ ] Validar todos los tipos de comprobantes
- [ ] Probar casos de error y recuperación
- [ ] Documentar casos de prueba
- [ ] Solicitar certificación con DGII (ambiente CerteCF)
- [ ] Pasar pruebas de certificación
- [ ] Preparar ambiente de producción
- [ ] Configurar monitoreo y alertas
- [ ] Crear manual de usuario final
- [ ] Deploy a producción

#### Entregables:
- Suite de pruebas completa
- Certificación DGII aprobada
- Sistema en producción
- Documentación completa

---

## 🎯 Decisiones Técnicas

### 1. **Almacenamiento del Certificado .p12**

#### Opción A: En el servidor del microservicio (RECOMENDADO)
**Ventajas**:
- ✅ Mayor seguridad (el certificado nunca viaja por la red)
- ✅ Más simple de implementar
- ✅ Mejor rendimiento (no se envía en cada request)

**Desventajas**:
- ⚠️ Requiere acceso al filesystem del servidor
- ⚠️ Si hay múltiples empresas, necesitas múltiples certificados

**Implementación**:
```javascript
// .env
CERTIFICATE_PATH=/app/certificates/empresa.p12
CERTIFICATE_PASSWORD=mipassword
```

---

#### Opción B: Odoo lo envía en cada request
**Ventajas**:
- ✅ Más flexible para múltiples empresas
- ✅ No requiere storage en microservicio

**Desventajas**:
- ❌ Menos seguro (certificado viaja por la red)
- ❌ Mayor payload en cada request
- ❌ Más complejo de implementar

---

**Decisión Final**: **Opción A** - Almacenar en servidor con variables de entorno

---

### 2. **Manejo de Múltiples RNCs/Empresas**

#### Opción A: Un microservicio por RNC
**Ventajas**:
- ✅ Aislamiento total entre empresas
- ✅ Más fácil de escalar

**Desventajas**:
- ❌ Más recursos (un servidor por empresa)
- ❌ Más difícil de mantener

---

#### Opción B: Microservicio multi-tenant (RECOMENDADO)
**Ventajas**:
- ✅ Un solo servidor para todas las empresas
- ✅ Más eficiente en recursos
- ✅ Más fácil de actualizar

**Desventajas**:
- ⚠️ Requiere lógica adicional para seleccionar certificado

**Implementación**:
```javascript
// Estructura de certificados
/app/certificates/
  ├── 130862346.p12  // RNC empresa 1
  ├── 131880738.p12  // RNC empresa 2
  └── ...

// En el request
{
  "rnc": "130862346",  // Selecciona el certificado correcto
  "invoiceData": {...}
}
```

---

**Decisión Final**: **Opción B** - Microservicio multi-tenant

---

### 3. **Ambiente de DGII a usar**

| Ambiente | URL Base | Propósito | Cuándo usar |
|----------|----------|-----------|-------------|
| **TesteCF** | `https://ecf.dgii.gov.do/TesteCF/` | Desarrollo | ✅ Desarrollo inicial, pruebas internas |
| **CerteCF** | `https://ecf.dgii.gov.do/CerteCF/` | Certificación | ✅ Antes de producción, requiere aprobación DGII |
| **eCF** | `https://ecf.dgii.gov.do/eCF/` | Producción | ✅ Solo después de certificación |

**Decisión Final**: Comenzar con **TesteCF**, certificar en **CerteCF**, deploy en **eCF**

---

### 4. **Stack Tecnológico del Microservicio**

```javascript
{
  "framework": "Express",           // Rápido y simple
  "language": "TypeScript",         // Type safety
  "testing": "Jest",                // Testing robusto
  "logging": "Winston",             // Logs estructurados
  "validation": "Joi",              // Validación de requests
  "documentation": "Swagger/OpenAPI", // Auto-documentación API
  "deployment": "Docker + Docker Compose",
  "monitoring": "PM2 + CloudWatch/Datadog"
}
```

---

### 5. **Seguridad**

#### Medidas a implementar:
- ✅ HTTPS obligatorio
- ✅ API Key para autenticación entre Odoo y microservicio
- ✅ Rate limiting (prevenir abuso)
- ✅ Certificados .p12 encriptados en disco
- ✅ Logs de auditoría de todas las operaciones
- ✅ Validación estricta de inputs (Joi schemas)
- ✅ Secrets en variables de entorno (nunca en código)
- ✅ Firewall: solo permitir IPs de servidores Odoo

```javascript
// Middleware de autenticación
app.use((req, res, next) => {
  const apiKey = req.headers['x-api-key'];
  if (apiKey !== process.env.ODOO_API_KEY) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
});
```

---

## 🚀 Próximos Pasos

### Inmediatos (Esta semana)
1. ✅ Instalar Node.js y dependencias
2. ✅ Crear proyecto del microservicio
3. ✅ Implementar endpoint básico de autenticación
4. ✅ Probar firma de XML con certificado de prueba
5. ✅ Validar conexión con TesteCF de DGII

---

### Corto plazo (Próximas 2 semanas)
1. ✅ Completar todos los endpoints del microservicio
2. ✅ Crear módulo Odoo básico
3. ✅ Implementar envío de primera factura de prueba
4. ✅ Dockerizar microservicio
5. ✅ Documentar API con Swagger

---

### Mediano plazo (Mes 1)
1. ✅ Completar todas las funcionalidades (notas, aprobaciones, etc)
2. ✅ Implementar suite de pruebas
3. ✅ Optimizar manejo de errores y retry
4. ✅ Agregar monitoreo y alertas
5. ✅ Solicitar certificación DGII

---

### Largo plazo (Mes 2+)
1. ✅ Pasar certificación DGII
2. ✅ Deploy a producción
3. ✅ Capacitar usuarios
4. ✅ Monitorear y optimizar
5. ✅ Agregar nuevas funcionalidades según necesidad

---

## 📚 Recursos Adicionales

### Documentación Oficial
- [DGII - Facturación Electrónica](https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Paginas/default.aspx)
- [Documentación Técnica DGII](https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Paginas/documentacionSobreE-CF.aspx)
- [dgii-ecf GitHub](https://github.com/victors1681/dgii-ecf)
- [dgii-ecf NPM](https://www.npmjs.com/package/dgii-ecf)
- [Video Tutorial](https://youtu.be/J_D2VBJscxI)

### Herramientas
- [Solicitar Certificado DigiFirma](https://www.camarasantodomingo.do/digifirma/FormularioWeb/)
- [Postman](https://www.postman.com/) - Testing de API
- [Docker](https://www.docker.com/) - Containerización
- [PM2](https://pm2.keymetrics.io/) - Process Manager

---

## 📞 Contacto y Soporte

### Autor de dgii-ecf
- **Victor Santos**
- GitHub: [@victors1681](https://github.com/victors1681)
- Portafolio: [vsantos.info](https://vsantos.info)

### Servicio Cloud
Si deseas ahorrar tiempo, existe un servicio cloud listo para usar:
- [ecf.mseller.app](https://ecf.mseller.app)

---

## 📝 Notas Finales

### Consideraciones Importantes

1. **Certificado Digital**: Es OBLIGATORIO tener un certificado .p12 válido emitido por DigiFirma
2. **Ambiente de Pruebas**: Siempre comenzar en TesteCF antes de ir a producción
3. **Certificación DGII**: Es un proceso obligatorio antes de usar en producción
4. **Mantenimiento**: La librería dgii-ecf se actualiza regularmente, mantener al día
5. **Backup**: Siempre guardar los XMLs firmados para auditoría

---

### Checklist de Inicio

Antes de comenzar la implementación, asegúrate de tener:

- [ ] Certificado .p12 válido
- [ ] Password del certificado
- [ ] RNC de la empresa
- [ ] Acceso al ambiente TesteCF de DGII
- [ ] Servidor para el microservicio (o Docker)
- [ ] Instancia de Odoo funcionando
- [ ] Conocimientos básicos de Node.js y Python

---

### Preguntas Frecuentes

**P: ¿Puedo usar esto sin Odoo?**
R: Sí, el microservicio es independiente. Puedes consumirlo desde cualquier sistema.

**P: ¿Cuánto cuesta el certificado?**
R: Aproximadamente 3,000 - 5,000 DOP anuales en DigiFirma.

**P: ¿Cuánto tiempo toma la certificación?**
R: Depende de DGII, usualmente 1-2 semanas.

**P: ¿Funciona para múltiples empresas?**
R: Sí, siguiendo el patrón multi-tenant explicado arriba.

**P: ¿Qué pasa si DGII está caído?**
R: Implementar retry automático y queue de mensajes para reintentar después.

---

## 🎉 ¡Listo para comenzar!

Este plan proporciona una ruta clara para implementar facturación electrónica DGII en Odoo.

**Siguiente paso recomendado**: Crear el proyecto del microservicio y probar la autenticación con DGII.

---

*Documento creado: 2025-12-09*
*Última actualización: 2025-12-09*
*Versión: 1.0*
