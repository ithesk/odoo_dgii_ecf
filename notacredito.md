Objetivo del flujo
Emitir Nota de Crédito e-CF tipo 34 referenciando un e-CF anterior (normalmente 32 consumo).
Guardarla como crédito disponible (saldo a favor).
En una venta futura (nueva factura consumo 32), permitir aplicar el crédito como FormaPago = 7 “Nota de crédito”, cobrando solo la diferencia

2) Entidades / campos que deben existir (mínimos)
A) account.move (Factura / NC)
l10n_do_ecf_tipo (Selection: 31/32/34/…)
l10n_do_ecf_en_cf (e-NCF)
l10n_do_ecf_fecha_emision
l10n_do_ecf_estado_dgii (draft/xml_built/signed/sent/accepted/rejected)
l10n_do_ecf_xml_signed_attachment_id
l10n_do_ecf_track_id / l10n_do_ecf_response
Campos extra solo para NC (move_type=out_refund, tipo 34)
l10n_do_ecf_ref_move_id (Factura original)
l10n_do_ecf_ncf_modificado (e-NCF original)
l10n_do_ecf_fecha_ncf_modificado
l10n_do_ecf_codigo_modificacion
l10n_do_ecf_indicador_nota_credito (0/1) (computed por días) 
Formato Comprobante Fiscal Elec…
l10n_do_credit_balance_total (saldo total)
l10n_do_credit_balance_available (saldo disponible)
l10n_do_credit_state (available/partial/consumed/void)
B) Registro de aplicación del crédito (nuevo modelo)
l10n_do.ecf.credit.application
credit_move_id (NC 34)
invoice_move_id (Factura nueva 32)
amount_applied
date_applied
pos_order_id (si aplica)
user_id
Esto evita doble uso y audita.

3) Flujo 1: Generar la Nota de Crédito (34)
A) Desde factura original (32)
Botón: “Crear Nota de Crédito e-CF (34)”
Wizard (obligatorio)
ref_invoice_id (autollena)
tipo (total/parcial)
líneas/cantidades (si parcial)
codigo_modificacion (01/03/04/05…)
“Con devolución de inventario” (sí/no) (si tienes stock)
Acciones
(Opcional) Ejecutar stock.return.picking si devolución física.
Crear account.move reversal (out_refund).
Setear:
l10n_do_ecf_tipo = 34
l10n_do_ecf_ref_move_id = factura_original
l10n_do_ecf_ncf_modificado = factura_original.eNCF
l10n_do_ecf_fecha_ncf_modificado = factura_original.fecha_emision
l10n_do_ecf_codigo_modificacion = wizard.codigo_modificacion
l10n_do_ecf_indicador_nota_credito:
0 si ≤30 días
1 si >30 días 
Formato Comprobante Fiscal Elec…
Validaciones antes de firmar/enviar
NC debe tener referencia a e-CF original (si no, bloquear).
Monto NC ≤ monto e-CF original (y sumatoria de NC ≤ original) (regla interna fuerte).
Si >30 días: marcar indicador=1 y aplicar lógica fiscal interna acorde (sin rebajar ITBIS) 
Formato Comprobante Fiscal Elec…
.
Flujo 2: Aplicar la Nota de Crédito en una nueva Factura de Consumo (32)
A) Punto de entrada: POS o Sales
En POS (recomendado)
En pantalla de pago → botón: “Aplicar Nota de Crédito”
El sistema solicita (mínimo):
e-NCF de la Nota de Crédito (E34...) (input)
monto a aplicar (default: min(saldo_disponible, total_factura))
Validaciones:
Existe NC tipo 34, estado DGII aceptado.
credit_state available/partial.
credit_balance_available > 0
Monto a aplicar ≤ saldo disponible
Monto a aplicar ≤ total factura
Bloqueo de concurrencia (SQL constraint/locking) para evitar doble canje simultáneo.

C) Contabilidad (Odoo)
No registrar la NC como “pago normal” (banco/caja) si tu implementación lo complica.
Lo correcto es:
Crear la factura 32.
Registrar un “pago” interno o asiento puente (según tu arquitectura) que:
reduzca el saldo de la factura por el monto aplicado
reduzca el saldo disponible de la NC (y la concilie/relacione)
Insertar en l10n_do.ecf.credit.application el vínculo NC→Factura y monto.
Resultado:
Cliente paga solo diferencia.
NC queda partial/consumed.




