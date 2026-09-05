import base64
import csv
import io
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from .lead_source import ESTRATO_LABELS

_logger = logging.getLogger(__name__)


class CrmLeadRequest(models.Model):
    """Solicitud de generación masiva de leads/oportunidades desde fuentes externas.

    Alíneado con la arquitectura canónica de Odoo (crm_iap_mine):
    draft -> done / error.
    """

    _name = 'crm.lead.request'
    _description = 'Solicitud de Generación de Leads'
    _order = 'id desc'

    name = fields.Char(string='Descripción', required=True, default=lambda self: _('Nueva Solicitud'))
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Completado'),
        ('error', 'Error'),
    ], string='Estado', default='draft', readonly=True, index=True)

    source_key = fields.Selection(
        selection=lambda self: self.env['lead.source.registry'].list_sources(),
        string='Fuente de Datos', required=True, default='denue')

    lead_type = fields.Selection([
        ('lead', 'Lead'),
        ('opportunity', 'Oportunidad'),
    ], string='Generar como', default='lead', required=True)

    lead_number = fields.Integer(string='Cantidad de Leads', default=10, required=True,
                                 help='Número de prospectos a generar.')

    team_id = fields.Many2one('crm.team', string='Equipo de Ventas',
                              default=lambda self: self.env['crm.team']._get_default_team_id(user_id=self.env.uid))
    user_id = fields.Many2one('res.users', string='Vendedor Asignado', default=lambda self: self.env.user)
    tag_ids = fields.Many2many('crm.tag', string='Etiquetas')

    lead_ids = fields.One2many('crm.lead', 'lead_request_id', string='Leads Generados', readonly=True)
    lead_count = fields.Integer(string='Leads Creados', compute='_compute_lead_count')

    error_type = fields.Char(string='Tipo de Error', readonly=True)
    error_msg = fields.Text(string='Mensaje de Error', readonly=True)

    # --- Criterios DENUE (INEGI) ---
    entidad_ids = fields.Many2many('crm.denue.entidad', string='Estados (Entidades)')
    sector_ids = fields.Many2many('crm.denue.sector', string='Sectores Económicos')
    estrato_min = fields.Selection(
        selection=[(str(i), ESTRATO_LABELS[i]) for i in range(1, 8)],
        string='Tamaño mínimo', default='1')
    estrato_max = fields.Selection(
        selection=[(str(i), ESTRATO_LABELS[i]) for i in range(1, 8)],
        string='Tamaño máximo', default='7')
    actividad = fields.Char(string='Giro / Actividad o palabras clave')
    nombre_busqueda = fields.Char(string='Razón social / Nombre del negocio')
    search_type = fields.Selection([
        ('by_activity_state', 'Por actividad / palabra clave'),
        ('by_state', 'Por sector económico'),
        ('by_name_state', 'Por nombre de negocio'),
    ], string='Tipo de búsqueda DENUE', required=True, default='by_activity_state')

    # --- Criterios YELP ---
    yelp_term = fields.Char(string='Término de búsqueda',
                            help='Palabra clave (ej: "restaurante", "plomería")')
    yelp_location = fields.Char(string='Ubicación',
                                help='Ciudad o estado (ej: "San Luis Potosí", "Querétaro")')
    yelp_categories = fields.Many2many('crm.yelp.category', string='Categorías Yelp')

    # --- Criterios GOOGLE PLACES ---
    google_query = fields.Char(string='Término de búsqueda',
                               help='Giro o palabra clave (ej: "despacho contable", "dentista")')
    google_location = fields.Char(string='Ubicación',
                                  help='Ciudad o estado (ej: "San Luis Potosí, SLP")')
    google_place_type_ids = fields.Many2many('crm.google.place.type', string='Tipo de establecimiento')

    @api.depends('lead_ids')
    def _compute_lead_count(self):
        leads_data = self.env['crm.lead']._read_group(
            [('lead_request_id', 'in', self.ids)],
            ['lead_request_id'], ['__count'],
        )
        mapped = {request.id: count for request, count in leads_data}
        for request in self:
            request.lead_count = mapped.get(request.id, 0)

    @api.onchange('lead_number')
    def _onchange_lead_number(self):
        if self.lead_number <= 0:
            self.lead_number = 1

    @api.onchange('estrato_min', 'estrato_max')
    def _onchange_estratos(self):
        if self.estrato_min and self.estrato_max and int(self.estrato_min) > int(self.estrato_max):
            self.estrato_max = self.estrato_min

    def action_duplicate_request(self):
        """Crea una nueva solicitud en borrador con los mismos filtros."""
        self.ensure_one()
        new_record = self.copy({
            'name': _('Nueva Solicitud'),
            'state': 'draft',
            'error_type': False,
            'error_msg': False,
            'lead_ids': [(5, 0, 0)],
        })
        return {
            'name': _('Minado de Leads'),
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead.request',
            'view_mode': 'form',
            'res_id': new_record.id,
            'target': 'current',
        }

    def action_export_csv(self):
        """Exporta los leads generados a un archivo CSV descargable."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/crm_lead_fetcher/export_csv/{self.id}',
            'target': 'self',
        }

    def action_submit(self):
        """Ejecuta la extracción de prospectos."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Solo se pueden procesar solicitudes en estado Borrador.'))

        source_handler = self.env['lead.source.registry'].get_source(self.source_key)
        if not source_handler:
            raise UserError(_('Fuente desconocida: %s', self.source_key))

        source_handler.validate_filters(self)

        self.env.cr.execute(
            'SELECT id FROM crm_lead_request WHERE id = %s FOR UPDATE NOWAIT',
            [self.id],
        )

        try:
            results = self._perform_request()
            created_leads = self._create_leads_from_response(results)

            if not created_leads:
                msg = _('La fuente respondió sin prospectos con los filtros especificados.')
                self.write({'state': 'error', 'error_type': 'Sin resultados', 'error_msg': msg})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Sin resultados'),
                        'message': msg,
                        'type': 'warning',
                        'sticky': False,
                    }
                }

            self.write({
                'state': 'done',
                'error_type': False,
                'error_msg': False,
            })

            # Recarga el formulario manteniendo los datos
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'crm.lead.request',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'current',
            }

        except Exception as err:
            _logger.exception('Error ejecutando solicitud de leads %s: %s', self.id, err)
            error_type = type(err).__name__
            error_msg = str(err)
            self.write({'state': 'error', 'error_type': error_type, 'error_msg': error_msg})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error al generar prospectos'),
                    'message': error_msg,
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_test_connection(self):
        """Prueba la conectividad con la API seleccionada."""
        self.ensure_one()
        source = self.env['lead.source.registry'].get_source(self.source_key)
        if not source:
            raise UserError(_('Fuente no encontrada: %s', self.source_key))

        try:
            ok, msg = source.test_connection()
            notification_type = 'success' if ok else 'danger'
            title = _('Conexión Exitosa') if ok else _('Fallo de Conexión')
        except Exception as e:
            ok = False
            msg = str(e)
            notification_type = 'danger'
            title = _('Error de Conexión')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': msg,
                'type': notification_type,
                'sticky': not ok,
            }
        }

    def _perform_request(self):
        self.ensure_one()
        source = self.env['lead.source.registry'].get_source(self.source_key)
        filters = source.build_filters(self)
        results = source.search(filters, self.lead_number)
        results = source.post_filter(results, self)
        return results

    def _create_leads_from_response(self, records):
        self.ensure_one()
        Lead = self.env['crm.lead']
        source = self.env['lead.source.registry'].get_source(self.source_key)
        registry = self.env['lead.source.registry']
        Tag = self.env['crm.tag'].sudo()

        all_tag_names = set()
        for r in records:
            for tag_name in source.get_automatic_tag_names(r):
                if tag_name:
                    all_tag_names.add(tag_name)

        tag_id_by_name = {}
        if all_tag_names:
            existing_tags = Tag.search([('name', 'in', list(all_tag_names))])
            for tag in existing_tags:
                tag_id_by_name[tag.name] = tag.id
            missing_names = all_tag_names - set(tag_id_by_name.keys())
            if missing_names:
                created = Tag.create([{'name': name} for name in missing_names])
                for tag in created:
                    tag_id_by_name[tag.name] = tag.id

        base_tag_ids = set(self.tag_ids.ids)

        candidate_phones = set()
        candidate_names = set()
        for r in records:
            phone = (r.get('Telefono') or r.get('phone') or '').strip()
            name = (r.get('Nombre') or r.get('Razon_social') or r.get('name') or '').strip()
            if phone:
                candidate_phones.add(phone)
            if name:
                candidate_names.add(name)

        existing_phones = set()
        if candidate_phones:
            existing_phones = set(
                Lead.search([('phone', 'in', list(candidate_phones))]).mapped('phone')
            )

        existing_names = set()
        if candidate_names:
            existing_names = set(
                Lead.search([('name', 'in', list(candidate_names))]).mapped('name')
            )

        seen_fingerprints = set()
        created_leads = self.env['crm.lead']
        lead_vals_list = []

        for record in records:
            auto_names = source.get_automatic_tag_names(record)
            auto_tag_ids = {tag_id_by_name[n] for n in auto_names if n in tag_id_by_name}
            final_tag_ids = list(base_tag_ids | auto_tag_ids)

            vals = source.record_to_lead_vals(
                record=record,
                lead_type=self.lead_type,
                team_id=self.team_id.id,
                user_id=self.user_id.id,
                tag_ids=final_tag_ids,
                request_id=self.id,
            )

            if not vals:
                continue

            name = (vals.get('name') or '').strip()
            phone = (vals.get('phone') or '').strip()
            city = (vals.get('city') or '').strip()

            if phone and phone in existing_phones:
                continue
            if name and name in existing_names:
                continue

            fp = registry._normalize_dedup_key(name=name, city=city, phone=phone)
            if fp in seen_fingerprints:
                continue
            seen_fingerprints.add(fp)

            if phone:
                existing_phones.add(phone)
            if name:
                existing_names.add(name)

            lead_vals_list.append(vals)

            if len(lead_vals_list) >= self.lead_number:
                break

        if lead_vals_list:
            created_leads = Lead.create(lead_vals_list)

        return created_leads
