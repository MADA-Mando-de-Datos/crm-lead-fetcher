from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .lead_source import ESTRATO_LABELS

MAX_LEAD = 200


class CrmLeadRequest(models.Model):
    _name = 'crm.lead.request'
    _description = 'Solicitud de Minado de Leads (multi-fuente)'
    _order = 'id desc'

    def _default_lead_type(self):
        if self.env.user.has_group('crm.group_use_lead'):
            return 'lead'
        return 'opportunity'

    def _default_user_id(self):
        return self.env.user

    def _default_entidades(self):
        slp = self.env.ref('crm_lead_fetcher.entidad_24', raise_if_not_found=False)
        return slp or self.env['crm.denue.entidad']

    @api.model
    def _get_source_selection(self):
        try:
            sel = self.env['lead.source.registry'].list_sources()
            if sel:
                return sel
        except Exception:
            pass
        return [('denue', 'DENUE (INEGI)')]

    name = fields.Char(string='Número de solicitud', required=True, readonly=True,
                       default=lambda self: _('Nueva'), copy=False)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('error', 'Error'),
        ('done', 'Completado')
    ], string='Estado', required=True, default='draft')
    error_type = fields.Selection([
        ('no_result', 'Sin resultados'),
        ('connection', 'Error de conexión'),
    ], string='Tipo de error', copy=False, readonly=True)
    error_msg = fields.Text(string='Detalles del error', readonly=True, copy=False)

    source_key = fields.Selection(selection='_get_source_selection', string='Fuente de datos',
                                  required=True, default='denue', help='Origen de datos para minar leads')

    # --- Campos comunes ---
    lead_number = fields.Integer(string='Número de leads a generar', required=True, default=20)
    lead_type = fields.Selection([
        ('lead', 'Leads (Clientes potenciales)'),
        ('opportunity', 'Oportunidades')
    ], string='Tipo', required=True, default=_default_lead_type)
    team_id = fields.Many2one('crm.team', string='Equipo de ventas', ondelete='set null')
    user_id = fields.Many2one('res.users', string='Vendedor asignado', default=_default_user_id)
    tag_ids = fields.Many2many('crm.tag', string='Etiquetas')
    lead_ids = fields.One2many('crm.lead', 'lead_request_id', string='Detalle de leads')
    lead_count = fields.Integer(compute='_compute_lead_count', string='Leads generados')

    # --- Campos DENUE ---
    entidad_ids = fields.Many2many('crm.denue.entidad', string='Entidades federativas',
                                   default=_default_entidades,
                                   help='Estados donde buscar (códigos INEGI)')
    sector_ids = fields.Many2many('crm.denue.sector', string='Sectores SCIAN',
                                  help='Filtro por sectores económicos')
    estrato_min = fields.Integer(string='Estrato mínimo', default=2)
    estrato_max = fields.Integer(string='Estrato máximo', default=7)
    estrato_min_label = fields.Char(compute='_compute_estrato_labels', string='Rango del estrato mínimo')
    estrato_max_label = fields.Char(compute='_compute_estrato_labels', string='Rango del estrato máximo')
    municipio = fields.Char(string='Municipio / Localidad')
    actividad = fields.Char(string='Actividad / Palabra clave')
    nombre_busqueda = fields.Char(string='Nombre del establecimiento')
    latitud = fields.Float(string='Latitud', digits=(10, 7))
    longitud = fields.Float(string='Longitud', digits=(10, 7))
    distancia_metros = fields.Float(string='Radio DENUE (metros)', default=5000)
    search_type = fields.Selection([
        ('by_state', 'Todo el estado (por sectores)'),
        ('by_activity_state', 'Por actividad / palabra clave'),
        ('by_name_state', 'Por nombre del establecimiento'),
        ('by_geo', 'Geográfica (actividad + radio)'),
    ], string='Tipo de búsqueda DENUE', required=True, default='by_state')

    # --- Campos YELP ---
    yelp_term = fields.Char(string='Término de búsqueda Yelp',
                            help='Palabra clave (ej: "restaurante italiano", "plomería")')
    yelp_location = fields.Char(string='Ubicación',
                                help='Ciudad o dirección (ej: "CDMX", "Monterrey, Nuevo León")')
    yelp_categories = fields.Many2many('crm.yelp.category', string='Categorías Yelp',
                                       help='Categorías de negocio en Yelp')
    yelp_radius = fields.Integer(string='Radio Yelp (metros)',
                                 help='Radio de búsqueda en metros (máximo 40,000)')
    yelp_price = fields.Selection([
        ('1', '$ (Económico)'), ('2', '$$ (Moderado)'),
        ('3', '$$$ (Caro)'), ('4', '$$$$ (Muy caro)')
    ], string='Nivel de precio')
    yelp_sort_by = fields.Selection([
        ('best_match', 'Mejor coincidencia'),
        ('rating', 'Mejor calificación'),
        ('review_count', 'Más reseñas'),
        ('distance', 'Más cercano'),
    ], string='Ordenar por', default='best_match')
    yelp_min_rating = fields.Float(string='Rating mínimo', default=0,
                                   help='Filtrar negocios con rating mínimo (0 = sin filtro)')
    yelp_min_reviews = fields.Integer(string='Reseñas mínimas', default=0,
                                      help='Filtrar negocios con al menos N reseñas (0 = sin filtro)')
    yelp_open_now = fields.Boolean(string='Solo abiertos ahora (Yelp)',
                                   help='Filtrar negocios que están abiertos en este momento')
    yelp_transactions = fields.Selection([
        ('delivery', 'Con entrega a domicilio'),
        ('pickup', 'Con recogida en tienda'),
        ('restaurant_reservation', 'Con reservación'),
    ], string='Servicios disponibles')
    yelp_attributes = fields.Selection([
        ('hot_and_new', 'Nuevos y populares'),
        ('deals', 'Con ofertas'),
        ('reservation', 'Con reservación'),
        ('request_a_quote', 'Cotización bajo solicitud'),
        ('cashback', 'Devolución de dinero'),
    ], string='Atributos especiales')
    yelp_latitude = fields.Float(string='Latitud (para orden por distancia)', digits=(10, 7),
                                 help='Usar esta latitud al ordenar por distancia')
    yelp_longitude = fields.Float(string='Longitud (para orden por distancia)', digits=(10, 7),
                                  help='Usar esta longitud al ordenar por distancia')

    # --- Campos GOOGLE PLACES ---
    google_query = fields.Char(string='Término de búsqueda Google',
                               help='Palabra clave o giro (ej: "despacho contable", "restaurantes", "dentista")')
    google_location = fields.Char(string='Ubicación / Ciudad',
                                  help='Ciudad o dirección (ej: "San Luis Potosí, SLP", "Guadalajara")')
    google_place_type_ids = fields.Many2many('crm.google.place.type', string='Tipo de establecimiento',
                                             help='Giro comercial según Google Places')
    google_radius = fields.Integer(string='Radio Google (metros)', default=5000,
                                   help='Radio de búsqueda en metros (máximo 50,000)')
    google_min_price = fields.Selection([
        ('0', 'Gratuito'), ('1', '$ (Económico)'), ('2', '$$ (Moderado)'),
        ('3', '$$$ (Caro)'), ('4', '$$$$ (Muy caro)')
    ], string='Precio mínimo')
    google_max_price = fields.Selection([
        ('0', 'Gratuito'), ('1', '$ (Económico)'), ('2', '$$ (Moderado)'),
        ('3', '$$$ (Caro)'), ('4', '$$$$ (Muy caro)')
    ], string='Precio máximo')
    google_min_rating = fields.Float(string='Rating mínimo Google', default=0,
                                     help='Filtrar lugares con calificación mínima (0 = sin filtro)')
    google_min_reviews = fields.Integer(string='Reseñas mínimas Google', default=0,
                                        help='Filtrar lugares con al menos N opiniones (0 = sin filtro)')
    google_open_now = fields.Boolean(string='Solo abiertos ahora (Google)',
                                     help='Filtrar lugares abiertos en este momento')

    @api.depends('lead_ids')
    def _compute_lead_count(self):
        leads_data = self.env['crm.lead']._read_group(
            [('lead_request_id', 'in', self.ids)],
            ['lead_request_id'], ['__count'],
        )
        mapped = {request.id: count for request, count in leads_data}
        for request in self:
            request.lead_count = mapped.get(request.id, 0)

    @api.depends('estrato_min', 'estrato_max')
    def _compute_estrato_labels(self):
        for request in self:
            request.estrato_min_label = ESTRATO_LABELS.get(request.estrato_min, '')
            request.estrato_max_label = ESTRATO_LABELS.get(request.estrato_max, '')

    @api.onchange('lead_number')
    def _onchange_lead_number(self):
        if self.lead_number <= 0:
            self.lead_number = 1
        elif self.lead_number > MAX_LEAD:
            self.lead_number = MAX_LEAD

    @api.onchange('estrato_min')
    def _onchange_estrato_min(self):
        if self.estrato_min <= 0:
            self.estrato_min = 1
        elif self.estrato_min > self.estrato_max:
            self.estrato_min = self.estrato_max

    @api.onchange('estrato_max')
    def _onchange_estrato_max(self):
        if self.estrato_max < self.estrato_min:
            self.estrato_max = self.estrato_min
        elif self.estrato_max > 7:
            self.estrato_max = 7

    def action_draft(self):
        self.ensure_one()
        leads = self.env['crm.lead'].search([('lead_request_id', '=', self.id)])
        n = len(leads)
        if leads:
            leads.unlink()
        self.write({'name': _('Nueva'), 'state': 'draft', 'error_type': False, 'error_msg': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Listo para nueva búsqueda'),
                'message': _('Se eliminaron los %d lead(s) previos. Puede comenzar una nueva búsqueda.', n),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_delete_with_leads(self):
        self.ensure_one()
        leads = self.env['crm.lead'].search([('lead_request_id', '=', self.id)])
        n = len(leads)
        if leads:
            leads.unlink()
        request_name = self.name
        self.unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Eliminado'),
                'message': _('Se eliminó la solicitud %s y %d lead(s) asociado(s).', request_name, n),
                'type': 'warning',
                'sticky': False,
            },
        }

    def action_export_csv(self):
        """Exporta los leads de esta solicitud a un archivo CSV descargable."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/crm_lead_fetcher/export_csv?request_id=%s' % self.id,
            'target': 'self',
        }

    def action_submit(self):
        self.ensure_one()
        self._check_filters()

        if self.name == _('Nueva'):
            self.name = self.env['ir.sequence'].next_by_code('crm.lead.request') or _('Nueva')

        try:
            records, stats = self._perform_request()
        except Exception as err:
            error_str = str(err)
            is_connection = any(kw in error_str.lower() for kw in (
                'connection', 'badstatusline', '000', 'timeout', 'connectionerror',
                'connection aborted', 'remote disconnected', 'connection refused',
                'bearer', '401', '403'))
            if is_connection:
                friendly = _(
                    'El servicio de datos no responde en este momento '
                    '(error de conexión o timeout). Esto es temporal.\n\n'
                    'Puede reintentar usando el botón "Reintentar", '
                    'o espere unos minutos y vuelva a intentarlo.')
                self.write({'state': 'error', 'error_type': 'connection', 'error_msg': friendly})
                raise UserError(_('El servicio de datos no responde. Intente de nuevo en unos segundos.'))
            else:
                self.write({'state': 'error', 'error_msg': error_str})
                raise UserError(_('No se pudo ejecutar la solicitud: %s', err))

        if records:
            created = self._create_leads_from_response(records)
            self.write({'state': 'done'})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Leads generados'),
                    'message': _('Se crearon %d leads nuevos.', created),
                    'type': 'success',
                    'sticky': False,
                },
            }

        detalle = _(
            'No se encontraron negocios que coincidan con los filtros.\n\n'
            'La fuente devolvió %(crudos)d registro(s). Descartados: '
            '%(filtrados)d por filtros locales.',
            crudos=stats.get('crudos', 0),
            filtrados=stats.get('filtrados', 0))
        self.write({'state': 'error', 'error_type': 'no_result', 'error_msg': detalle})
        if self.env.context.get('is_modal'):
            return {
                'name': _('Generar Leads'),
                'res_model': 'crm.lead.request',
                'views': [[False, 'form']],
                'target': 'new',
                'type': 'ir.actions.act_window',
                'res_id': self.id,
                'context': dict(self.env.context, edit=True),
            }
        return False

    def _check_filters(self):
        """Valida filtros delegando al objeto de la fuente seleccionada."""
        self.ensure_one()
        source = self.env['lead.source.registry'].get_source(self.source_key)
        source.validate_filters(self)

    def _build_source_filters(self):
        """Construye los filtros delegando al objeto de la fuente seleccionada."""
        self.ensure_one()
        source = self.env['lead.source.registry'].get_source(self.source_key)
        return source.build_filters(self)

    def _perform_request(self):
        """Despacha la búsqueda a la fuente seleccionada vía el registry."""
        self.ensure_one()
        source = self.env['lead.source.registry'].get_source(self.source_key)
        scan_cap = source.get_scan_cap()
        raw_records = source.search(self._build_source_filters(), scan_cap)

        # Post-filtrado delegado al modelo de la fuente
        filtered = source.post_filter(raw_records, self)
        stats = {'crudos': len(raw_records), 'filtrados': len(raw_records) - len(filtered)}
        return filtered[:self.lead_number] if filtered else [], stats

    def _create_leads_from_response(self, records):
        """Crea leads deduplicando por external_id y etiquetas automáticas de la fuente.

        Además de deduplicar por external_id (dentro de la misma fuente), reconcilia
        contra leads ya existentes de otras fuentes por nombre+ciudad/teléfono
        para evitar duplicados del mismo negocio encontrado en varias fuentes.
        """
        self.ensure_one()
        source = self.env['lead.source.registry'].get_source(self.source_key)
        manual_tag_ids = self.tag_ids.ids

        candidate_map = {}
        for record in records:
            ext_id = source.get_external_id(record)
            if ext_id and ext_id not in candidate_map:
                candidate_map[ext_id] = record

        if not candidate_map:
            return 0

        existing = set(self.env['crm.lead'].search([
            ('external_id', 'in', list(candidate_map.keys()))
        ]).mapped('external_id'))

        registry = self.env['lead.source.registry']
        Lead = self.env['crm.lead']
        fingerprint_seen = set()

        lead_vals_list = []
        for ext_id, record in candidate_map.items():
            if ext_id in existing:
                continue
            existing.add(ext_id)

            auto_tag_ids = source.get_automatic_tag_ids(record)
            all_tag_ids = list(set(manual_tag_ids + auto_tag_ids))

            vals = source.record_to_lead_vals(
                record, self.lead_type, self.team_id.id,
                self.user_id.id, all_tag_ids, self.id)
            vals['external_id'] = ext_id

            # Deduplicación entre fuentes por huella (nombre+ciudad o teléfono)
            name = (vals.get('name') or vals.get('partner_name') or '').strip()
            phone = (vals.get('phone') or '').strip()
            city = (vals.get('city') or '').strip()
            if name:
                fp = registry._normalize_dedup_key(name=name, city=city, phone=phone)
                if fp in fingerprint_seen:
                    continue
                duplicate = registry.find_existing_by_fingerprint(vals)
                if duplicate:
                    fingerprint_seen.add(fp)
                    continue
                fingerprint_seen.add(fp)

            lead_vals_list.append(vals)

        if lead_vals_list:
            Lead.create(lead_vals_list)
        return len(lead_vals_list)
