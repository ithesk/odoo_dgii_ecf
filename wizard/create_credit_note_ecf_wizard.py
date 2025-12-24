# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import date

_logger = logging.getLogger(__name__)


class CreateCreditNoteEcfWizard(models.TransientModel):
    """
    Wizard simplificado para crear Nota de Crédito e-CF tipo 34 desde una factura.
    Crea la NC como borrador para que el usuario pueda editar las líneas si es parcial.
    """
    _name = 'account.move.create.credit.note.ecf.wizard'
    _description = 'Wizard para Crear NC e-CF (34)'

    # ========== CAMPOS DE REFERENCIA ==========
    ref_invoice_id = fields.Many2one(
        'account.move',
        string='Factura Original',
        required=True,
        readonly=True,
        domain=[('move_type', '=', 'out_invoice'), ('state', '=', 'posted')],
    )

    ref_invoice_encf = fields.Char(
        string='e-NCF Original',
        related='ref_invoice_id.encf',
        readonly=True
    )

    ref_invoice_date = fields.Date(
        string='Fecha Factura Original',
        related='ref_invoice_id.invoice_date',
        readonly=True
    )

    ref_invoice_amount = fields.Monetary(
        string='Monto Factura Original',
        related='ref_invoice_id.amount_total',
        readonly=True,
        currency_field='currency_id'
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='ref_invoice_id.partner_id',
        readonly=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='ref_invoice_id.currency_id',
        readonly=True
    )

    # ========== TIPO DE NC ==========
    tipo_nc = fields.Selection(
        selection=[
            ('total', 'Total - Anular toda la factura'),
            ('parcial', 'Parcial - Solo algunos items/montos'),
        ],
        string='Tipo de Nota de Crédito',
        required=True,
        default='total',
        help='Total: Copia todas las líneas de la factura\n'
             'Parcial: Crea NC borrador para que edites las líneas manualmente'
    )

    # ========== CÓDIGO DE MODIFICACIÓN DGII ==========
    codigo_modificacion = fields.Selection(
        selection=[
            ('1', '1 - Anulación total'),
            ('2', '2 - Corrección de monto'),
            ('3', '3 - Corrección de datos del comprador'),
            ('4', '4 - Cambio de NCF por error en secuencia'),
            ('5', '5 - Reemplazo por error en información'),
        ],
        string='Código de Modificación',
        required=True,
        default='1',
        help='Código de modificación según normativa DGII para NC tipo 34'
    )

    razon_modificacion = fields.Text(
        string='Razón de Modificación',
        required=True,
        help='Descripción del motivo de la Nota de Crédito'
    )

    # ========== CAMPOS CALCULADOS ==========
    dias_transcurridos = fields.Integer(
        string='Días Transcurridos',
        compute='_compute_dias_transcurridos',
    )

    indicador_nc = fields.Char(
        string='Indicador NC',
        compute='_compute_indicador_nc',
    )

    nc_existentes_amount = fields.Monetary(
        string='NC Existentes',
        compute='_compute_nc_existentes',
        currency_field='currency_id',
    )

    monto_disponible = fields.Monetary(
        string='Monto Disponible',
        compute='_compute_nc_existentes',
        currency_field='currency_id',
    )

    warning_message = fields.Text(
        string='Advertencias',
        compute='_compute_warning_message'
    )

    # ========== COMPUTES ==========
    @api.depends('ref_invoice_id')
    def _compute_dias_transcurridos(self):
        today = date.today()
        for record in self:
            if record.ref_invoice_id and record.ref_invoice_id.invoice_date:
                delta = today - record.ref_invoice_id.invoice_date
                record.dias_transcurridos = delta.days
            else:
                record.dias_transcurridos = 0

    @api.depends('dias_transcurridos')
    def _compute_indicador_nc(self):
        for record in self:
            if record.dias_transcurridos > 30:
                record.indicador_nc = '1 - Más de 30 días'
            else:
                record.indicador_nc = '0 - Dentro de 30 días'

    @api.depends('ref_invoice_id')
    def _compute_nc_existentes(self):
        for record in self:
            if record.ref_invoice_id:
                nc_existentes = self.env['account.move'].search([
                    ('x_ref_move_id', '=', record.ref_invoice_id.id),
                    ('move_type', '=', 'out_refund'),
                    ('state', '!=', 'cancel'),
                ])
                record.nc_existentes_amount = sum(nc.amount_total for nc in nc_existentes)
                record.monto_disponible = record.ref_invoice_id.amount_total - record.nc_existentes_amount
            else:
                record.nc_existentes_amount = 0.0
                record.monto_disponible = 0.0

    @api.depends('dias_transcurridos', 'monto_disponible', 'tipo_nc')
    def _compute_warning_message(self):
        for record in self:
            warnings = []

            if record.dias_transcurridos > 30:
                warnings.append(
                    '⚠️ Han pasado %d días desde la factura original. '
                    'El indicador de NC será 1 (más de 30 días).'
                    % record.dias_transcurridos
                )

            if record.monto_disponible <= 0:
                warnings.append(
                    '⚠️ No hay monto disponible para NC. '
                    'Ya existen NC que cubren el total de la factura.'
                )

            if record.tipo_nc == 'parcial':
                warnings.append(
                    'ℹ️ Se creará una NC en borrador. '
                    'Podrás editar las líneas y cantidades antes de confirmar.'
                )

            record.warning_message = '\n\n'.join(warnings) if warnings else False

    # ========== ONCHANGE ==========
    @api.onchange('tipo_nc')
    def _onchange_tipo_nc(self):
        if self.tipo_nc == 'total':
            self.codigo_modificacion = '1'
        elif self.tipo_nc == 'parcial':
            self.codigo_modificacion = '2'

    # ========== VALIDACIONES ==========
    def _validate_before_create(self):
        """Validaciones antes de crear la NC."""
        self.ensure_one()

        if not self.ref_invoice_id:
            raise UserError(_('Debe seleccionar una factura original.'))

        if not self.ref_invoice_id.encf:
            raise UserError(_(
                'La factura original debe tener un e-NCF asignado para crear una NC e-CF tipo 34.'
            ))

        if self.monto_disponible <= 0:
            raise UserError(_(
                'No hay monto disponible para crear NC. '
                'Ya existen NC que cubren el total de la factura.'
            ))

        if not self.razon_modificacion:
            raise UserError(_('Debe indicar la razón de modificación.'))

    # ========== ACCIÓN PRINCIPAL ==========
    def action_create_credit_note(self):
        """Crea la Nota de Crédito e-CF tipo 34 como borrador."""
        self.ensure_one()
        self._validate_before_create()

        invoice = self.ref_invoice_id

        # Crear líneas de la NC copiando de la factura original
        invoice_lines = []
        for line in invoice.invoice_line_ids:
            # Solo copiar líneas de producto (no secciones ni notas)
            if line.display_type not in ('line_section', 'line_note'):
                invoice_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.name,
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                    'discount': line.discount,
                    'tax_ids': [(6, 0, line.tax_ids.ids)],
                    'account_id': line.account_id.id,
                }))

        # Valores de la NC
        nc_vals = {
            'move_type': 'out_refund',
            'partner_id': invoice.partner_id.id,
            'journal_id': invoice.journal_id.id,
            'invoice_date': fields.Date.today(),
            'ref': _('NC para %s') % invoice.name,
            'narration': self.razon_modificacion,
            'invoice_line_ids': invoice_lines,
            # Forzar tipo 34 (Nota de Crédito Electrónica)
            'x_tipo_ecf_manual': '34',
            # Campos DGII - x_indicador_nota_credito se calcula automáticamente
            'x_ref_move_id': invoice.id,
            'x_ncf_modificado': invoice.encf,
            'x_fecha_ncf_modificado': invoice.invoice_date,
            'x_codigo_modificacion': self.codigo_modificacion,
            'x_razon_modificacion': self.razon_modificacion,
        }

        # Crear la NC como borrador
        credit_note = self.env['account.move'].create(nc_vals)

        # Log en la factura original
        invoice.message_post(
            body=_('Nota de Crédito %s creada desde este documento. Código de modificación: %s')
            % (credit_note.name or 'Borrador', dict(self._fields['codigo_modificacion'].selection).get(self.codigo_modificacion))
        )

        # Mensaje según tipo de NC
        if self.tipo_nc == 'parcial':
            message = _(
                'Nota de Crédito creada en borrador.\n\n'
                '📝 SIGUIENTE PASO: Edita las líneas de la NC para ajustar '
                'las cantidades o eliminar productos que no deseas acreditar.\n\n'
                'Una vez ajustadas las líneas, confirma la NC.'
            )
            credit_note.message_post(body=message)

        # Retornar acción para ver la NC creada
        return {
            'name': _('Nota de Crédito'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': credit_note.id,
            'target': 'current',
        }
