# Formato e-NCF según Normativa DGII

## Estructura del e-NCF

Según la normativa de la DGII de República Dominicana, el formato del e-NCF (Comprobante Fiscal Electrónico) es:

```
E + TipoECF(2) + Secuencial(10) = 13 caracteres
```

### Componentes:

1. **Serie (1 carácter)**: `E`
   - Indica que es un comprobante electrónico

2. **Tipo de Comprobante (2 dígitos)**: `31`, `32`, `33`, etc.
   - Especifica el tipo de comprobante fiscal

3. **Secuencial (10 dígitos)**: `0000000001` hasta `9999999999`
   - Número correlativo del comprobante

### Ejemplos:

| e-NCF | Desglose | Descripción |
|-------|----------|-------------|
| `E310000000001` | E + 31 + 0000000001 | Factura de Crédito Fiscal #1 |
| `E310000000005` | E + 31 + 0000000005 | Factura de Crédito Fiscal #5 |
| `E320000000100` | E + 32 + 0000000100 | Factura de Consumo #100 |
| `E331234567890` | E + 33 + 1234567890 | Nota de Débito #1234567890 |
| `E349999999999` | E + 34 + 9999999999 | Nota de Crédito (último número posible) |

## Configuración en Odoo

### 1. Establecimiento y Punto de Emisión

**IMPORTANTE**: El establecimiento y punto de emisión **NO** forman parte del e-NCF generado.

Estos valores se usan únicamente para:
- Identificar el rango de secuencias autorizado por DGII
- Controlar qué rango usar según la ubicación física
- Permitir múltiples rangos por tipo de comprobante

**Ejemplo de configuración**:
- **Diario de Ventas Sucursal 1**:
  - Establecimiento: `001`
  - Punto de Emisión: `001`
  - Tipo e-CF: `31` (Crédito Fiscal)

- **Rango asociado**:
  - Tipo: `31`
  - Establecimiento: `001`
  - Punto de Emisión: `001`
  - Secuencia desde: `1`
  - Secuencia hasta: `10000000`

**e-NCF generado**: `E310000000001`, `E310000000002`, etc.

### 2. Múltiples Rangos

Puedes tener varios rangos para el mismo tipo de comprobante pero diferentes ubicaciones:

**Sucursal A**:
- Establecimiento: `001`, Punto: `001`
- Genera: `E310000000001` hasta `E310000010000`

**Sucursal B**:
- Establecimiento: `002`, Punto: `001`
- Genera: `E310000010001` hasta `E310000020000`

Aunque el e-NCF no incluye el establecimiento/punto, estos aseguran que cada sucursal use su rango específico autorizado.

## Validaciones Implementadas

El módulo valida automáticamente:

1. ✅ **Longitud exacta de 13 caracteres**
   - Si el e-NCF generado no tiene 13 caracteres, se rechaza

2. ✅ **Formato correcto**
   - Comienza con 'E'
   - 2 dígitos para tipo de comprobante
   - 10 dígitos para secuencial

3. ✅ **Rango autorizado**
   - El secuencial debe estar dentro del rango autorizado por DGII
   - Control de vencimiento de autorización
   - Detección de rangos agotados

4. ✅ **Unicidad**
   - No se pueden generar e-NCF duplicados
   - Locking concurrente para evitar race conditions

## Generación Automática

El sistema genera automáticamente el e-NCF cuando:

1. Se confirma una factura (`state = 'posted'`)
2. El diario tiene tipos e-CF configurados
3. Existe un rango válido y activo
4. El cliente cumple los requisitos del tipo de comprobante

**Selección inteligente del tipo**:
- Cliente **con RNC** → Tipo 31 (Crédito Fiscal)
- Cliente **sin RNC** → Tipo 32 (Consumo)
- Nota de Crédito → Tipo 34
- Nota de Débito → Tipo 33

## Preguntas Frecuentes

### ¿Por qué el e-NCF no incluye establecimiento y punto de emisión?

Según la normativa DGII, el e-NCF es un identificador único a nivel nacional que solo requiere:
- Serie electrónica (E)
- Tipo de comprobante
- Número secuencial

El establecimiento y punto de emisión son datos administrativos que se usan internamente para:
- Identificar de qué rango tomar el siguiente número
- Permitir autorizar múltiples rangos por ubicación
- Control de auditoría

### ¿Cuántos e-NCF puedo generar?

Con el formato de 10 dígitos para el secuencial, puedes generar hasta **9,999,999,999** comprobantes por tipo.

En la práctica, DGII autoriza rangos más pequeños (ej: 1 al 10,000,000) que debes renovar periódicamente.

### ¿Qué pasa si cambio de establecimiento?

El e-NCF generado sigue siendo el mismo formato. El establecimiento solo determina qué rango usar.

**Ejemplo**:
- Rango Est. 001: Secuencias 1-10000 → Genera `E310000000001` a `E310000010000`
- Rango Est. 002: Secuencias 10001-20000 → Genera `E310000010001` a `E310000020000`

Los e-NCF son únicos pero provienen de rangos diferentes autorizados por DGII.

## Referencias

- Norma General 01-2007 de la DGII (actualizada)
- Manual de Facturación Electrónica DGII
- Formato de 13 caracteres: E + Tipo(2) + Secuencial(10)
