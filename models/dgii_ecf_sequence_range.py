# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import date, timedelta


class DgiiEcfSequenceRange(models.Model):
    """
    Modelo para gestionar rangos de secuencias de e-NCF (Comprobantes Fiscales Electrónicos)
    según normativa DGII de República Dominicana.
    """
    _name = 'dgii.ecf.sequence.range'
    _description = 'Rangos de Secuencias e-NCF DGII'
    _order = 'fecha_vencimiento desc, tipo_ecf, establecimiento, punto_emision'
    _rec_name = 'name'

    # ========== CAMPOS BÁSICOS ==========
    name = fields.Char(
        string='Nombre',
        required=True,
        copy=False,
        help='Nombre descriptivo del rango de secuencia'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        help='Compañía a la que pertenece este rango'
    )

    # ========== TIPO DE COMPROBANTE ==========
    tipo_ecf = fields.Selection(
        selection=[
            ('31', '31 – Factura de Crédito Fiscal Electrónica'),
            ('32', '32 – Factura de Consumo Electrónica'),
            ('33', '33 – Nota de Débito Electrónica'),
            ('34', '34 – Nota de Crédito Electrónica'),
            ('41', '41 – Comprobante Electrónico de Compras'),
            ('43', '43 – Comprobante Electrónico para Gastos Menores'),
            ('44', '44 – Comprobante Electrónico para Regímenes Especiales'),
            ('45', '45 – Comprobante Electrónico Gubernamental'),
            ('46', '46 – Comprobante Electrónico para Exportaciones'),
            ('47', '47 – Comprobante Electrónico para Pagos al Exterior'),
        ],
        string='Tipo e-CF',
        required=True,
        help='Tipo de Comprobante Fiscal Electrónico según normativa DGII'
    )

    # ========== IDENTIFICACIÓN DEL EMISOR ==========
    establecimiento = fields.Char(
        string='Establecimiento',
        size=3,
        required=True,
        help='Código de establecimiento (3 dígitos numéricos)'
    )

    punto_emision = fields.Char(
        string='Punto de Emisión',
        size=3,
        required=True,
        help='Código de punto de emisión (3 dígitos numéricos)'
    )

    # ========== RANGO DE SECUENCIAS ==========
    secuencia_desde = fields.Integer(
        string='Secuencia Desde',
        required=True,
        help='Número inicial del rango autorizado por DGII'
    )

    secuencia_hasta = fields.Integer(
        string='Secuencia Hasta',
        required=True,
        help='Número final del rango autorizado por DGII'
    )

    secuencia_actual = fields.Integer(
        string='Secuencia Actual',
        readonly=True,
        help='Última secuencia utilizada (se inicializa en secuencia_desde - 1)'
    )

    # ========== FECHAS ==========
    fecha_vencimiento = fields.Date(
        string='Fecha de Vencimiento',
        required=True,
        help='Fecha en que vence la autorización de este rango'
    )

    # ========== ESTADO ==========
    estado = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('activo', 'Activo'),
            ('agotado', 'Agotado'),
            ('vencido', 'Vencido'),
            ('anulado', 'Anulado'),
        ],
        string='Estado',
        default='draft',
        required=True,
        help='Estado actual del rango de secuencias'
    )

    # ========== RELACIONES ==========
    journal_ids = fields.Many2many(
        'account.journal',
        'dgii_ecf_range_journal_rel',
        'range_id',
        'journal_id',
        string='Diarios',
        help='Diarios contables que pueden usar este rango'
    )

    # ========== CONFIGURACIÓN ==========
    es_electronico = fields.Boolean(
        string='Es Electrónico',
        default=True,
        help='Indica si este rango es para comprobantes electrónicos'
    )

    # ========== CAMPOS COMPUTADOS ==========
    secuencias_disponibles = fields.Integer(
        string='Secuencias Disponibles',
        compute='_compute_secuencias_disponibles',
        store=True,
        help='Cantidad de secuencias aún disponibles en este rango'
    )

    porcentaje_usado = fields.Float(
        string='% Usado',
        compute='_compute_porcentaje_usado',
        store=True,
        help='Porcentaje del rango que ha sido utilizado'
    )

    dias_para_vencer = fields.Integer(
        string='Días para Vencer',
        compute='_compute_dias_para_vencer',
        store=True,
        search='_search_dias_para_vencer',
        help='Días restantes hasta la fecha de vencimiento'
    )

    # ========== MÉTODOS COMPUTADOS ==========
    @api.depends('secuencia_desde', 'secuencia_hasta', 'secuencia_actual')
    def _compute_secuencias_disponibles(self):
        """Calcula la cantidad de secuencias disponibles."""
        for record in self:
            if record.secuencia_hasta and record.secuencia_actual is not False:
                record.secuencias_disponibles = record.secuencia_hasta - record.secuencia_actual
            else:
                record.secuencias_disponibles = 0

    @api.depends('secuencia_desde', 'secuencia_hasta', 'secuencia_actual')
    def _compute_porcentaje_usado(self):
        """Calcula el porcentaje de uso del rango."""
        for record in self:
            if record.secuencia_hasta and record.secuencia_desde:
                total = record.secuencia_hasta - record.secuencia_desde + 1
                usado = record.secuencia_actual - record.secuencia_desde + 1
                record.porcentaje_usado = (usado / total * 100.0) if total > 0 else 0.0
            else:
                record.porcentaje_usado = 0.0

    @api.depends('fecha_vencimiento')
    def _compute_dias_para_vencer(self):
        """Calcula los días restantes hasta el vencimiento."""
        for record in self:
            if record.fecha_vencimiento:
                delta = record.fecha_vencimiento - date.today()
                record.dias_para_vencer = delta.days
            else:
                record.dias_para_vencer = 0

    def _search_dias_para_vencer(self, operator, value):
        """Permite buscar por días para vencer usando fecha_vencimiento."""
        target_date = date.today() + timedelta(days=value)
        return [('fecha_vencimiento', operator, target_date)]

    # ========== VALIDACIONES ==========
    @api.constrains('secuencia_desde', 'secuencia_hasta')
    def _check_secuencia_range(self):
        """Valida que secuencia_desde sea menor o igual a secuencia_hasta."""
        for record in self:
            if record.secuencia_desde > record.secuencia_hasta:
                raise ValidationError(_(
                    'La secuencia inicial (%s) no puede ser mayor que la secuencia final (%s).'
                ) % (record.secuencia_desde, record.secuencia_hasta))

    @api.constrains('establecimiento')
    def _check_establecimiento(self):
        """Valida que el establecimiento tenga exactamente 3 dígitos numéricos."""
        for record in self:
            if record.establecimiento:
                if len(record.establecimiento) != 3:
                    raise ValidationError(_(
                        'El código de establecimiento debe tener exactamente 3 dígitos.'
                    ))
                if not record.establecimiento.isdigit():
                    raise ValidationError(_(
                        'El código de establecimiento debe contener solo dígitos numéricos.'
                    ))

    @api.constrains('punto_emision')
    def _check_punto_emision(self):
        """Valida que el punto de emisión tenga exactamente 3 dígitos numéricos."""
        for record in self:
            if record.punto_emision:
                if len(record.punto_emision) != 3:
                    raise ValidationError(_(
                        'El código de punto de emisión debe tener exactamente 3 dígitos.'
                    ))
                if not record.punto_emision.isdigit():
                    raise ValidationError(_(
                        'El código de punto de emisión debe contener solo dígitos numéricos.'
                    ))

    @api.constrains('tipo_ecf', 'establecimiento', 'punto_emision', 'secuencia_desde', 'secuencia_hasta', 'estado', 'company_id')
    def _check_overlapping_ranges(self):
        """
        Valida que no existan rangos activos solapados para el mismo tipo de e-CF,
        establecimiento y punto de emisión.
        """
        for record in self:
            if record.estado in ['activo']:
                overlapping = self.search([
                    ('id', '!=', record.id),
                    ('company_id', '=', record.company_id.id),
                    ('tipo_ecf', '=', record.tipo_ecf),
                    ('establecimiento', '=', record.establecimiento),
                    ('punto_emision', '=', record.punto_emision),
                    ('estado', 'in', ['activo']),
                    '|',
                    '&',
                    ('secuencia_desde', '<=', record.secuencia_hasta),
                    ('secuencia_hasta', '>=', record.secuencia_desde),
                    '&',
                    ('secuencia_desde', '>=', record.secuencia_desde),
                    ('secuencia_hasta', '<=', record.secuencia_hasta),
                ])
                if overlapping:
                    raise ValidationError(_(
                        'Ya existe un rango activo que se solapa con este rango para el mismo '
                        'tipo de e-CF, establecimiento y punto de emisión.\n'
                        'Rango(s) en conflicto: %s'
                    ) % ', '.join(overlapping.mapped('name')))

    # ========== MÉTODOS CRUD ==========
    @api.model_create_multi
    def create(self, vals_list):
        """Inicializa secuencia_actual en secuencia_desde - 1."""
        for vals in vals_list:
            if 'secuencia_actual' not in vals and 'secuencia_desde' in vals:
                vals['secuencia_actual'] = vals['secuencia_desde'] - 1
        return super(DgiiEcfSequenceRange, self).create(vals_list)

    # ========== MÉTODOS DE ACCIÓN ==========
    def action_activar(self):
        """Activa el rango para su uso."""
        for record in self:
            if record.estado != 'draft':
                raise UserError(_('Solo los rangos en estado borrador pueden ser activados.'))
            if record.fecha_vencimiento < date.today():
                raise UserError(_('No se puede activar un rango con fecha de vencimiento pasada.'))
            record.estado = 'activo'

    def action_anular(self):
        """Anula el rango."""
        for record in self:
            if record.estado in ['agotado', 'vencido']:
                raise UserError(_('No se pueden anular rangos agotados o vencidos.'))
            record.estado = 'anulado'

    # ========== MÉTODOS DE NEGOCIO ==========
    def get_next_sequence_number(self):
        """
        Obtiene el siguiente número de secuencia disponible.
        Incluye locking para evitar duplicados en entornos concurrentes.

        Returns:
            int: Siguiente número de secuencia

        Raises:
            UserError: Si el rango está agotado o no está activo
        """
        self.ensure_one()

        # Bloqueo pesimista para evitar race conditions
        self.env.cr.execute(
            "SELECT id FROM dgii_ecf_sequence_range WHERE id=%s FOR UPDATE NOWAIT",
            (self.id,),
            log_exceptions=False
        )

        # Recargar el registro para obtener el estado más reciente
        self.invalidate_recordset(['secuencia_actual', 'estado'])

        if self.estado != 'activo':
            raise UserError(_(
                'El rango de secuencias "%s" no está activo (estado: %s).'
            ) % (self.name, dict(self._fields['estado'].selection).get(self.estado)))

        next_number = self.secuencia_actual + 1

        if next_number > self.secuencia_hasta:
            self.estado = 'agotado'
            raise UserError(_(
                'El rango de secuencias "%s" está agotado. '
                'Última secuencia disponible: %s'
            ) % (self.name, self.secuencia_hasta))

        # Actualizar secuencia actual
        self.secuencia_actual = next_number

        # Marcar como agotado si alcanzamos el límite
        if self.secuencia_actual >= self.secuencia_hasta:
            self.estado = 'agotado'

        return next_number

    @api.model
    def check_expired_ranges(self):
        """
        Método llamado por cron job para marcar rangos vencidos.
        También puede enviar alertas de vencimiento próximo.
        """
        today = date.today()

        # Marcar rangos vencidos
        expired_ranges = self.search([
            ('estado', '=', 'activo'),
            ('fecha_vencimiento', '<', today)
        ])

        if expired_ranges:
            expired_ranges.write({'estado': 'vencido'})

        # Opcional: Alertas para rangos próximos a vencer (7 días)
        # Aquí se puede implementar lógica de notificación

        return True