Flujo correcto en Odoo: Nota de Crédito (34) + Uso como crédito en Factura Consumo (32)
1) Objetivo funcional
Emitir Nota de Crédito e-CF 34 por devolución (total o parcial) referenciando la factura original.
Guardarla como crédito disponible para el cliente consumo.
En una compra futura, aplicar ese crédito para pagar parte de la nueva factura, registrándolo como Forma de Pago = 7 (Nota de crédito) 
Formato Resumen Factura Consumo…
.
2) Datos y modelos (mínimos)
A) account.move (Factura/NC)
Campos:
l10n_do_ecf_tipo (32 o 34)
l10n_do_ecf_en_cf (e-NCF)
l10n_do_ecf_fecha_emision
l10n_do_ecf_estado_dgii (draft/sent/accepted/rejected)
l10n_do_ecf_json_payload (texto o attachment: el JSON que se generó)
Solo para Nota de Crédito (move_type=out_refund, tipo 34)
l10n_do_ecf_ref_move_id (Factura original)
l10n_do_ecf_ncf_modificado (e-NCF original)
l10n_do_ecf_fecha_ncf_modificado
l10n_do_ecf_codigo_modificacion
l10n_do_ecf_indicador_nota_credito (0/1 si >30 días)
B) Control de crédito (recomendado)
Modelo nuevo: l10n_do.ecf_credit
credit_move_id (Many2one a la NC 34)
partner_id (cliente; si POS no usa partner, usar cliente genérico + teléfono)
amount_total
amount_available
state (available/partial/consumed/void)
Modelo nuevo: l10n_do.ecf_credit_application
credit_id
invoice_move_id (Factura donde se aplicó)
amount_applied
date_applied
pos_order_id (si aplica)
user_id
3) Flujo 1 — Crear Nota de Crédito (34) por devolución
A) Entrada (desde factura 32)
Botón en factura: “Crear Nota de Crédito e-CF (34)”
Wizard
tipo: total/parcial
líneas y cantidades (si parcial)
codigo_modificacion (devolución / descuento / corrección)
(opcional) “generar devolución de inventario” si aplica
B) Acciones
(Opcional) generar devolución logística (stock.return.picking).
Crear account.move tipo out_refund.
Setear campos de referencia:
ref_move_id = factura_original
ncf_modificado = factura_original.eNCF
fecha_ncf_modificado = factura_original.fecha_emision
codigo_modificacion = wizard.codigo_modificacion
Calcular indicador_nota_credito:
0 si fecha_nc - fecha_factura <= 30 días
1 si > 30 días
C) Validaciones duras
No permitir NC 34 sin referencia.
NC ≤ factura y sumatoria NC ≤ factura.
Si la NC está “available” para uso comercial solo cuando estado_dgii = accepted.
D) Generación de JSON e-CF 34
Odoo genera y guarda l10n_do_ecf_json_payload con:
Encabezado (TipoeCF=34, eNCF, fechas)
Emisor
Comprador (si aplica)
Detalles/ítems
Totales
Información de referencia:
NCFModificado
FechaNCFModificado
CodigoModificacion
IndicadorNotaCredito (0/1)
Luego marca estado interno: payload_ready.
E) Publicar el crédito
Cuando la NC esté aceptada (según tu estado interno):
Crear/actualizar l10n_do.ecf_credit:
amount_total = monto_nc
amount_available = monto_nc
state = available
4) Flujo 2 — Aplicar NC como crédito en una nueva Factura de Consumo (32)
A) Entrada (POS o Ventas)
En POS (pantalla de pago) botón: “Aplicar Nota de Crédito”
El sistema debe pedir:
Número de NC (e-NCF de la 34) (ej: E34...)
Monto a aplicar (por defecto: min(saldo disponible, total a pagar))
B) Validaciones
Existe NC 34 aceptada.
Tiene un crédito available/partial con saldo.
Monto a aplicar:
≤ saldo disponible
≤ total factura
Bloqueo de concurrencia para evitar doble uso (importante en POS).
C) Cómo se refleja en la factura (lo correcto DGII)
En el JSON de la nueva factura 32:
En TablaFormasPago incluir:
FormaPago = 7 “Nota de crédito” por el monto aplicado 
Formato Resumen Factura Consumo…
otra forma de pago por el restante (efectivo/tarjeta)
La tabla se compone por pares FormaPago + MontoPago. 
Formato Resumen Factura Consumo…
Ejemplo conceptual (JSON):
formas_pago:
{ "forma": 7, "monto": 1000, "ref_nc": "E34..." }
{ "forma": 1, "monto": 1000 }
D) Registrar la aplicación del crédito
Al confirmar la factura:
Crear registro credit_application (NC → factura) con el monto aplicado.
Reducir amount_available.
Si amount_available == 0 → state = consumed, si no partial.
5) Flujo 3 — Reglas de reversión / anulaciones (imprescindible)
Si la factura donde aplicaste el crédito se cancela:
Crear una “reversión de aplicación”:
devolver saldo al crédito
marcar el credit_application como reversado/anulado
Evitar que el crédito se pierda.
6) Checklist final para el agente
Wizard NC 34 desde factura 32 (total/parcial + motivo).
Campos de referencia obligatorios en la NC.
Construcción JSON e-CF 34 con referencia e indicador >30 días.
Modelo ecf_credit + ecf_credit_application.
POS: “Aplicar Nota de Crédito” pidiendo e-NCF de NC.
Factura 32: registrar FormaPago=7 por monto aplicado 
Formato Resumen Factura Consumo…
.
Control de doble uso (locking).
Reversión al cancelar factura.