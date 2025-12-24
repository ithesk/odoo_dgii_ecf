# -*- coding: utf-8 -*-
import json
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class DgiiTransactionLog(models.Model):
    """
    Modelo para registrar todas las transacciones DGII.
    Permite a usuarios técnicos ver el flujo completo de cada operación.
    """
    _name = 'dgii.transaction.log'
    _description = 'Log de Transacciones DGII'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    # ========== CAMPOS DE IDENTIFICACIÓN ==========
    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True,
    )

    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        ondelete='cascade',
        index=True,
    )

    encf = fields.Char(
        string='e-NCF',
        index=True,
    )

    # ========== TIPO DE OPERACIÓN ==========
    operation_type = fields.Selection(
        selection=[
            ('generate_encf', 'Generación e-NCF'),
            ('build_json', 'Construcción JSON'),
            ('send_invoice', 'Envío Factura'),
            ('send_summary', 'Envío Resumen (Tipo 32)'),
            ('check_status', 'Consulta Estado'),
            ('send_approval', 'Envío Aprobación'),
            ('send_void', 'Envío Anulación'),
            ('api_response', 'Respuesta API'),
            ('api_error', 'Error API'),
            ('validation_error', 'Error Validación'),
            ('rnc_lookup', 'Consulta RNC'),
        ],
        string='Tipo Operación',
        required=True,
        index=True,
    )

    # ========== ESTADO ==========
    state = fields.Selection(
        selection=[
            ('success', 'Exitoso'),
            ('error', 'Error'),
            ('pending', 'Pendiente'),
            ('warning', 'Advertencia'),
        ],
        string='Estado',
        default='pending',
        index=True,
    )

    # ========== DATOS DE LA PETICIÓN ==========
    request_url = fields.Char(
        string='URL',
        help='URL del endpoint llamado',
    )

    request_method = fields.Char(
        string='Método HTTP',
        help='GET, POST, etc.',
    )

    request_headers = fields.Text(
        string='Headers (Request)',
        help='Headers enviados en la petición (sin API key)',
    )

    request_payload = fields.Text(
        string='Payload (JSON Enviado)',
        help='JSON enviado a la API',
    )

    request_payload_formatted = fields.Text(
        string='Payload Formateado',
        compute='_compute_formatted_fields',
    )

    # ========== DATOS DE LA RESPUESTA ==========
    response_status_code = fields.Integer(
        string='Código HTTP',
        help='Código de estado HTTP de la respuesta',
    )

    response_body = fields.Text(
        string='Respuesta (JSON)',
        help='Cuerpo de la respuesta de la API',
    )

    response_body_formatted = fields.Text(
        string='Respuesta Formateada',
        compute='_compute_formatted_fields',
    )

    # ========== DATOS ESPECÍFICOS DGII ==========
    dgii_track_id = fields.Char(
        string='Track ID DGII',
    )

    dgii_status = fields.Char(
        string='Estado DGII',
    )

    dgii_messages = fields.Text(
        string='Mensajes DGII',
    )

    # ========== INFORMACIÓN ADICIONAL ==========
    duration_ms = fields.Integer(
        string='Duración (ms)',
        help='Tiempo que tardó la operación en milisegundos',
    )

    error_message = fields.Text(
        string='Mensaje de Error',
    )

    notes = fields.Text(
        string='Notas',
        help='Notas adicionales o contexto',
    )

    # ========== INFORMACIÓN DEL USUARIO ==========
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        default=lambda self: self.env.user,
        readonly=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        readonly=True,
    )

    # ========== CAMPOS COMPUTADOS ==========
    @api.depends('operation_type', 'encf', 'create_date')
    def _compute_display_name(self):
        operation_labels = dict(self._fields['operation_type'].selection)
        for record in self:
            op_label = operation_labels.get(record.operation_type, record.operation_type)
            date_str = record.create_date.strftime('%Y-%m-%d %H:%M:%S') if record.create_date else ''
            record.display_name = f"{op_label} - {record.encf or 'N/A'} - {date_str}"

    @api.depends('request_payload', 'response_body')
    def _compute_formatted_fields(self):
        for record in self:
            # Formatear payload
            if record.request_payload:
                try:
                    parsed = json.loads(record.request_payload)
                    record.request_payload_formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    record.request_payload_formatted = record.request_payload
            else:
                record.request_payload_formatted = ''

            # Formatear respuesta
            if record.response_body:
                try:
                    parsed = json.loads(record.response_body)
                    record.response_body_formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    record.response_body_formatted = record.response_body
            else:
                record.response_body_formatted = ''

    # ========== MÉTODOS DE CREACIÓN DE LOGS ==========
    @api.model
    def log_operation(self, operation_type, move=None, encf=None, **kwargs):
        """
        Método helper para crear logs de forma sencilla.

        Args:
            operation_type: Tipo de operación (ver selection)
            move: account.move relacionado (opcional)
            encf: e-NCF (opcional, se toma de move si no se provee)
            **kwargs: Campos adicionales del log

        Returns:
            dgii.transaction.log: Registro creado
        """
        vals = {
            'operation_type': operation_type,
            'move_id': move.id if move else False,
            'encf': encf or (move.encf if move else False),
            'state': kwargs.get('state', 'pending'),
        }

        # Campos opcionales
        for field in ['request_url', 'request_method', 'request_headers',
                      'request_payload', 'response_status_code', 'response_body',
                      'dgii_track_id', 'dgii_status', 'dgii_messages',
                      'duration_ms', 'error_message', 'notes']:
            if field in kwargs:
                vals[field] = kwargs[field]

        try:
            return self.create(vals)
        except Exception as e:
            _logger.error(f"Error creando log DGII: {e}")
            return self.browse()  # Retorna recordset vacío

    @api.model
    def log_json_build(self, move, json_data):
        """Log específico para construcción de JSON."""
        return self.log_operation(
            'build_json',
            move=move,
            request_payload=json.dumps(json_data, ensure_ascii=False) if isinstance(json_data, dict) else json_data,
            state='success',
            notes=f"Tipo e-CF: {move.encf[1:3] if move.encf else 'N/A'}",
        )

    @api.model
    def log_api_call(self, move, url, method, payload, response, duration_ms=0):
        """Log específico para llamadas a API."""
        state = 'success'
        error_msg = None
        dgii_track_id = None
        dgii_status = None
        dgii_messages = None

        try:
            resp_json = response.json() if hasattr(response, 'json') else response
            if isinstance(resp_json, dict):
                if not resp_json.get('success', True):
                    state = 'error'
                    error_msg = resp_json.get('error', 'Error desconocido')
                data = resp_json.get('data', {})
                dgii_track_id = data.get('trackId')
                dgii_status = data.get('estado')
                if data.get('mensajes'):
                    dgii_messages = json.dumps(data.get('mensajes'), ensure_ascii=False)
        except:
            pass

        if hasattr(response, 'status_code') and response.status_code >= 400:
            state = 'error'

        return self.log_operation(
            'send_invoice' if '/invoice/' in url else 'api_response',
            move=move,
            request_url=url,
            request_method=method,
            request_payload=json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else payload,
            response_status_code=response.status_code if hasattr(response, 'status_code') else None,
            response_body=response.text if hasattr(response, 'text') else json.dumps(response, ensure_ascii=False),
            dgii_track_id=dgii_track_id,
            dgii_status=dgii_status,
            dgii_messages=dgii_messages,
            duration_ms=duration_ms,
            state=state,
            error_message=error_msg,
        )

    @api.model
    def log_error(self, operation_type, move=None, error_message=None, **kwargs):
        """Log específico para errores."""
        return self.log_operation(
            operation_type,
            move=move,
            state='error',
            error_message=str(error_message) if error_message else None,
            **kwargs,
        )

    # ========== ACCIONES ==========
    def action_view_move(self):
        """Abrir la factura relacionada."""
        self.ensure_one()
        if self.move_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': self.move_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def action_copy_payload(self):
        """Copiar payload al portapapeles (muestra en notificación)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Payload JSON'),
                'message': self.request_payload_formatted or _('Sin payload'),
                'type': 'info',
                'sticky': True,
            }
        }

    def action_copy_response(self):
        """Copiar respuesta al portapapeles (muestra en notificación)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Respuesta API'),
                'message': self.response_body_formatted or _('Sin respuesta'),
                'type': 'info',
                'sticky': True,
            }
        }

    # ========== LIMPIEZA AUTOMÁTICA ==========
    @api.model
    def _cron_cleanup_old_logs(self, days=90):
        """Elimina logs más antiguos que X días."""
        from datetime import timedelta
        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        old_logs = self.search([('create_date', '<', cutoff_date)])
        count = len(old_logs)
        old_logs.unlink()
        _logger.info(f"DGII Log cleanup: eliminados {count} registros anteriores a {cutoff_date}")
        return count
