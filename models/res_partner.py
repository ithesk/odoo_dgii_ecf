# -*- coding: utf-8 -*-
import logging
import requests
import re
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    """Extensión del modelo res.partner para validación de RNC mediante API externa."""
    _inherit = 'res.partner'

    # Hacer el campo name no obligatorio cuando hay RNC
    name = fields.Char(required=False)

    # ========== CAMPOS DGII ==========
    x_nombre_comercial = fields.Char(
        string='Nombre Comercial',
        help='Nombre comercial registrado en DGII'
    )

    x_actividad_economica = fields.Char(
        string='Actividad Económica',
        help='Actividad económica principal registrada en DGII'
    )

    x_regimen_pagos = fields.Char(
        string='Régimen de Pagos',
        help='Régimen de pagos ante la DGII'
    )

    x_estado_dgii = fields.Char(
        string='Estado DGII',
        help='Estado del contribuyente en DGII (ACTIVO, INACTIVO, etc.)'
    )

    x_admin_local = fields.Char(
        string='Administración Local',
        help='Administración local de DGII que gestiona al contribuyente'
    )

    x_facturador_electronico = fields.Selection(
        selection=[
            ('SI', 'Sí'),
            ('NO', 'No'),
            ('N/A', 'N/A'),
        ],
        string='Facturador Electrónico',
        help='Indica si el contribuyente está registrado como facturador electrónico en DGII'
    )

    x_rnc_validado = fields.Boolean(
        string='RNC Validado',
        default=False,
        help='Indica si el RNC fue validado contra la API de DGII'
    )

    x_rnc_ultima_actualizacion = fields.Datetime(
        string='Última Validación RNC',
        readonly=True,
        help='Fecha y hora de la última validación del RNC'
    )

    x_tipo_contribuyente = fields.Selection(
        selection=[
            ('consumo_final', 'Consumidor Final'),
            ('credito_fiscal', 'Crédito Fiscal'),
            ('gubernamental', 'Gubernamental'),
            ('regimen_especial', 'Régimen Especial'),
        ],
        string='Tipo de Contribuyente',
        default='consumo_final',
        required=True,
        help='Tipo de contribuyente para determinar el tipo de comprobante fiscal a emitir:\n'
             '• Consumidor Final: Facturas tipo 32 (NO requiere RNC)\n'
             '• Crédito Fiscal: Facturas tipo 31 (requiere RNC validado)\n'
             '• Gubernamental: Facturas tipo 45 (requiere RNC validado)\n'
             '• Régimen Especial: Facturas tipo 44 (puede o no tener RNC)'
    )

    # ========== CAMPOS UBICACIÓN DGII ==========
    x_dgii_municipio = fields.Char(
        string='Código Municipio DGII',
        size=6,
        help='Código de municipio según catálogo DGII (6 dígitos). Ej: 010100'
    )

    x_dgii_provincia = fields.Char(
        string='Código Provincia DGII',
        size=6,
        help='Código de provincia según catálogo DGII (6 dígitos). Ej: 010000'
    )

    x_dgii_identificador_extranjero = fields.Char(
        string='Identificador Extranjero',
        help='Identificador para clientes extranjeros (usado en e-CF tipo 47)'
    )

    x_dgii_pais_destino = fields.Char(
        string='País Destino',
        help='País de destino para pagos al exterior (e-CF tipo 47)'
    )

    # ========== CAMPOS DIRECTORIO e-CF DGII ==========
    x_dgii_url_recepcion = fields.Char(
        string='URL Recepción e-CF',
        help='URL para recepción de comprobantes fiscales electrónicos del cliente'
    )

    x_dgii_url_aceptacion = fields.Char(
        string='URL Aceptación e-CF',
        help='URL para aceptación comercial de comprobantes fiscales electrónicos'
    )

    x_dgii_url_opcional = fields.Char(
        string='URL Opcional e-CF',
        help='URL opcional adicional del directorio de facturadores electrónicos'
    )

    x_dgii_directorio_validado = fields.Boolean(
        string='Directorio e-CF Validado',
        default=False,
        help='Indica si el cliente fue consultado en el directorio de facturadores electrónicos'
    )

    x_dgii_directorio_ultima_actualizacion = fields.Datetime(
        string='Última Consulta Directorio',
        readonly=True,
        help='Fecha y hora de la última consulta al directorio de facturadores electrónicos'
    )

    # ========== VALIDACIONES ==========
    @api.constrains('name', 'vat')
    def _check_name_or_vat(self):
        """Validar que tenga nombre O RNC."""
        for partner in self:
            if not partner.name and not partner.vat:
                raise ValidationError(_(
                    'Debe proporcionar al menos un Nombre o un RNC/Cédula.'
                ))

    # ========== ONCHANGE - AUTOCOMPLETAR DESDE NOMBRE O VAT ==========
    @api.onchange('name')
    def _onchange_name_detect_rnc(self):
        """
        Detecta si el usuario escribe un RNC/Cédula en el campo nombre
        y automáticamente busca en DGII para autocompletar.
        """
        if not self.name or self.x_rnc_validado:
            return

        # Limpiar el nombre de espacios
        name_clean = self.name.strip()

        # Detectar si parece un RNC (solo números, o formato con guiones)
        # RNC: 9 dígitos, Cédula: 11 dígitos
        rnc_normalized = self._normalize_rnc(name_clean)

        # Si tiene entre 9 y 11 dígitos, es probablemente un RNC/Cédula
        if rnc_normalized and len(rnc_normalized) >= 9 and len(rnc_normalized) <= 11:
            # Verificar que el nombre original sea principalmente números
            # (permitir guiones y espacios)
            chars_no_digits = re.sub(r'[\d\s\-]', '', name_clean)
            if len(chars_no_digits) == 0:  # Solo tenía números, guiones o espacios
                # Mover el RNC al campo VAT
                self.vat = rnc_normalized
                # Poner nombre temporal
                self.name = f'Buscando RNC: {rnc_normalized}...'
                # Intentar buscar automáticamente
                try:
                    response = self._call_rnc_api(rnc_normalized)
                    self._process_rnc_response_onchange(response, rnc_normalized)
                except Exception:
                    # Si falla la API, dejar el nombre temporal
                    self.name = f'RNC: {rnc_normalized}'

    @api.onchange('vat')
    def _onchange_vat_autofill_name(self):
        """
        Cuando se ingresa un RNC y el nombre está vacío,
        auto-llenar con 'RNC: [número]' como placeholder temporal.
        Esto permite guardar el registro antes de validar.
        """
        # Solo aplicar si:
        # 1. Hay un VAT ingresado
        # 2. No hay nombre todavía (o es un nombre temporal anterior)
        # 3. El RNC no ha sido validado aún
        if self.vat and not self.x_rnc_validado:
            # Si no hay nombre O es un nombre temporal previo de RNC
            if not self.name or self.name.startswith('RNC: ') or self.name.startswith('Buscando'):
                # Normalizar el RNC para mostrarlo limpio
                rnc_limpio = self._normalize_rnc(self.vat)
                if rnc_limpio:
                    # Intentar buscar automáticamente
                    try:
                        response = self._call_rnc_api(rnc_limpio)
                        self._process_rnc_response_onchange(response, rnc_limpio)
                    except Exception:
                        # Si falla, poner nombre temporal
                        self.name = f'RNC: {rnc_limpio}'

    # ========== MÉTODOS DE VALIDACIÓN RNC ==========
    def _normalize_rnc(self, rnc):
        """
        Normaliza el RNC eliminando guiones y dejando solo dígitos.

        Args:
            rnc (str): RNC a normalizar

        Returns:
            str: RNC normalizado (solo dígitos)
        """
        if not rnc:
            return ''
        # Eliminar guiones, espacios y caracteres especiales
        return re.sub(r'[^0-9]', '', rnc)

    def action_validate_rnc(self):
        """
        Acción del botón para validar y autocompletar datos del RNC
        mediante la API externa de Megaplus.
        """
        self.ensure_one()

        if not self.vat:
            raise UserError(_(
                'Debe ingresar un RNC o Cédula antes de validar.'
            ))

        # Normalizar RNC
        rnc_normalized = self._normalize_rnc(self.vat)

        if not rnc_normalized:
            raise UserError(_(
                'El RNC o Cédula ingresado no es válido.'
            ))

        # Llamar a la API
        try:
            response = self._call_rnc_api(rnc_normalized)
        except Exception as e:
            raise UserError(_(
                'Error al consultar la API de validación de RNC:\n\n%s'
            ) % str(e))

        # Procesar respuesta y actualizar campos
        self._process_rnc_response(response, rnc_normalized)

        # Consultar directorio de facturadores electrónicos para obtener URLs
        directory_message = ''
        try:
            directory_response = self._call_customer_directory_api(rnc_normalized)
            if directory_response:
                self._process_directory_response(directory_response)
                directory_message = _(' También se obtuvieron las URLs del directorio de facturadores electrónicos.')
        except Exception as e:
            _logger.warning(f"Error consultando directorio e-CF: {e}")

        # Refrescar el formulario para mostrar los datos actualizados
        # Esto es importante para que el usuario vea el nombre autocompletado
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('✓ RNC Validado Correctamente'),
                'message': _('Los datos del contribuyente fueron autocompletados desde DGII. '
                           'El nombre, actividad económica y demás campos se han actualizado.') + directory_message,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window_close',
                }
            }
        }

    def _call_rnc_api(self, rnc):
        """
        Realiza la llamada a la API de Megaplus para consultar el RNC.

        Args:
            rnc (str): RNC normalizado a consultar

        Returns:
            dict: Respuesta de la API en formato JSON

        Raises:
            Exception: Si hay error en la llamada a la API
        """
        api_url = 'https://rnc.megaplus.com.do/api/consulta'
        params = {'rnc': rnc}

        try:
            response = requests.get(api_url, params=params, timeout=10)

            # Intentar parsear JSON antes de verificar status
            try:
                data = response.json()
            except ValueError:
                raise Exception(_('La respuesta de la API no es un JSON válido.'))

            # Si la API devuelve error en el JSON, manejarlo
            if data.get('error') is True:
                mensaje = data.get('mensaje', 'Error desconocido')
                codigo = data.get('codigo_http', response.status_code)

                if codigo == 404:
                    raise Exception(_(
                        'El RNC/Cédula "%s" no está inscrito como contribuyente en DGII.\n\n'
                        'Por favor verifique:\n'
                        '• Que el número esté correcto\n'
                        '• Que el contribuyente esté registrado en DGII\n'
                        '• Que sea un RNC/Cédula válido'
                    ) % rnc)
                else:
                    raise Exception(_('Error de la API DGII: %s (Código: %s)') % (mensaje, codigo))

            # Si todo está bien, devolver los datos
            return data

        except requests.exceptions.Timeout:
            raise Exception(_('Tiempo de espera agotado al conectar con la API de RNC.'))
        except requests.exceptions.ConnectionError:
            raise Exception(_('No se pudo conectar con la API de RNC. Verifique su conexión a internet.'))
        except requests.exceptions.RequestException as e:
            raise Exception(_('Error al consultar RNC: %s') % str(e))

    def _call_customer_directory_api(self, rnc, environment='prod'):
        """
        Consulta el directorio de clientes de facturación electrónica de DGII.
        Obtiene las URLs de recepción, aceptación y opcional del contribuyente.

        Args:
            rnc (str): RNC normalizado a consultar
            environment (str): Ambiente de consulta ('prod' o 'test')

        Returns:
            dict: Respuesta de la API con URLs del directorio o None si no está registrado

        Raises:
            Exception: Si hay error en la llamada a la API
        """
        api_url = f'https://dgii.ithesk.com/api/invoice/customer-directory/{rnc}'
        params = {'environment': environment}
        headers = {
            'X-API-Key': 'development_api_key_123',
            'Accept': 'application/json',
        }

        try:
            _logger.info(f"Consultando directorio e-CF para RNC: {rnc}")
            response = requests.get(api_url, params=params, headers=headers, timeout=15)

            # Si el cliente no está en el directorio (404), retornar None
            if response.status_code == 404:
                _logger.info(f"RNC {rnc} no está registrado en el directorio de facturadores electrónicos")
                return None

            # Intentar parsear JSON
            try:
                data = response.json()
            except ValueError:
                _logger.warning(f"Respuesta del directorio no es JSON válido: {response.text[:200]}")
                return None

            # Verificar si hay error en la respuesta
            if data.get('error') is True or data.get('success') is False:
                mensaje = data.get('message', data.get('mensaje', 'Error desconocido'))
                _logger.warning(f"Error en directorio e-CF: {mensaje}")
                return None

            _logger.info(f"Respuesta directorio e-CF para RNC {rnc}: {data}")
            return data

        except requests.exceptions.Timeout:
            _logger.warning(f"Timeout consultando directorio e-CF para RNC: {rnc}")
            return None
        except requests.exceptions.ConnectionError:
            _logger.warning(f"Error de conexión consultando directorio e-CF para RNC: {rnc}")
            return None
        except requests.exceptions.RequestException as e:
            _logger.warning(f"Error consultando directorio e-CF: {e}")
            return None

    def _process_directory_response(self, response):
        """
        Procesa la respuesta del directorio de clientes y actualiza los campos.

        Args:
            response (dict): Respuesta de la API del directorio
        """
        if not response:
            return

        vals = {
            'x_dgii_directorio_validado': True,
            'x_dgii_directorio_ultima_actualizacion': fields.Datetime.now(),
        }

        # Extraer URLs del directorio
        # La API puede devolver los datos directamente o dentro de un objeto 'data'
        data = response.get('data', response)

        # URL de Recepción
        url_recepcion = data.get('urlRecepcion', data.get('url_recepcion', data.get('URL Recepción', '')))
        if url_recepcion:
            vals['x_dgii_url_recepcion'] = url_recepcion

        # URL de Aceptación
        url_aceptacion = data.get('urlAceptacion', data.get('url_aceptacion', data.get('URL Aceptación', '')))
        if url_aceptacion:
            vals['x_dgii_url_aceptacion'] = url_aceptacion

        # URL Opcional
        url_opcional = data.get('urlOpcional', data.get('url_opcional', data.get('URL Opcional', '')))
        if url_opcional:
            vals['x_dgii_url_opcional'] = url_opcional

        # Si el facturador electrónico viene en la respuesta del directorio, actualizar
        if data.get('facturadorElectronico') or data.get('facturador_electronico'):
            vals['x_facturador_electronico'] = 'SI'

        _logger.info(f"Actualizando partner con datos del directorio: {vals}")
        self.write(vals)

    def _process_rnc_response(self, response, rnc_normalized):
        """
        Procesa la respuesta de la API y actualiza los campos del partner.

        Args:
            response (dict): Respuesta de la API
            rnc_normalized (str): RNC normalizado

        Raises:
            UserError: Si el estado no es ACTIVO
        """
        # Mapeo según estructura real de la API Megaplus:
        # {
        #   "error": false,
        #   "codigo_http": 200,
        #   "mensaje": "Consulta Exitosa",
        #   "cedula_rnc": "133-52499-6",
        #   "nombre_razon_social": "NOMBRE EMPRESA",
        #   "nombre_comercial": "NOMBRE COMERCIAL",
        #   "regimen_de_pagos": "NORMAL",
        #   "estado": "ACTIVO",
        #   "actividad_economica": "DESCRIPCION",
        #   "administracion_local": "ADM LOCAL",
        #   "facturador_electronico": "SI" o "NO",
        # }

        # Actualizar VAT con el RNC formateado de la API (con guiones)
        vat_formatted = response.get('cedula_rnc', rnc_normalized)

        vals = {
            'vat': vat_formatted,
            'x_rnc_validado': True,
            'x_rnc_ultima_actualizacion': fields.Datetime.now(),
        }

        # Nombre comercial
        if 'nombre_comercial' in response:
            vals['x_nombre_comercial'] = response.get('nombre_comercial', '')

        # Nombre/Razón social - SIEMPRE actualizar desde la API si viene
        if 'nombre_razon_social' in response:
            nombre_api = response.get('nombre_razon_social', '').strip()
            if nombre_api:
                vals['name'] = nombre_api

        # Actividad económica
        if 'actividad_economica' in response:
            vals['x_actividad_economica'] = response.get('actividad_economica', '')

        # Régimen de pagos
        if 'regimen_de_pagos' in response:
            vals['x_regimen_pagos'] = response.get('regimen_de_pagos', '')

        # Estado
        if 'estado' in response:
            estado = response.get('estado', '').upper()
            vals['x_estado_dgii'] = estado

            # Advertir si no está activo
            if estado != 'ACTIVO':
                # Se podría bloquear aquí, pero por ahora solo advertimos
                try:
                    self.message_post(
                        body=_('⚠️ ADVERTENCIA: El RNC consultado tiene estado "%s" en DGII. '
                               'Se recomienda verificar antes de realizar operaciones.') % estado,
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
                except:
                    # Si falla el message_post (no tiene mail instalado), continuar
                    pass

        # Administración local
        if 'administracion_local' in response:
            vals['x_admin_local'] = response.get('administracion_local', '')

        # Facturador electrónico
        if 'facturador_electronico' in response:
            fe = response.get('facturador_electronico', '').upper()
            if fe in ['SI', 'SÍ', 'YES', 'S', 'Y']:
                vals['x_facturador_electronico'] = 'SI'
            elif fe in ['NO', 'N']:
                vals['x_facturador_electronico'] = 'NO'
            else:
                vals['x_facturador_electronico'] = 'N/A'

        # Marcar como compañía si tiene RNC
        if len(rnc_normalized) >= 9:  # RNC tiene 9+ dígitos
            vals['is_company'] = True

        # Determinar automáticamente el tipo de contribuyente según el estado DGII
        estado = vals.get('x_estado_dgii', '').upper()

        # Si el estado es ACTIVO, es contribuyente fiscal
        if estado == 'ACTIVO':
            # Por defecto Crédito Fiscal
            vals['x_tipo_contribuyente'] = 'credito_fiscal'

            # Si detectamos que es gubernamental (esto puede mejorarse con más lógica)
            nombre = vals.get('name', '').upper()
            if any(keyword in nombre for keyword in ['AYUNTAMIENTO', 'MINISTERIO', 'GOBIERNO', 'MUNICIPAL']):
                vals['x_tipo_contribuyente'] = 'gubernamental'
        else:
            # Si no está activo, dejarlo como consumo final
            vals['x_tipo_contribuyente'] = 'consumo_final'

        # Actualizar campos
        _logger.warning("========== _process_rnc_response ==========")
        _logger.warning(f"Partner ID: {self.id}")
        _logger.warning(f"Vals a escribir: {vals}")
        self.write(vals)
        _logger.warning(f"Write completado. Partner ahora: name={self.name}, "
                       f"x_rnc_validado={self.x_rnc_validado}, "
                       f"x_estado_dgii={self.x_estado_dgii}")

    def _process_rnc_response_onchange(self, response, rnc_normalized):
        """
        Procesa la respuesta de la API durante onchange (sin guardar en BD).
        Asigna los valores directamente a self para que se vean en el formulario.
        """
        # Actualizar VAT con el RNC formateado
        vat_formatted = response.get('cedula_rnc', rnc_normalized)
        self.vat = vat_formatted
        self.x_rnc_validado = True

        # Nombre comercial
        if 'nombre_comercial' in response:
            self.x_nombre_comercial = response.get('nombre_comercial', '')

        # Nombre/Razón social
        if 'nombre_razon_social' in response:
            nombre_api = response.get('nombre_razon_social', '').strip()
            if nombre_api:
                self.name = nombre_api

        # Actividad económica
        if 'actividad_economica' in response:
            self.x_actividad_economica = response.get('actividad_economica', '')

        # Régimen de pagos
        if 'regimen_de_pagos' in response:
            self.x_regimen_pagos = response.get('regimen_de_pagos', '')

        # Estado
        if 'estado' in response:
            estado = response.get('estado', '').upper()
            self.x_estado_dgii = estado

        # Administración local
        if 'administracion_local' in response:
            self.x_admin_local = response.get('administracion_local', '')

        # Facturador electrónico
        if 'facturador_electronico' in response:
            fe = response.get('facturador_electronico', '').upper()
            if fe in ['SI', 'SÍ', 'YES', 'S', 'Y']:
                self.x_facturador_electronico = 'SI'
            elif fe in ['NO', 'N']:
                self.x_facturador_electronico = 'NO'
            else:
                self.x_facturador_electronico = 'N/A'

        # Marcar como compañía si tiene RNC
        if len(rnc_normalized) >= 9:
            self.is_company = True

        # Determinar tipo de contribuyente
        estado = self.x_estado_dgii or ''
        if estado.upper() == 'ACTIVO':
            self.x_tipo_contribuyente = 'credito_fiscal'
            # Detectar gubernamental
            nombre = (self.name or '').upper()
            if any(kw in nombre for kw in ['AYUNTAMIENTO', 'MINISTERIO', 'GOBIERNO', 'MUNICIPAL']):
                self.x_tipo_contribuyente = 'gubernamental'
        else:
            self.x_tipo_contribuyente = 'consumo_final'

    def write(self, vals):
        """
        Sobrescribe write para marcar como no validado si se modifica el VAT manualmente.
        Solo resetea x_rnc_validado si el VAT cambió Y no viene de una validación.
        """
        _logger.warning("========== WRITE PARTNER ==========")
        _logger.warning(f"Partner IDs: {self.ids}")
        _logger.warning(f"Vals recibidos: {vals}")
        _logger.warning(f"Campos DGII en vals: x_rnc_validado={vals.get('x_rnc_validado')}, "
                       f"x_estado_dgii={vals.get('x_estado_dgii')}, "
                       f"x_nombre_comercial={vals.get('x_nombre_comercial')}, "
                       f"x_tipo_contribuyente={vals.get('x_tipo_contribuyente')}")

        # Si se modifica el VAT y no es desde la validación
        if 'vat' in vals and 'x_rnc_validado' not in vals:
            # Verificar si el VAT realmente cambió
            for partner in self:
                old_vat = self._normalize_rnc(partner.vat or '')
                new_vat = self._normalize_rnc(vals.get('vat') or '')
                _logger.warning(f"Comparando VAT: old='{old_vat}' vs new='{new_vat}'")
                # Solo resetear si el VAT es diferente (no solo formato)
                if old_vat != new_vat:
                    _logger.warning("VAT cambió! Reseteando x_rnc_validado a False")
                    vals['x_rnc_validado'] = False
                    break
                else:
                    _logger.warning("VAT no cambió, NO reseteamos x_rnc_validado")

        result = super(ResPartner, self).write(vals)

        # Log después del write
        for partner in self:
            _logger.warning(f"DESPUÉS de write - Partner {partner.id}: "
                           f"name={partner.name}, vat={partner.vat}, "
                           f"x_rnc_validado={partner.x_rnc_validado}, "
                           f"x_estado_dgii={partner.x_estado_dgii}, "
                           f"x_tipo_contribuyente={partner.x_tipo_contribuyente}")

        return result

    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobrescribe create para validar RNC automáticamente si viene con VAT.
        Si el nombre parece ser temporal (RNC: xxx o Buscando...),
        intenta buscar en DGII y actualizar los datos.
        """
        _logger.warning("========== CREATE PARTNER ==========")
        _logger.warning(f"Vals list recibidos: {vals_list}")

        # Log campos DGII en cada vals
        for i, vals in enumerate(vals_list):
            _logger.warning(f"Vals[{i}] campos DGII: "
                           f"name={vals.get('name')}, "
                           f"vat={vals.get('vat')}, "
                           f"x_rnc_validado={vals.get('x_rnc_validado')}, "
                           f"x_estado_dgii={vals.get('x_estado_dgii')}, "
                           f"x_nombre_comercial={vals.get('x_nombre_comercial')}, "
                           f"x_tipo_contribuyente={vals.get('x_tipo_contribuyente')}, "
                           f"x_actividad_economica={vals.get('x_actividad_economica')}")

        records = super(ResPartner, self).create(vals_list)

        _logger.warning(f"Records creados: {records.ids}")

        # Log después de crear
        for record in records:
            _logger.warning(f"DESPUÉS de create - Partner {record.id}: "
                           f"name={record.name}, vat={record.vat}, "
                           f"x_rnc_validado={record.x_rnc_validado}, "
                           f"x_estado_dgii={record.x_estado_dgii}, "
                           f"x_tipo_contribuyente={record.x_tipo_contribuyente}")

        # Post-create: validar RNC automáticamente si es necesario
        # IMPORTANTE: Si tiene VAT pero NO tiene x_rnc_validado, buscar en DGII
        # (porque los campos del onchange no se envían al servidor)
        for record in records:
            _logger.warning(f"Verificando record {record.id}: vat={record.vat}, "
                           f"x_rnc_validado={record.x_rnc_validado}, name={record.name}")

            if record.vat and not record.x_rnc_validado:
                rnc_normalized = record._normalize_rnc(record.vat)
                _logger.warning(f"Tiene VAT pero NO x_rnc_validado. RNC normalizado: {rnc_normalized}")

                if rnc_normalized and len(rnc_normalized) >= 9:
                    try:
                        _logger.warning(f"Llamando API DGII para RNC: {rnc_normalized}")
                        response = record._call_rnc_api(rnc_normalized)
                        _logger.warning(f"Respuesta API: {response}")
                        record._process_rnc_response(response, rnc_normalized)
                        _logger.warning(f"Después de _process_rnc_response: "
                                       f"name={record.name}, x_rnc_validado={record.x_rnc_validado}")

                        # Consultar directorio de facturadores electrónicos
                        try:
                            directory_response = record._call_customer_directory_api(rnc_normalized)
                            if directory_response:
                                record._process_directory_response(directory_response)
                                _logger.info(f"Directorio e-CF procesado para RNC: {rnc_normalized}")
                        except Exception as dir_e:
                            _logger.warning(f"Error consultando directorio e-CF: {dir_e}")
                    except Exception as e:
                        _logger.warning(f"ERROR en API DGII: {e}")
                        # Si falla, marcar como no validado pero no cambiar nombre
                        pass
            else:
                _logger.warning(f"No necesita validar: vat={bool(record.vat)}, "
                               f"x_rnc_validado={record.x_rnc_validado}")

        return records
