# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """Extensión del modelo account.move para agregar generación de e-NCF."""
    _inherit = 'account.move'

    # ========== CAMPOS E-NCF ==========
    encf = fields.Char(
        string='e-NCF',
        copy=False,
        readonly=True,
        help='Número de Comprobante Fiscal Electrónico generado según normativa DGII',
        index=True
    )

    x_tipo_ecf_manual = fields.Selection(
        selection=[
            ('31', '31 – Factura de Crédito Fiscal'),
            ('32', '32 – Factura de Consumo'),
            ('33', '33 – Nota de Débito'),
            ('34', '34 – Nota de Crédito'),
            ('44', '44 – Régimen Especial'),
            ('45', '45 – Gubernamental'),
        ],
        string='Tipo de Comprobante',
        help='Seleccione manualmente el tipo de comprobante fiscal a generar.\n'
             'Si no selecciona ninguno, el sistema determinará automáticamente según el cliente.\n'
             '• Consumo (32): Para clientes sin RNC\n'
             '• Crédito Fiscal (31): Para clientes con RNC validado',
        copy=False
    )

    # ========== CAMPO COMPUTADO PARA ESTADO DE E-NCF ==========
    encf_state = fields.Selection(
        selection=[
            ('pending', 'Pendiente de Generar'),
            ('generated', 'e-NCF Generado'),
            ('sent', 'Enviado a DGII'),
        ],
        string='Estado e-NCF',
        compute='_compute_encf_state',
        store=True,
        help='Estado del proceso de facturación electrónica'
    )

    # ========== CAMPOS DE INTEGRACIÓN DGII ==========
    dgii_track_id = fields.Char(
        string='DGII Track ID',
        copy=False,
        readonly=True,
        help='Identificador de seguimiento devuelto por DGII/microservicio'
    )

    dgii_estado = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('pending', 'Pendiente'),
            ('accepted', 'Aceptado'),
            ('rejected', 'Rechazado'),
            ('error', 'Error'),
        ],
        string='Estado DGII',
        default='draft',
        copy=False,
        readonly=True,
        help='Estado reportado por DGII para este comprobante'
    )

    dgii_signed_xml = fields.Text(
        string='XML Firmado',
        copy=False,
        readonly=True,
        help='XML firmado devuelto por el microservicio'
    )

    dgii_security_code = fields.Char(
        string='Código de Seguridad',
        copy=False,
        readonly=True,
        help='Código de seguridad (hash) generado al firmar el e-CF'
    )

    dgii_qr_url = fields.Char(
        string='URL Código QR',
        copy=False,
        readonly=True,
        help='URL de código QR devuelta por DGII/microservicio'
    )

    dgii_response_message = fields.Text(
        string='Mensaje DGII',
        copy=False,
        readonly=True,
        help='Mensaje devuelto por DGII/microservicio (texto legible)'
    )

    dgii_response_raw = fields.Text(
        string='Respuesta DGII (JSON)',
        copy=False,
        readonly=True,
        help='Respuesta completa en JSON para auditoría'
    )

    dgii_last_status_date = fields.Datetime(
        string='Última Consulta DGII',
        copy=False,
        readonly=True,
        help='Fecha/hora de la última consulta de estado en DGII'
    )

    # ========== CAMPOS DE LOGS DE API ==========
    api_log_ids = fields.One2many(
        'ecf.api.log',
        'move_id',
        string='Logs de API',
        readonly=True,
    )
    api_log_count = fields.Integer(
        string='Cantidad de Logs',
        compute='_compute_api_log_count',
    )

    # ========== CAMPOS PARA NOTAS DE CRÉDITO/DÉBITO ==========
    x_ncf_modificado = fields.Char(
        string='NCF Modificado',
        copy=False,
        help='e-NCF de la factura original que se está modificando (para NC/ND)'
    )

    x_fecha_ncf_modificado = fields.Date(
        string='Fecha NCF Modificado',
        copy=False,
        help='Fecha de emisión del NCF original que se modifica'
    )

    x_codigo_modificacion = fields.Selection(
        selection=[
            ('1', '1 - Descuento completo'),
            ('2', '2 - Corrección de texto'),
            ('3', '3 - Corrección de monto'),
            ('4', '4 - Cambio de NCF'),
            ('5', '5 - Reemplazo de NCF por pago adelantado'),
        ],
        string='Código Modificación',
        copy=False,
        help='Motivo de la nota de crédito/débito según DGII'
    )

    x_razon_modificacion = fields.Char(
        string='Razón Modificación',
        copy=False,
        help='Descripción del motivo de la modificación'
    )

    # Referencia directa a la factura original (Many2one)
    x_ref_move_id = fields.Many2one(
        'account.move',
        string='Factura Original',
        copy=False,
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]",
        help='Factura original que se está modificando con esta NC/ND'
    )

    # Indicador de NC según días transcurridos (0=≤30 días, 1=>30 días)
    x_indicador_nota_credito = fields.Selection(
        selection=[
            ('0', '0 - Dentro de 30 días'),
            ('1', '1 - Más de 30 días'),
        ],
        string='Indicador NC',
        compute='_compute_indicador_nota_credito',
        store=True,
        help='Indicador según normativa DGII:\n'
             '0 = NC emitida dentro de 30 días de la factura original\n'
             '1 = NC emitida después de 30 días (sin rebajar ITBIS)'
    )

    # ========== CAMPOS DE CRÉDITO (para NC tipo 34) ==========
    credit_ids = fields.One2many(
        'l10n_do.ecf_credit',
        'credit_move_id',
        string='Créditos Generados',
        help='Créditos generados por esta Nota de Crédito'
    )

    credit_available = fields.Monetary(
        string='Crédito Disponible',
        compute='_compute_credit_info',
        currency_field='currency_id',
        help='Saldo de crédito disponible de esta NC'
    )

    credit_state = fields.Selection(
        selection=[
            ('no_credit', 'Sin Crédito'),
            ('available', 'Disponible'),
            ('partial', 'Parcialmente Usado'),
            ('consumed', 'Consumido'),
        ],
        string='Estado Crédito',
        compute='_compute_credit_info',
        help='Estado del crédito de esta NC'
    )

    # ========== CAMPOS DE CRÉDITOS APLICADOS (para facturas) ==========
    applied_credit_ids = fields.One2many(
        'l10n_do.ecf_credit_application',
        'invoice_move_id',
        string='Créditos Aplicados',
        help='Créditos de NC aplicados a esta factura'
    )

    applied_credit_total = fields.Monetary(
        string='Total Créditos Aplicados',
        compute='_compute_applied_credit_total',
        currency_field='currency_id',
        help='Suma de créditos de NC aplicados a esta factura'
    )

    # ========== CAMPOS ADICIONALES DGII ==========
    x_tipo_ingresos = fields.Selection(
        selection=[
            ('01', '01 - Ingresos por operaciones (No financieros)'),
            ('02', '02 - Ingresos financieros'),
            ('03', '03 - Ingresos extraordinarios'),
            ('04', '04 - Ingresos por arrendamientos'),
            ('05', '05 - Ingresos por venta de activo depreciable'),
            ('06', '06 - Otros ingresos'),
        ],
        string='Tipo de Ingresos',
        default='01',
        help='Clasificación del tipo de ingreso según DGII'
    )

    x_tipo_pago = fields.Selection(
        selection=[
            ('1', '1 - Contado'),
            ('2', '2 - Crédito'),
            ('3', '3 - Gratuito'),
        ],
        string='Tipo de Pago DGII',
        compute='_compute_tipo_pago',
        store=True,
        help='Tipo de pago para facturación electrónica'
    )

    # ========== MÉTODOS COMPUTADOS ==========
    @api.depends('invoice_payment_term_id')
    def _compute_tipo_pago(self):
        """Calcula el tipo de pago basado en el término de pago."""
        for move in self:
            if move.invoice_payment_term_id:
                # Si tiene término de pago, es crédito
                move.x_tipo_pago = '2'
            else:
                # Si no tiene término, es contado
                move.x_tipo_pago = '1'

    @api.depends('x_ref_move_id', 'x_fecha_ncf_modificado', 'invoice_date')
    def _compute_indicador_nota_credito(self):
        """
        Calcula el indicador de NC según días transcurridos desde factura original.
        0 = NC emitida dentro de 30 días
        1 = NC emitida después de 30 días
        """
        for move in self:
            if move.move_type != 'out_refund':
                move.x_indicador_nota_credito = False
                continue

            # Obtener fecha de la factura original
            fecha_original = None
            if move.x_ref_move_id and move.x_ref_move_id.invoice_date:
                fecha_original = move.x_ref_move_id.invoice_date
            elif move.x_fecha_ncf_modificado:
                fecha_original = move.x_fecha_ncf_modificado

            if not fecha_original:
                move.x_indicador_nota_credito = '0'  # Default
                continue

            # Fecha de la NC
            fecha_nc = move.invoice_date or fields.Date.context_today(move)

            # Calcular diferencia en días
            diferencia = (fecha_nc - fecha_original).days

            if diferencia > 30:
                move.x_indicador_nota_credito = '1'
            else:
                move.x_indicador_nota_credito = '0'

    @api.depends('credit_ids', 'credit_ids.amount_available', 'credit_ids.state')
    def _compute_credit_info(self):
        """Calcula información de crédito para NC tipo 34."""
        for move in self:
            if move.move_type != 'out_refund' or not move.credit_ids:
                move.credit_available = 0.0
                move.credit_state = 'no_credit'
                continue

            credit = move.credit_ids[:1]  # Solo debería haber uno por NC
            move.credit_available = credit.amount_available
            if credit.state == 'void':
                move.credit_state = 'no_credit'
            elif credit.state == 'consumed':
                move.credit_state = 'consumed'
            elif credit.state == 'partial':
                move.credit_state = 'partial'
            else:
                move.credit_state = 'available'

    @api.depends('applied_credit_ids', 'applied_credit_ids.amount_applied', 'applied_credit_ids.state')
    def _compute_applied_credit_total(self):
        """Calcula el total de créditos aplicados a esta factura."""
        for move in self:
            total = sum(
                app.amount_applied
                for app in move.applied_credit_ids.filtered(lambda a: a.state == 'applied')
            )
            move.applied_credit_total = total

    def _compute_api_log_count(self):
        """Cuenta los logs de API relacionados."""
        for move in self:
            move.api_log_count = len(move.api_log_ids)

    def action_view_api_logs(self):
        """Abre la vista de logs de API para esta factura."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Logs de API'),
            'res_model': 'ecf.api.log',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id)],
            'context': {'default_move_id': self.id},
        }

    @api.depends('encf', 'state', 'dgii_estado')
    def _compute_encf_state(self):
        """Calcula el estado del e-NCF basado en si fue generado y enviado."""
        for move in self:
            if move.dgii_estado and move.dgii_estado != 'draft':
                move.encf_state = 'sent'
            elif move.encf:
                # Aquí se podría verificar si fue enviado a DGII
                # Por ahora solo verificamos si existe el e-NCF
                move.encf_state = 'generated'
            elif move.state == 'posted':
                move.encf_state = 'pending'
            else:
                move.encf_state = False

    # ========== GENERACIÓN DE E-NCF ==========
    def _generate_encf(self):
        """
        Genera el e-NCF para la factura según la normativa DGII.

        Formato: E + TipoECF(2) + Establecimiento(3) + PuntoEmision(3) + Secuencia(8)
        Ejemplo: E3100500100000123

        Returns:
            str: El e-NCF generado

        Raises:
            UserError: Si no se cumplen las condiciones para generar el e-NCF
        """
        self.ensure_one()

        # Validación 1: La factura debe estar confirmada
        if self.state != 'posted':
            raise UserError(_(
                'La factura debe estar confirmada (posted) para generar el e-NCF.'
            ))

        # Validación 2: El diario debe tener establecimiento y punto de emisión
        if not self.journal_id.dgii_establecimiento or not self.journal_id.dgii_punto_emision:
            raise UserError(_(
                'El diario "%s" no tiene configurado el establecimiento y/o punto de emisión DGII.\n'
                'Establecimiento: %s\n'
                'Punto de Emisión: %s'
            ) % (
                self.journal_id.name,
                self.journal_id.dgii_establecimiento or 'NO CONFIGURADO',
                self.journal_id.dgii_punto_emision or 'NO CONFIGURADO'
            ))

        # Determinar el tipo de e-CF a usar
        # Prioridad 1: Tipo manual seleccionado por el usuario
        # Prioridad 2: Selección automática según el cliente

        _logger = logging.getLogger(__name__)
        _logger.warning(f"""
        ========== DEBUG GENERACIÓN E-NCF ==========
        Factura ID: {self.id}
        Cliente: {self.partner_id.name}
        Cliente RNC: {self.partner_id.vat or 'SIN RNC'}
        Cliente Tipo Contribuyente: {getattr(self.partner_id, 'x_tipo_contribuyente', 'NO DEFINIDO')}
        Tipo Manual Seleccionado: {self.x_tipo_ecf_manual or 'NINGUNO (automático)'}
        Diario: {self.journal_id.name}
        Diario Tipos Configurados: {[t.codigo for t in self.journal_id.dgii_tipo_ecf_ids]}
        ============================================
        """)

        if self.x_tipo_ecf_manual:
            tipo_ecf = self.x_tipo_ecf_manual
            _logger.warning(f"→ Usando tipo MANUAL: {tipo_ecf}")
        else:
            tipo_ecf = self.journal_id.get_tipo_ecf_for_invoice(self)
            _logger.warning(f"→ Tipo AUTOMÁTICO seleccionado: {tipo_ecf}")

        if not tipo_ecf:
            raise UserError(_(
                'No se pudo determinar el tipo de e-CF.\n\n'
                'SOLUCIONES:\n'
                '1. Seleccione manualmente el tipo de comprobante en el campo "Tipo de Comprobante"\n'
                '2. Configure tipos de e-CF en el diario: %s\n'
                '3. Verifique que el cliente tenga configurado el "Tipo de Contribuyente"'
            ) % self.journal_id.name)

        # Validación 3: El cliente debe tener RNC/Cédula (vat) según el tipo
        # IMPORTANTE: Solo tipos que requieren RNC (31, 33, 34, 41, 45, 46, 47)
        # NO requieren RNC: Tipo 32 (Consumo), 43 (Gastos Menores), 44 (Regímenes Especiales)
        tipo_obj = self.env['dgii.ecf.tipo'].search([('codigo', '=', tipo_ecf)], limit=1)

        _logger.warning(f"""
        ========== DEBUG VALIDACIÓN RNC ==========
        Tipo e-CF buscado: {tipo_ecf}
        Tipo encontrado: {tipo_obj.name if tipo_obj else 'NO ENCONTRADO'}
        Requiere RNC: {tipo_obj.requiere_rnc if tipo_obj else 'N/A'}
        Cliente tiene RNC: {bool(self.partner_id.vat)}
        ¿Va a pedir RNC?: {tipo_obj and tipo_obj.requiere_rnc and not self.partner_id.vat}
        ============================================
        """)

        _logger.warning(f"→ Condición IF (línea 148): tipo_obj={bool(tipo_obj)} AND requiere_rnc={tipo_obj.requiere_rnc if tipo_obj else 'N/A'} AND not vat={not self.partner_id.vat}")

        if tipo_obj and tipo_obj.requiere_rnc and not self.partner_id.vat:
            _logger.warning("→→→ ENTRANDO A RAISE USERERROR (línea 149-166)")
            # Obtener tipo de contribuyente del cliente
            tipo_contribuyente = getattr(self.partner_id, 'x_tipo_contribuyente', 'consumo_final')
            tipo_contribuyente_nombre = dict(self.partner_id._fields['x_tipo_contribuyente'].selection).get(
                tipo_contribuyente, tipo_contribuyente
            ) if hasattr(self.partner_id, 'x_tipo_contribuyente') else 'Consumidor Final'

            raise UserError(_(
                'El cliente "%s" no tiene RNC o Cédula configurado.\n'
                'Es obligatorio para el tipo de comprobante: %s\n\n'
                'Tipo de Contribuyente del Cliente: %s\n\n'
                'SOLUCIÓN:\n'
                '1. Si es consumidor final SIN RNC:\n'
                '   → Cambiar "Tipo de Contribuyente" a "Consumidor Final"\n\n'
                '2. Si requiere crédito fiscal:\n'
                '   → Agregar RNC al cliente\n'
                '   → Validar RNC con botón "🔍 Autocompletar desde DGII"\n'
                '   → Cambiar "Tipo de Contribuyente" a "Crédito Fiscal"'
            ) % (self.partner_id.name, tipo_obj.name, tipo_contribuyente_nombre))

        _logger.warning("→ NO ENTRÓ AL IF - Continuando sin pedir RNC ✓")

        # Validación 4 (Opcional pero recomendada): RNC validado
        if hasattr(self.partner_id, 'x_rnc_validado') and not self.partner_id.x_rnc_validado:
            # Solo advertencia, no bloquea
            pass

        # Obtener rango válido del diario para el tipo específico
        _logger.warning(f"→ Buscando rango para tipo_ecf={tipo_ecf} en diario={self.journal_id.name}")
        ecf_range = self.journal_id.get_available_ecf_range(tipo_ecf=tipo_ecf)
        _logger.warning(f"→ Rango encontrado: {ecf_range.name if ecf_range else 'NO ENCONTRADO'}")

        if not ecf_range:
            raise UserError(_(
                'No existe un rango de secuencias e-NCF válido y disponible para el diario "%s".\n\n'
                'Verifique que:\n'
                '- Existe un rango activo\n'
                '- El tipo de e-CF coincide: %s\n'
                '- El establecimiento coincide: %s\n'
                '- El punto de emisión coincide: %s\n'
                '- El rango no está vencido\n'
                '- El rango no está agotado'
            ) % (
                self.journal_id.name,
                tipo_obj.name if tipo_obj else tipo_ecf,
                self.journal_id.dgii_establecimiento,
                self.journal_id.dgii_punto_emision
            ))

        # Obtener siguiente número de secuencia (con locking)
        try:
            next_sequence = ecf_range.get_next_sequence_number()
        except UserError as e:
            raise UserError(_(
                'Error al obtener la siguiente secuencia del rango "%s":\n%s'
            ) % (ecf_range.name, str(e)))

        # Construir e-NCF según normativa DGII
        # Formato: E + TipoECF(2) + Secuencial(10)
        # Ejemplo: E + 31 + 0000000005 = E310000000005 (13 caracteres)
        # Nota: El establecimiento y punto de emisión NO van en el e-NCF,
        # solo se usan para identificar el rango de secuencias
        encf = 'E{tipo}{seq:010d}'.format(
            tipo=tipo_ecf,
            seq=next_sequence
        )

        # Validar longitud del e-NCF (debe ser exactamente 13 caracteres)
        if len(encf) != 13:
            raise UserError(_(
                'Error en formato de e-NCF generado: %s (longitud: %d, esperada: 13)\n\n'
                'Formato correcto: E + Tipo(2) + Secuencial(10)\n'
                'Ejemplo: E310000000005'
            ) % (encf, len(encf)))

        # Guardar e-NCF en la factura
        self.encf = encf

        return encf

    # ========== SOBRESCRITURA DE MÉTODOS ODOO ==========
    def action_post(self):
        """
        Sobrescribe action_post para generar automáticamente el e-NCF
        cuando se confirma la factura (si aplica).
        """
        res = super(AccountMove, self).action_post()

        # Generar e-NCF para facturas de cliente que lo requieran
        for move in self:
            # Solo para facturas de cliente/proveedor (no asientos contables)
            if move.move_type in ['out_invoice', 'out_refund'] and not move.encf:
                # Verificar si el diario está configurado para DGII
                if move.journal_id.dgii_tipo_ecf_ids or move.journal_id.dgii_tipo_ecf:
                    try:
                        move._generate_encf()
                    except UserError:
                        # Si falla, no bloquea la confirmación
                        # El e-NCF se puede generar manualmente después
                        pass

        return res

    # ========== MÉTODOS DE ACCIÓN ==========
    def action_generate_encf(self):
        """Acción manual para generar el e-NCF."""
        for move in self:
            if move.encf:
                raise UserError(_(
                    'Esta factura ya tiene un e-NCF generado: %s'
                ) % move.encf)

            encf = move._generate_encf()

            # Mensaje de confirmación
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('e-NCF Generado'),
                    'message': _('Se generó el e-NCF: %s') % encf,
                    'type': 'success',
                    'sticky': False,
                }
            }

    def action_preview_dgii_json(self):
        """
        Muestra el JSON que se enviaría a DGII sin enviarlo.
        Útil para debugging y verificación del formato.
        """
        self.ensure_one()

        if not self.encf:
            raise UserError(_('Primero debe generar el e-NCF para ver el JSON.'))

        invoice_data = self._build_dgii_invoice_data()
        json_formatted = json.dumps(invoice_data, indent=2, ensure_ascii=False)

        # Log también en consola
        _logger.warning("========== PREVIEW JSON DGII ==========")
        _logger.warning(f"Factura: {self.name} | e-NCF: {self.encf}")
        _logger.warning(f"JSON:\n{json_formatted}")
        _logger.warning("========================================")

        # Guardar en el campo de respuesta para visualización
        self.write({
            'dgii_response_raw': json_formatted,
            'dgii_response_message': f'Preview JSON - Tipo {self.encf[1:3]} - {self.name}',
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('JSON Generado'),
                'message': _('El JSON se ha guardado en el campo "Respuesta DGII (JSON)" en la pestaña DGII.'),
                'type': 'info',
                'sticky': False,
            }
        }

    def action_send_to_dgii(self):
        """
        Envía la factura al microservicio DGII usando el sistema de proveedores de API.
        """
        self.ensure_one()

        # Validaciones previas al envío
        self._validate_before_dgii_send()

        # Obtener proveedor de API por defecto
        provider = self.env['ecf.api.provider'].get_default_provider()
        if not provider:
            raise UserError(_(
                'No hay proveedor de API configurado.\n\n'
                'Configure un proveedor en:\nDGII → Técnico → Proveedores de API'
            ))

        # Construir el JSON del e-CF
        invoice_data = self._build_dgii_invoice_data()

        # Log en consola para debugging
        _logger.info("========== JSON DGII GENERADO ==========")
        _logger.info(f"Factura: {self.name} | e-NCF: {self.encf}")
        _logger.info(f"Tipo e-CF: {self.encf[1:3] if self.encf else 'N/A'}")
        _logger.info(f"Proveedor: {provider.name}")
        _logger.info("=========================================")

        # Determinar origen según tipo de documento
        move_type = self.move_type
        if move_type in ('out_refund', 'in_refund'):
            origin = 'credit_note'
        elif self.encf and self.encf[1:3] == '33':
            origin = 'debit_note'
        else:
            origin = 'invoice'

        # Enviar usando el proveedor (usa método extendido que asocia el move_id al log)
        success, response_data, track_id, error_msg, raw_response, signed_xml = provider.send_ecf_from_invoice(
            ecf_json=invoice_data,
            move=self,
            origin=origin,
        )

        if not success:
            raise UserError(_(
                'Error al enviar a DGII:\n%s'
            ) % (error_msg or 'Error desconocido'))

        # Procesar respuesta exitosa
        data = response_data.get('data', response_data) if isinstance(response_data, dict) else {}

        self.write({
            'dgii_track_id': track_id or data.get('trackId'),
            'dgii_estado': 'pending' if data.get('codigo') in ('0', 0, None) else 'accepted',
            'dgii_signed_xml': signed_xml or data.get('signedXml') or data.get('signedEcfXml'),
            'dgii_security_code': data.get('securityCode') or data.get('ecfSecurityCode'),
            'dgii_qr_url': data.get('qrCodeUrl'),
            'dgii_last_status_date': fields.Datetime.now(),
            'dgii_response_message': self._format_dgii_messages(data),
            'dgii_response_raw': json.dumps(response_data, ensure_ascii=False) if isinstance(response_data, dict) else raw_response,
        })

        # Registrar en chatter para auditoría
        message = _('Enviado a DGII via %s. TrackID: %s') % (provider.name, track_id or _('N/D'))
        if data.get('estado'):
            message += _('\nEstado inicial: %s') % data.get('estado')
        self.message_post(body=message)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Enviado a DGII'),
                'message': _('TrackID: %s') % (track_id or _('N/D')),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_send_dgii_approval(self, approval_payload=None, file_name=None):
        """
        Envía una aprobación comercial (ACECF) usando el microservicio.
        approval_payload debe ser un dict con la estructura esperada por /api/approval/send.
        """
        self.ensure_one()
        if not approval_payload:
            raise UserError(_('Debe proporcionar el payload de aprobación (ACECF).'))

        config = self._get_microservice_config()
        payload = {
            "approvalData": approval_payload,
            "fileName": file_name or f"{self.company_id.vat or ''}{self.encf or ''}.xml",
        }
        self._call_microservice('/approval/send', payload, success_message=_('Aprobación comercial enviada a DGII.'))

    def action_send_dgii_void(self, void_payload=None, file_name=None):
        """
        Envía una anulación de rango (ANECF) usando el microservicio.
        void_payload debe ser un dict con la estructura esperada por /api/void/send.
        """
        self.ensure_one()
        if not void_payload:
            raise UserError(_('Debe proporcionar el payload de anulación (ANECF).'))

        payload = {
            "voidData": void_payload,
            "fileName": file_name or f"{self.company_id.vat or ''}ANULACION.xml",
        }
        self._call_microservice('/void/send', payload, success_message=_('Solicitud de anulación enviada a DGII.'))

    def _call_microservice(self, endpoint, payload, method='post', success_message=None):
        """Helper genérico para enviar requests al microservicio."""
        config = self._get_microservice_config()
        url = f"{config['base_url']}{endpoint}"
        try:
            response = requests.request(
                method=method,
                url=url,
                json=payload,
                headers=self._get_microservice_headers(config),
                timeout=20,
            )
        except requests.RequestException as exc:
            raise UserError(_('No se pudo conectar con el microservicio DGII: %s') % str(exc))

        if response.status_code >= 400:
            raise UserError(_('Error HTTP %s desde microservicio:\n%s') % (response.status_code, response.text))

        try:
            result = response.json()
        except ValueError:
            raise UserError(_('La respuesta del microservicio no es JSON válido.'))

        if not result.get('success'):
            raise UserError(_('Microservicio devolvió error: %s') % result.get('error', 'Error desconocido'))

        self.write({
            'dgii_response_message': self._format_dgii_messages(result.get('data', {})),
            'dgii_response_raw': json.dumps(result, ensure_ascii=False),
            'dgii_last_status_date': fields.Datetime.now(),
        })
        if success_message:
            self.message_post(body=success_message)
        return result

    def _validate_before_dgii_send(self):
        """
        Valida que la factura cumpla todos los requisitos antes de enviar a DGII.

        Raises:
            UserError: Si no se cumplen las validaciones
        """
        self.ensure_one()

        # Validación 1: Factura confirmada
        if self.state != 'posted':
            raise UserError(_(
                'La factura debe estar confirmada antes de enviar a DGII.'
            ))

        # Validación 2: Debe tener e-NCF
        if not self.encf:
            # Intentar generar
            try:
                self._generate_encf()
            except UserError as e:
                raise UserError(_(
                    'No se puede enviar a DGII sin e-NCF.\n\n'
                    'Error al generar e-NCF:\n%s'
                ) % str(e))

        # Validación 3: Cliente con RNC
        if not self.partner_id.vat:
            raise UserError(_(
                'El cliente "%s" no tiene RNC o Cédula configurado.'
            ) % self.partner_id.name)

        # Validación 4 (Recomendada): RNC validado
        if hasattr(self.partner_id, 'x_rnc_validado') and not self.partner_id.x_rnc_validado:
            # Solo advertencia
            pass

        # Validación 5: Diario correctamente configurado
        if not (self.journal_id.dgii_tipo_ecf or self.journal_id.dgii_tipo_ecf_ids):
            raise UserError(_(
                'El diario "%s" no tiene tipo de e-CF configurado.'
            ) % self.journal_id.name)

        if not self.journal_id.dgii_establecimiento or not self.journal_id.dgii_punto_emision:
            raise UserError(_(
                'El diario "%s" no tiene establecimiento y/o punto de emisión configurado.'
            ) % self.journal_id.name)

        return True

    def _build_dgii_invoice_data(self):
        """
        Construye el JSON esperado por el microservicio DGII.
        Dispatcher que llama al método específico según el tipo de e-CF.
        """
        self.ensure_one()

        tipo_ecf = self.encf[1:3] if self.encf else '31'

        # Dispatcher: buscar método específico para el tipo
        builder_method = getattr(self, f'_build_ecf_tipo_{tipo_ecf}', None)
        if builder_method:
            return builder_method()
        else:
            # Fallback al tipo 31 como default
            return self._build_ecf_tipo_31()

    # ========== MÉTODOS AUXILIARES PARA CONSTRUIR ECF ==========

    def _get_indicador_facturacion(self, line):
        """
        Determina el IndicadorFacturacion basado en los impuestos de la línea.
        1 = Gravado ITBIS 18%
        2 = Gravado ITBIS 16%
        3 = Gravado ITBIS 0%
        4 = Exento de ITBIS
        """
        for tax in line.tax_ids:
            if tax.amount == 18:
                return 1
            elif tax.amount == 16:
                return 2
            elif tax.amount == 0:
                return 3
        # Sin impuestos = Exento
        return 4

    def _calculate_itbis_by_rate(self):
        """
        Calcula los montos de ITBIS agrupados por tasa.
        Retorna dict con MontoGravadoI1/I2/I3, TotalITBIS1/2/3, etc.
        """
        result = {
            'monto_gravado_18': 0.0,
            'monto_gravado_16': 0.0,
            'monto_gravado_0': 0.0,
            'monto_exento': 0.0,
            'itbis_18': 0.0,
            'itbis_16': 0.0,
            'itbis_0': 0.0,
        }

        for line in self.invoice_line_ids.filtered(
                lambda l: l.display_type not in ('line_section', 'line_note')):
            tax_amount = line.price_total - line.price_subtotal
            has_tax = False

            for tax in line.tax_ids:
                has_tax = True
                if tax.amount == 18:
                    result['monto_gravado_18'] += line.price_subtotal
                    result['itbis_18'] += tax_amount
                elif tax.amount == 16:
                    result['monto_gravado_16'] += line.price_subtotal
                    result['itbis_16'] += tax_amount
                elif tax.amount == 0:
                    result['monto_gravado_0'] += line.price_subtotal
                    result['itbis_0'] += tax_amount

            if not has_tax:
                result['monto_exento'] += line.price_subtotal

        return result

    def _build_ecf_emisor(self, include_optional=True):
        """Construye la sección Emisor del ECF."""
        company = self.company_id
        emisor = {
            "RNCEmisor": company.vat or '',
            "RazonSocialEmisor": company.name or '',
            "DireccionEmisor": company.street or '',
            "FechaEmision": (self.invoice_date or fields.Date.context_today(self)).strftime("%d-%m-%Y"),
        }

        if include_optional:
            if hasattr(company, 'x_nombre_comercial') and company.x_nombre_comercial:
                emisor["NombreComercial"] = company.x_nombre_comercial
            if hasattr(company.partner_id, 'x_dgii_municipio') and company.partner_id.x_dgii_municipio:
                emisor["Municipio"] = company.partner_id.x_dgii_municipio
            if hasattr(company.partner_id, 'x_dgii_provincia') and company.partner_id.x_dgii_provincia:
                emisor["Provincia"] = company.partner_id.x_dgii_provincia
            if company.phone:
                emisor["TablaTelefonoEmisor"] = {"TelefonoEmisor": [company.phone]}
            if company.email:
                emisor["CorreoEmisor"] = company.email
            if company.website:
                emisor["WebSite"] = company.website

        return emisor

    def _build_ecf_comprador(self, include_optional=True):
        """Construye la sección Comprador del ECF."""
        partner = self.partner_id
        comprador = {
            "RNCComprador": partner.vat or '',
            "RazonSocialComprador": partner.name or '',
        }

        if include_optional:
            if partner.street:
                comprador["DireccionComprador"] = partner.street
            if hasattr(partner, 'x_dgii_municipio') and partner.x_dgii_municipio:
                comprador["MunicipioComprador"] = partner.x_dgii_municipio
            if hasattr(partner, 'x_dgii_provincia') and partner.x_dgii_provincia:
                comprador["ProvinciaComprador"] = partner.x_dgii_provincia
            if partner.email:
                comprador["CorreoComprador"] = partner.email

        return comprador

    def _build_ecf_comprador_extranjero(self):
        """Construye la sección Comprador para tipo 47 (Pagos Exterior)."""
        partner = self.partner_id
        comprador = {
            "RazonSocialComprador": partner.name or '',
        }

        # Usar identificador extranjero en lugar de RNC
        if hasattr(partner, 'x_dgii_identificador_extranjero') and partner.x_dgii_identificador_extranjero:
            comprador["IdentificadorExtranjero"] = partner.x_dgii_identificador_extranjero
        elif partner.vat:
            comprador["IdentificadorExtranjero"] = partner.vat

        return comprador

    def _build_ecf_items(self, include_retention=False):
        """Construye la sección DetallesItems del ECF."""
        items = []

        for idx, line in enumerate(self.invoice_line_ids.filtered(
                lambda l: l.display_type not in ('line_section', 'line_note')), start=1):

            # Obtener tipo bien/servicio del producto
            bien_servicio = '1'  # Default: Bien
            unidad_medida = '43'  # Default: Unidad

            if line.product_id:
                if hasattr(line.product_id, 'x_dgii_bien_servicio') and line.product_id.x_dgii_bien_servicio:
                    bien_servicio = line.product_id.x_dgii_bien_servicio
                elif line.product_id.type == 'service':
                    bien_servicio = '2'

                if hasattr(line.product_id, 'x_dgii_unidad_medida') and line.product_id.x_dgii_unidad_medida:
                    unidad_medida = line.product_id.x_dgii_unidad_medida

            item = {
                "NumeroLinea": idx,
                "IndicadorFacturacion": self._get_indicador_facturacion(line),
                "NombreItem": (line.name or line.product_id.name or 'Producto')[:80],
                "IndicadorBienoServicio": int(bien_servicio),
                "CantidadItem": f"{line.quantity:.2f}",
                "UnidadMedida": unidad_medida,
                "PrecioUnitarioItem": f"{line.price_unit:.4f}",
                "MontoItem": f"{line.price_subtotal:.2f}",
            }

            # Agregar descripción si es diferente al nombre
            if line.name and line.product_id and line.name != line.product_id.name:
                descripcion = line.name[:250] if len(line.name) > 250 else line.name
                if descripcion != item["NombreItem"]:
                    item["DescripcionItem"] = descripcion

            items.append(item)

        return {"Item": items}

    def _build_ecf_totales(self, itbis_data):
        """Construye la sección Totales del ECF."""
        totales = {}

        monto_gravado_total = (
            itbis_data['monto_gravado_18'] +
            itbis_data['monto_gravado_16'] +
            itbis_data['monto_gravado_0']
        )
        total_itbis = (
            itbis_data['itbis_18'] +
            itbis_data['itbis_16'] +
            itbis_data['itbis_0']
        )

        # Montos gravados por tasa
        if monto_gravado_total > 0:
            totales["MontoGravadoTotal"] = f"{monto_gravado_total:.2f}"

        if itbis_data['monto_gravado_18'] > 0:
            totales["MontoGravadoI1"] = f"{itbis_data['monto_gravado_18']:.2f}"
            totales["ITBIS1"] = "18"
            totales["TotalITBIS1"] = f"{itbis_data['itbis_18']:.2f}"

        if itbis_data['monto_gravado_16'] > 0:
            totales["MontoGravadoI2"] = f"{itbis_data['monto_gravado_16']:.2f}"
            totales["ITBIS2"] = "16"
            totales["TotalITBIS2"] = f"{itbis_data['itbis_16']:.2f}"

        if itbis_data['monto_gravado_0'] > 0:
            totales["MontoGravadoI3"] = f"{itbis_data['monto_gravado_0']:.2f}"
            totales["ITBIS3"] = "0"
            totales["TotalITBIS3"] = f"{itbis_data['itbis_0']:.2f}"

        if itbis_data['monto_exento'] > 0:
            totales["MontoExento"] = f"{itbis_data['monto_exento']:.2f}"

        if total_itbis > 0:
            totales["TotalITBIS"] = f"{total_itbis:.2f}"

        totales["MontoTotal"] = f"{self.amount_total:.2f}"

        return totales

    def _build_ecf_informacion_referencia(self):
        """Construye la sección InformacionReferencia para NC/ND."""
        if not self.x_ncf_modificado:
            return None

        referencia = {
            "NCFModificado": self.x_ncf_modificado,
        }

        if self.x_fecha_ncf_modificado:
            referencia["FechaNCFModificado"] = self.x_fecha_ncf_modificado.strftime("%d-%m-%Y")

        if self.x_codigo_modificacion:
            referencia["CodigoModificacion"] = self.x_codigo_modificacion

        if self.x_razon_modificacion:
            referencia["RazonModificacion"] = self.x_razon_modificacion

        return referencia

    # ========== BUILDERS POR TIPO DE ECF ==========

    def _build_ecf_tipo_31(self):
        """Construye ECF Tipo 31 - Factura de Crédito Fiscal."""
        itbis_data = self._calculate_itbis_by_rate()

        encabezado = {
            "Version": "1.0",
            "IdDoc": {
                "TipoeCF": "31",
                "eNCF": self.encf,
                "FechaVencimientoSecuencia": self._get_dgii_range_expiration() or "",
                "TipoIngresos": self.x_tipo_ingresos or "01",
                "TipoPago": self.x_tipo_pago or "1",
            },
            "Emisor": self._build_ecf_emisor(),
            "Comprador": self._build_ecf_comprador(),
            "Totales": self._build_ecf_totales(itbis_data),
        }

        ecf = {
            "Encabezado": encabezado,
            "DetallesItems": self._build_ecf_items(),
        }

        return {"ECF": ecf}

    def _build_ecf_tipo_32(self):
        """
        Construye ECF Tipo 32 - Factura de Consumo.
        Si MontoTotal >= 250,000: incluir datos completos del comprador.
        Si MontoTotal < 250,000: formato simplificado.
        Soporta múltiples formas de pago incluyendo FormaPago=7 (Nota de Crédito).
        """
        itbis_data = self._calculate_itbis_by_rate()
        totales = self._build_ecf_totales(itbis_data)

        # Agregar campos específicos de tipo 32
        totales["MontoPeriodo"] = f"{self.amount_total:.2f}"
        totales["ValorPagar"] = f"{self.amount_total:.2f}"

        id_doc = {
            "TipoeCF": "32",
            "eNCF": self.encf,
            "IndicadorMontoGravado": "0",
            "TipoIngresos": self.x_tipo_ingresos or "01",
            "TipoPago": self.x_tipo_pago or "1",
        }

        # Construir TablaFormasPago dinámicamente
        id_doc["TablaFormasPago"] = self._build_tabla_formas_pago()

        encabezado = {
            "Version": "1.0",
            "IdDoc": id_doc,
            "Emisor": self._build_ecf_emisor(),
            "Totales": totales,
        }

        # Regla >= 250,000: incluir datos del comprador
        if self.amount_total >= 250000:
            encabezado["Comprador"] = self._build_ecf_comprador()

        ecf = {
            "Encabezado": encabezado,
            "DetallesItems": self._build_ecf_items(),
        }

        return {"ECF": ecf}

    def _build_tabla_formas_pago(self):
        """
        Construye la tabla de formas de pago para el JSON e-CF.
        Incluye FormaPago=7 (Nota de Crédito) si hay créditos aplicados.

        Códigos de FormaPago según DGII:
        1 = Efectivo
        2 = Cheques/Transferencias/Depósito
        3 = Tarjeta Crédito/Débito
        4 = Venta a Crédito
        5 = Bonos o Certificados de Regalo
        6 = Permuta
        7 = Nota de Crédito
        8 = Otras Formas de Venta
        """
        formas_pago = []

        # Obtener créditos aplicados a esta factura
        creditos_aplicados = self.applied_credit_ids.filtered(
            lambda app: app.state == 'applied'
        )

        monto_creditos = 0.0

        # Agregar cada crédito aplicado como FormaPago=7
        for app in creditos_aplicados:
            formas_pago.append({
                "FormaPago": 7,  # Nota de Crédito
                "MontoPago": f"{app.amount_applied:.2f}"
            })
            monto_creditos += app.amount_applied

        # Calcular monto restante (no cubierto por créditos)
        monto_restante = self.amount_total - monto_creditos

        # Agregar el resto en efectivo (o forma de pago por defecto)
        if monto_restante > 0.01:  # Tolerancia para evitar problemas de redondeo
            formas_pago.append({
                "FormaPago": 1,  # Efectivo (default)
                "MontoPago": f"{monto_restante:.2f}"
            })

        # Si no hay formas de pago (caso edge), agregar todo como efectivo
        if not formas_pago:
            formas_pago.append({
                "FormaPago": 1,
                "MontoPago": f"{self.amount_total:.2f}"
            })

        return {"FormaDePago": formas_pago}

    def _build_ecf_tipo_33(self):
        """Construye ECF Tipo 33 - Nota de Débito."""
        itbis_data = self._calculate_itbis_by_rate()

        encabezado = {
            "Version": "1.0",
            "IdDoc": {
                "TipoeCF": "33",
                "eNCF": self.encf,
                "FechaVencimientoSecuencia": self._get_dgii_range_expiration() or "",
                "TipoIngresos": self.x_tipo_ingresos or "01",
                "TipoPago": self.x_tipo_pago or "1",
            },
            "Emisor": self._build_ecf_emisor(),
            "Comprador": self._build_ecf_comprador(),
            "Totales": self._build_ecf_totales(itbis_data),
        }

        ecf = {
            "Encabezado": encabezado,
            "DetallesItems": self._build_ecf_items(),
        }

        # Agregar información de referencia (NCF modificado)
        info_ref = self._build_ecf_informacion_referencia()
        if info_ref:
            ecf["InformacionReferencia"] = info_ref

        return {"ECF": ecf}

    def _build_ecf_tipo_34(self):
        """Construye ECF Tipo 34 - Nota de Crédito."""
        itbis_data = self._calculate_itbis_by_rate()

        # Usar indicador calculado dinámicamente según días transcurridos
        # 0 = NC emitida dentro de 30 días de la factura original
        # 1 = NC emitida después de 30 días (sin rebajar ITBIS)
        indicador_nc = self.x_indicador_nota_credito or "0"

        id_doc = {
            "TipoeCF": "34",
            "eNCF": self.encf,
            "IndicadorNotaCredito": indicador_nc,
            "TipoIngresos": self.x_tipo_ingresos or "01",
            "TipoPago": self.x_tipo_pago or "1",
        }
        # NOTA: Según normativa DGII, la secuencia de NC tipo 34 NO lleva
        # FechaVencimientoSecuencia (código 0 = "No corresponde")
        # Por lo tanto, NO se incluye este campo para tipo 34

        encabezado = {
            "Version": "1.0",
            "IdDoc": id_doc,
            "Emisor": self._build_ecf_emisor(),
            "Comprador": self._build_ecf_comprador(),
            "Totales": self._build_ecf_totales(itbis_data),
        }

        ecf = {
            "Encabezado": encabezado,
            "DetallesItems": self._build_ecf_items(),
        }

        # Agregar información de referencia (NCF modificado) - OBLIGATORIO para NC
        info_ref = self._build_ecf_informacion_referencia()
        if info_ref:
            ecf["InformacionReferencia"] = info_ref

        return {"ECF": ecf}

    def _build_ecf_tipo_41(self):
        """Construye ECF Tipo 41 - Comprobante de Compras."""
        itbis_data = self._calculate_itbis_by_rate()
        totales = self._build_ecf_totales(itbis_data)

        # Campos de retención (si aplica)
        totales["TotalITBISRetenido"] = "0.00"
        totales["TotalISRRetencion"] = "0.00"
        totales["ValorPagar"] = f"{self.amount_total:.2f}"

        encabezado = {
            "Version": "1.0",
            "IdDoc": {
                "TipoeCF": "41",
                "eNCF": self.encf,
                "FechaVencimientoSecuencia": self._get_dgii_range_expiration() or "",
                "IndicadorMontoGravado": "0",
                "TipoPago": self.x_tipo_pago or "1",
                "TablaFormasPago": {
                    "FormaDePago": [{
                        "FormaPago": 1,
                        "MontoPago": f"{self.amount_total:.2f}"
                    }]
                }
            },
            "Emisor": self._build_ecf_emisor(include_optional=False),
            "Comprador": self._build_ecf_comprador(),
            "Totales": totales,
        }

        ecf = {
            "Encabezado": encabezado,
            "DetallesItems": self._build_ecf_items(include_retention=True),
        }

        return {"ECF": ecf}

    def _build_ecf_tipo_43(self):
        """Construye ECF Tipo 43 - Gastos Menores."""
        itbis_data = self._calculate_itbis_by_rate()

        # Tipo 43 suele ser exento
        totales = {
            "MontoExento": f"{self.amount_total:.2f}",
            "MontoTotal": f"{self.amount_total:.2f}",
        }

        encabezado = {
            "Version": "1.0",
            "IdDoc": {
                "TipoeCF": "43",
                "eNCF": self.encf,
                "FechaVencimientoSecuencia": self._get_dgii_range_expiration() or "",
            },
            "Emisor": self._build_ecf_emisor(),
            "Totales": totales,
        }

        ecf = {
            "Encabezado": encabezado,
            "DetallesItems": self._build_ecf_items(),
        }

        return {"ECF": ecf}

    def _build_ecf_tipo_44(self):
        """Construye ECF Tipo 44 - Régimen Especial."""
        # Productos exentos
        totales = {
            "MontoExento": f"{self.amount_total:.2f}",
            "MontoTotal": f"{self.amount_total:.2f}",
            "MontoPeriodo": f"{self.amount_total:.2f}",
            "ValorPagar": f"{self.amount_total:.2f}",
        }

        encabezado = {
            "Version": "1.0",
            "IdDoc": {
                "TipoeCF": "44",
                "eNCF": self.encf,
                "FechaVencimientoSecuencia": self._get_dgii_range_expiration() or "",
                "TipoIngresos": self.x_tipo_ingresos or "01",
                "TipoPago": self.x_tipo_pago or "1",
                "TablaFormasPago": {
                    "FormaDePago": [{
                        "FormaPago": 1,
                        "MontoPago": f"{self.amount_total:.2f}"
                    }]
                }
            },
            "Emisor": self._build_ecf_emisor(),
            "Comprador": self._build_ecf_comprador(),
            "Totales": totales,
        }

        ecf = {
            "Encabezado": encabezado,
            "DetallesItems": self._build_ecf_items(),
        }

        return {"ECF": ecf}

    def _build_ecf_tipo_45(self):
        """Construye ECF Tipo 45 - Gubernamental."""
        itbis_data = self._calculate_itbis_by_rate()
        totales = self._build_ecf_totales(itbis_data)
        totales["ValorPagar"] = f"{self.amount_total:.2f}"

        encabezado = {
            "Version": "1.0",
            "IdDoc": {
                "TipoeCF": "45",
                "eNCF": self.encf,
                "FechaVencimientoSecuencia": self._get_dgii_range_expiration() or "",
                "IndicadorMontoGravado": "0",
                "TipoIngresos": self.x_tipo_ingresos or "01",
                "TipoPago": self.x_tipo_pago or "1",
            },
            "Emisor": self._build_ecf_emisor(),
            "Comprador": self._build_ecf_comprador(),
            "Totales": totales,
        }

        ecf = {
            "Encabezado": encabezado,
            "DetallesItems": self._build_ecf_items(),
        }

        return {"ECF": ecf}

    def _build_ecf_tipo_46(self):
        """Construye ECF Tipo 46 - Exportaciones."""
        # Exportaciones: ITBIS 0%
        totales = {
            "MontoGravadoTotal": f"{self.amount_total:.2f}",
            "MontoGravadoI3": f"{self.amount_total:.2f}",
            "ITBIS3": "0",
            "TotalITBIS": "0.00",
            "TotalITBIS3": "0.00",
            "MontoTotal": f"{self.amount_total:.2f}",
            "MontoPeriodo": f"{self.amount_total:.2f}",
            "ValorPagar": f"{self.amount_total:.2f}",
        }

        encabezado = {
            "Version": "1.0",
            "IdDoc": {
                "TipoeCF": "46",
                "eNCF": self.encf,
                "FechaVencimientoSecuencia": self._get_dgii_range_expiration() or "",
                "TipoIngresos": self.x_tipo_ingresos or "01",
                "TipoPago": self.x_tipo_pago or "1",
            },
            "Emisor": self._build_ecf_emisor(),
            "Comprador": self._build_ecf_comprador(),
            "Totales": totales,
        }

        # Sección Transporte
        transporte = {}
        if self.partner_id.country_id and self.partner_id.country_id.name:
            transporte["PaisDestino"] = self.partner_id.country_id.name

        ecf = {
            "Encabezado": encabezado,
            "DetallesItems": self._build_ecf_items(),
        }

        if transporte:
            encabezado["Transporte"] = transporte

        return {"ECF": ecf}

    def _build_ecf_tipo_47(self):
        """Construye ECF Tipo 47 - Pagos al Exterior."""
        # Exento + retención ISR
        totales = {
            "MontoExento": f"{self.amount_total:.2f}",
            "MontoTotal": f"{self.amount_total:.2f}",
            "MontoPeriodo": f"{self.amount_total:.2f}",
            "ValorPagar": f"{self.amount_total:.2f}",
            "TotalISRRetencion": "0.00",  # TODO: calcular retención real
        }

        encabezado = {
            "Version": "1.0",
            "IdDoc": {
                "TipoeCF": "47",
                "eNCF": self.encf,
                "FechaVencimientoSecuencia": self._get_dgii_range_expiration() or "",
                "TipoPago": self.x_tipo_pago or "1",
                "TablaFormasPago": {
                    "FormaDePago": [{
                        "FormaPago": 1,
                        "MontoPago": f"{self.amount_total:.2f}"
                    }]
                }
            },
            "Emisor": self._build_ecf_emisor(),
            "Comprador": self._build_ecf_comprador_extranjero(),
            "Totales": totales,
        }

        # Sección Transporte con país destino
        partner = self.partner_id
        pais_destino = None
        if hasattr(partner, 'x_dgii_pais_destino') and partner.x_dgii_pais_destino:
            pais_destino = partner.x_dgii_pais_destino
        elif partner.country_id and partner.country_id.name:
            pais_destino = partner.country_id.name

        if pais_destino:
            encabezado["Transporte"] = {"PaisDestino": pais_destino}

        ecf = {
            "Encabezado": encabezado,
            "DetallesItems": self._build_ecf_items(include_retention=True),
        }

        return {"ECF": ecf}

    def _get_dgii_range_expiration(self):
        """Obtiene fecha de vencimiento del rango activo (si aplica)."""
        ecf_range = self.journal_id.get_available_ecf_range(tipo_ecf=self.encf[1:3] if self.encf else False)
        return ecf_range.fecha_vencimiento.strftime("%d-%m-%Y") if ecf_range and ecf_range.fecha_vencimiento else ''

    def _get_microservice_config(self):
        """Lee configuración de microservicio desde parámetros del sistema."""
        icp = self.env['ir.config_parameter'].sudo()
        base_url = icp.get_param('dgii_ecf.api_base_url', '').rstrip('/')
        api_key = icp.get_param('dgii_ecf.api_key', '')
        environment = icp.get_param('dgii_ecf.environment', 'test')

        if not base_url:
            raise UserError(_('Configure la URL del microservicio DGII en Ajustes del sistema (dgii_ecf.api_base_url).'))

        return {
            'base_url': base_url,
            'api_key': api_key,
            'environment': environment,
        }

    def _get_microservice_headers(self, config):
        """Headers comunes para el microservicio."""
        headers = {
            'Content-Type': 'application/json',
        }
        if config.get('api_key'):
            headers['x-api-key'] = config['api_key']
        return headers

    def action_check_dgii_status(self):
        """Consulta el estado de DGII usando el trackId almacenado."""
        self.ensure_one()

        if not self.dgii_track_id:
            raise UserError(_('No hay trackID almacenado para consultar.'))

        config = self._get_microservice_config()
        try:
            response = requests.get(
                f"{config['base_url']}/invoice/status/{self.dgii_track_id}",
                headers=self._get_microservice_headers(config),
                timeout=10,
            )
        except requests.RequestException as exc:
            raise UserError(_('No se pudo consultar estado en DGII: %s') % str(exc))

        if response.status_code >= 400:
            raise UserError(_('Error HTTP %s al consultar estado DGII.') % response.status_code)

        try:
            result = response.json()
        except ValueError:
            raise UserError(_('La respuesta del microservicio no es JSON válido.'))

        if not result.get('success'):
            raise UserError(_('DGII devolvió error: %s') % result.get('error', 'Error desconocido'))

        data = result.get('data', {})
        estado_map = {
            '0': 'pending',
            '1': 'accepted',
            '2': 'rejected',
            0: 'pending',
            1: 'accepted',
            2: 'rejected',
        }
        new_state = estado_map.get(data.get('codigo'), self.dgii_estado or 'pending')
        self.write({
            'dgii_estado': new_state,
            'dgii_last_status_date': fields.Datetime.now(),
            'dgii_response_message': self._format_dgii_messages(data),
            'dgii_response_raw': json.dumps(result, ensure_ascii=False),
        })

        note = _('DGII estado actualizado: %s') % data.get('estado', new_state)
        self.message_post(body=note)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Estado DGII'),
                'message': _('Estado: %s') % data.get('estado', new_state),
                'type': 'success' if new_state == 'accepted' else 'warning',
                'sticky': False,
            }
        }

    @api.model
    def _cron_update_dgii_status(self):
        """Cron para actualizar estados pendientes en DGII."""
        pending_moves = self.search([
            ('dgii_track_id', '!=', False),
            ('dgii_estado', 'in', ['pending', 'draft']),
        ], limit=50)
        for move in pending_moves:
            try:
                move.action_check_dgii_status()
            except Exception as exc:  # noqa: BLE001
                _logger = logging.getLogger(__name__)
                _logger.warning('No se pudo actualizar estado DGII para %s: %s', move.name, exc)

    def _format_dgii_messages(self, data):
        """Devuelve un texto legible a partir de la lista de mensajes DGII."""
        mensajes = data.get('mensajes') or data.get('messages') or []
        if isinstance(mensajes, list):
            return '\n'.join(
                f"{m.get('codigo', '')}: {m.get('valor', m.get('message', ''))}"
                for m in mensajes
                if isinstance(m, dict)
            )
        return ''

    # ========== GESTIÓN DE CRÉDITOS NC ==========
    def write(self, vals):
        """Override write para crear crédito cuando NC es aceptada por DGII."""
        result = super().write(vals)

        # Si el estado DGII cambia a 'accepted', verificar si es NC para crear crédito
        if vals.get('dgii_estado') == 'accepted':
            for move in self:
                if move.move_type == 'out_refund' and move.encf and move.encf[1:3] == '34':
                    move._create_credit_from_nc()

        return result

    def _create_credit_from_nc(self):
        """
        Crea un registro de crédito cuando la NC tipo 34 es aceptada por DGII.
        Solo crea si no existe ya un crédito para esta NC.
        """
        self.ensure_one()

        if self.move_type != 'out_refund':
            return

        # Verificar si ya existe un crédito para esta NC
        existing_credit = self.env['l10n_do.ecf_credit'].search([
            ('credit_move_id', '=', self.id)
        ], limit=1)

        if existing_credit:
            _logger.info(
                'Crédito ya existe para NC %s (crédito ID: %s)',
                self.encf, existing_credit.id
            )
            return existing_credit

        # Crear el crédito
        credit = self.env['l10n_do.ecf_credit'].create({
            'credit_move_id': self.id,
            'partner_id': self.partner_id.id,
            'encf': self.encf,
            'amount_total': self.amount_total,
            'amount_available': self.amount_total,
            'state': 'available',
        })

        _logger.info(
            'Crédito creado para NC %s: %s (monto: %s)',
            self.encf, credit.id, self.amount_total
        )

        self.message_post(
            body=_(
                'Crédito disponible creado automáticamente.\n'
                'Monto: %s\n'
                'El cliente puede usar este crédito en futuras compras.'
            ) % self.amount_total
        )

        return credit

    def button_cancel(self):
        """
        Override para revertir créditos aplicados antes de cancelar la factura.
        Si hay créditos aplicados, los devuelve al saldo disponible de la NC.
        """
        for move in self:
            # Solo para facturas de cliente (no NC)
            if move.move_type == 'out_invoice':
                # Revertir créditos aplicados
                for app in move.applied_credit_ids.filtered(lambda a: a.state == 'applied'):
                    try:
                        app.action_reverse()
                        move.message_post(
                            body=_(
                                'Crédito revertido por cancelación de factura.\n'
                                'NC: %s\n'
                                'Monto devuelto: %s'
                            ) % (app.credit_encf, app.amount_applied)
                        )
                    except Exception as e:
                        _logger.warning(
                            'Error al revertir crédito %s: %s', app.id, str(e)
                        )

            # Para NC tipo 34, anular el crédito si existe
            elif move.move_type == 'out_refund':
                for credit in move.credit_ids:
                    if credit.state != 'void' and credit.amount_applied == 0:
                        credit.action_void()
                        move.message_post(
                            body=_('Crédito anulado por cancelación de la NC.')
                        )

        return super().button_cancel()

    def action_create_credit_note_ecf(self):
        """
        Abre el wizard para crear una Nota de Crédito e-CF tipo 34
        referenciando esta factura.
        """
        self.ensure_one()

        if self.move_type != 'out_invoice':
            raise UserError(_('Solo puede crear NC desde facturas de cliente.'))

        if self.state != 'posted':
            raise UserError(_('La factura debe estar confirmada para crear una NC.'))

        if not self.encf:
            raise UserError(_(
                'La factura debe tener un e-NCF asignado para crear una NC e-CF tipo 34.'
            ))

        return {
            'name': _('Crear Nota de Crédito e-CF (34)'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.create.credit.note.ecf.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ref_invoice_id': self.id,
            },
        }

    def action_apply_credit(self):
        """Abre el wizard para aplicar un crédito de NC a esta factura."""
        self.ensure_one()

        if self.move_type != 'out_invoice':
            raise UserError(_('Solo puede aplicar créditos a facturas de cliente.'))

        if self.state != 'posted':
            raise UserError(_('La factura debe estar confirmada para aplicar créditos.'))

        # Verificar si hay créditos disponibles
        available_credits = self.env['l10n_do.ecf_credit'].search([
            ('partner_id', '=', self.partner_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['available', 'partial']),
            ('amount_available', '>', 0),
        ])

        if not available_credits:
            raise UserError(_(
                'No hay créditos disponibles para el cliente %s.'
            ) % self.partner_id.name)

        return {
            'name': _('Aplicar Crédito de NC'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.apply.credit.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_invoice_id': self.id,
            },
        }

    # ========== ONCHANGE PARA SELECCIÓN AUTOMÁTICA DE TIPO ==========
    @api.onchange('partner_id')
    def _onchange_partner_id_tipo_ecf(self):
        """
        Auto-selecciona el tipo de documento (x_tipo_ecf_manual) cuando cambia el cliente.
        Basado en el campo x_tipo_contribuyente del cliente.
        """
        if not self.partner_id:
            return

        # Solo para facturas de venta/notas de crédito
        if self.move_type not in ['out_invoice', 'out_refund']:
            return

        # No sobrescribir si el usuario ya seleccionó manualmente
        # Solo auto-seleccionar si está vacío o es la primera vez
        if self._origin and self._origin.x_tipo_ecf_manual and self._origin.partner_id == self.partner_id:
            return

        # Obtener tipo de contribuyente del cliente
        tipo_contribuyente = getattr(self.partner_id, 'x_tipo_contribuyente', None)

        # Mapeo de tipo de contribuyente a tipo de documento
        tipo_ecf_map = {
            'consumo_final': '32',      # Factura de Consumo
            'credito_fiscal': '31',     # Factura de Crédito Fiscal
            'gubernamental': '45',      # Gubernamental
            'regimen_especial': '44',   # Régimen Especial
        }

        # Para notas de crédito, usar tipo 34 siempre
        if self.move_type == 'out_refund':
            self.x_tipo_ecf_manual = '34'
            return

        # Auto-seleccionar según tipo de contribuyente
        if tipo_contribuyente and tipo_contribuyente in tipo_ecf_map:
            new_tipo = tipo_ecf_map[tipo_contribuyente]
            # Verificar que el diario tenga ese tipo configurado
            if self.journal_id and self.journal_id.dgii_tipo_ecf_ids:
                tipos_disponibles = [t.codigo for t in self.journal_id.dgii_tipo_ecf_ids]
                if new_tipo in tipos_disponibles:
                    self.x_tipo_ecf_manual = new_tipo
                elif tipos_disponibles:
                    # Si el tipo deseado no está disponible, usar el primero disponible
                    self.x_tipo_ecf_manual = tipos_disponibles[0]
            else:
                self.x_tipo_ecf_manual = new_tipo
        else:
            # Sin tipo de contribuyente definido, usar 32 (Consumo) por defecto
            self.x_tipo_ecf_manual = '32'

    # ========== VALIDACIONES ==========
    @api.constrains('encf')
    def _check_encf_unique(self):
        """Valida que el e-NCF sea único en el sistema."""
        for move in self:
            if move.encf:
                duplicate = self.search([
                    ('id', '!=', move.id),
                    ('encf', '=', move.encf),
                    ('company_id', '=', move.company_id.id)
                ], limit=1)

                if duplicate:
                    raise ValidationError(_(
                        'El e-NCF "%s" ya está siendo utilizado en otra factura: %s'
                    ) % (move.encf, duplicate.name))

    @api.constrains('amount_total', 'x_ref_move_id', 'move_type')
    def _check_nc_amount_vs_original(self):
        """
        Valida que el monto de la NC no exceda el monto de la factura original
        y que la sumatoria de todas las NC no exceda la factura original.
        """
        for move in self:
            if move.move_type != 'out_refund' or not move.x_ref_move_id:
                continue

            original = move.x_ref_move_id

            # Validación 1: NC individual no puede exceder factura original
            if move.amount_total > original.amount_total:
                raise ValidationError(_(
                    'El monto de la Nota de Crédito (%(nc_amount)s) no puede exceder '
                    'el monto de la factura original (%(orig_amount)s).',
                    nc_amount=move.amount_total,
                    orig_amount=original.amount_total
                ))

            # Validación 2: Sumatoria de NC no puede exceder factura original
            all_nc = self.search([
                ('x_ref_move_id', '=', original.id),
                ('move_type', '=', 'out_refund'),
                ('state', '!=', 'cancel'),
                ('id', '!=', move.id if move.id else 0),
            ])
            suma_nc = sum(nc.amount_total for nc in all_nc) + move.amount_total

            if suma_nc > original.amount_total:
                raise ValidationError(_(
                    'La suma de todas las Notas de Crédito (%(suma)s) excede '
                    'el monto de la factura original (%(orig_amount)s).\n\n'
                    'NC existentes: %(existentes)s\n'
                    'NC actual: %(actual)s',
                    suma=suma_nc,
                    orig_amount=original.amount_total,
                    existentes=sum(nc.amount_total for nc in all_nc),
                    actual=move.amount_total
                ))
