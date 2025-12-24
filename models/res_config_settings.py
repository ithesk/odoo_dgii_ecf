# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dgii_ecf_api_base_url = fields.Char(
        string='DGII API Base URL',
        help='URL base del microservicio dgii-ecf (ej: http://localhost:3000/api)'
    )
    dgii_ecf_api_key = fields.Char(
        string='DGII API Key',
        help='API Key para autenticación con el microservicio (opcional)'
    )
    dgii_ecf_environment = fields.Selection(
        selection=[
            ('test', 'Test (TesteCF)'),
            ('cert', 'Certificación (CerteCF)'),
            ('prod', 'Producción (eCF)'),
        ],
        string='Ambiente DGII',
        default='test',
        help='Ambiente a utilizar en el microservicio dgii-ecf'
    )

    def set_values(self):
        super().set_values()
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('dgii_ecf.api_base_url', self.dgii_ecf_api_base_url or '')
        params.set_param('dgii_ecf.api_key', self.dgii_ecf_api_key or '')
        params.set_param('dgii_ecf.environment', self.dgii_ecf_environment or 'test')

    @api.model
    def get_values(self):
        res = super().get_values()
        params = self.env['ir.config_parameter'].sudo()
        res.update(
            dgii_ecf_api_base_url=params.get_param('dgii_ecf.api_base_url', default=''),
            dgii_ecf_api_key=params.get_param('dgii_ecf.api_key', default=''),
            dgii_ecf_environment=params.get_param('dgii_ecf.environment', default='test'),
        )
        return res
