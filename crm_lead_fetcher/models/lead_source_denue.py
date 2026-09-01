from odoo import _, api, models
from odoo.exceptions import UserError
from .lead_source import ESTRATO_LABELS

MAX_DENUE_GEO_DISTANCE = 5000


class LeadSourceDenue(models.AbstractModel):
    """Implementación DENUE (INEGI) de lead source."""

    _name = 'lead.source.denue'
    _inherit = 'lead.source'
    _description = 'DENUE (INEGI) - Directorio Nacional de Unidades Económicas'

    @api.model
    def _get_api(self):
        return self.env['denue.api']

    @api.model
    def _get_denue_token(self):
        return (self.env['ir.config_parameter'].sudo()
                .get_param('crm_lead_fetcher.denue_token', '')).strip()

    @api.model
    def _get_max_records(self):
        return int(self.env['ir.config_parameter'].sudo()
                   .get_param('crm_lead_fetcher.denue_max_records', '30000'))

    @api.model
    def validate_filters(self, wizard):
        """Valida las reglas específicas de búsqueda para DENUE (INEGI)."""
        if not wizard.entidad_ids:
            raise UserError(_('Seleccione al menos una entidad federativa.'))
        st = wizard.search_type
        if st == 'by_state' and not wizard.sector_ids:
            raise UserError(_('En búsqueda "Todo el estado" debe seleccionar al menos un sector SCIAN.'))
        if st == 'by_activity_state' and not (wizard.actividad or '').strip():
            raise UserError(_('Capture la actividad o palabra clave a buscar.'))
        if st == 'by_name_state' and not (wizard.nombre_busqueda or '').strip():
            raise UserError(_('Capture el nombre del establecimiento a buscar.'))
        if st == 'by_geo':
            lat = wizard.latitud
            lon = wizard.longitud
            if lat is None or lon is None:
                raise UserError(_('Capture latitud y longitud válidas para la búsqueda geográfica.'))
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                raise UserError(_('Latitud y longitud deben ser valores numéricos.'))
            if not (-90 <= lat_f <= 90) or not (-180 <= lon_f <= 180):
                raise UserError(_('Latitud debe estar entre -90 y 90, y longitud entre -180 y 180.'))
            if not (wizard.distancia_metros or 0) > 0:
                raise UserError(_('El radio de búsqueda debe ser mayor a 0 metros.'))
            if wizard.distancia_metros > MAX_DENUE_GEO_DISTANCE:
                raise UserError(_(
                    'El radio máximo permitido por DENUE es de %s metros.',
                    '{:,}'.format(MAX_DENUE_GEO_DISTANCE)))

    @api.model
    def build_filters(self, wizard):
        """Construye los parámetros para el cliente DENUE API."""
        return {
            'entidad_ids': [e.code for e in wizard.entidad_ids],
            'search_type': wizard.search_type,
            'sectores': [s.code for s in wizard.sector_ids],
            'actividad': (wizard.actividad or '').strip(),
            'nombre': (wizard.nombre_busqueda or '').strip(),
            'lat': wizard.latitud,
            'lon': wizard.longitud,
            'radio_km': (wizard.distancia_metros or 5000) / 1000.0,
            'municipio': (wizard.municipio or '').strip(),
            'estrato_min': wizard.estrato_min or None,
            'estrato_max': wizard.estrato_max or None,
        }

    @api.model
    def search(self, filters, max_records):
        entidad_ids = filters.get('entidad_ids') or []
        if not entidad_ids:
            raise ValueError(_('Debe seleccionar al menos una entidad'))

        search_type = filters.get('search_type', 'by_state')
        all_matches = []

        for entidad in entidad_ids:
            for gen in self._generators_for(search_type, filters, entidad, max_records):
                for record in gen:
                    all_matches.append(record)
                    if len(all_matches) >= max_records:
                        return all_matches

        return all_matches[:max_records]

    @api.model
    def _generators_for(self, search_type, filters, entidad, max_records):
        api = self._get_api()
        if search_type == 'by_state':
            sectores = filters.get('sectores') or []
            if sectores:
                return [
                    api.search_by_area_act(entidad, code, max_records)
                    for code in sectores
                ]
            return [api.search_by_state(entidad, max_records)]
        if search_type == 'by_activity_state':
            actividad = filters.get('actividad', '')
            if not actividad:
                return []
            return [api.search_by_activity_and_state(actividad, entidad, max_records)]
        if search_type == 'by_name_state':
            nombre = filters.get('nombre', '')
            if not nombre:
                return []
            return [api.search_by_name_and_state(nombre, entidad, max_records)]
        return []

    @api.model
    def test_connection(self, config=None):
        token = ((config.denue_token if config and hasattr(config, 'denue_token') else None) or self._get_denue_token() or '').strip()
        entidad = ((config.denue_entidad if config and hasattr(config, 'denue_entidad') else None) or '24').strip()
        if not token:
            return False, _('Configure el Token de DENUE primero.')
        url = f'https://www.inegi.org.mx/app/api/denue/v1/consulta/BuscarEntidad/todos/{entidad}/1/1/{token}'
        import requests
        try:
            resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0 (crm-lead-mining)'})
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                return True, _('Conexión exitosa. DENUE respondió con %d registro(s) de prueba.', len(data))
            return True, _('Conexión OK (el API respondió pero no devolvió datos para esta entidad).')
        except Exception as e:
            return False, _('Error de conexión con DENUE: %s', e)

    @api.model
    def get_available_filters(self):
        return [
            {'field': 'entidad_ids', 'label': 'Entidades', 'type': 'many2many',
              'model': 'crm.denue.entidad', 'required': True,
              'help': 'Estados a buscar (códigos INEGI)'},
            {'field': 'search_type', 'label': 'Tipo de búsqueda', 'type': 'selection',
              'selection': [
                  ('by_state', 'Todo el estado'),
                  ('by_activity_state', 'Por actividad + estado'),
                  ('by_name_state', 'Por nombre + estado'),
                  ('by_geo', 'Por geolocalización (radio km)'),
              ], 'required': True, 'default': 'by_state'},
            {'field': 'actividad', 'label': 'Actividad / Palabra clave', 'type': 'char'},
            {'field': 'nombre_busqueda', 'label': 'Nombre del establecimiento', 'type': 'char'},
            {'field': 'municipio', 'label': 'Municipio / Ciudad', 'type': 'char',
              'help': 'Filtrar por municipio (búsqueda en cliente)'},
            {'field': 'sector_ids', 'label': 'Sectores SCIAN', 'type': 'many2many',
              'model': 'crm.denue.sector'},
            {'field': 'estrato_min', 'label': 'Estrato mínimo', 'type': 'selection',
              'selection': [(i, ESTRATO_LABELS[i]) for i in range(1, 8)]},
            {'field': 'estrato_max', 'label': 'Estrato máximo', 'type': 'selection',
              'selection': [(i, ESTRATO_LABELS[i]) for i in range(1, 8)]},
            {'field': 'latitud', 'label': 'Latitud', 'type': 'float'},
            {'field': 'longitud', 'label': 'Longitud', 'type': 'float'},
            {'field': 'distancia_metros', 'label': 'Radio (metros)', 'type': 'float', 'default': 5000},
        ]

    @api.model
    def get_external_id(self, record):
        return str(record.get('Id') or '').strip()

    @api.model
    def get_automatic_tag_ids(self, record):
        """Devuelve IDs de etiquetas de sector SCIAN para un registro DENUE."""
        code = str(record.get('SUBSECTOR_ACTIVIDAD_ID') or
                   record.get('SECTOR_ACTIVIDAD_ID') or '').strip()
        if not code:
            return []
        Sector = self.env['crm.denue.sector']
        Tag = self.env['crm.tag'].sudo()
        sector = Sector.search([('code', '=', code)], limit=1)
        if not sector and len(code) >= 3:
            sector = Sector.search([('code', '=', code[:2])], limit=1)
        if not sector:
            return []
        tag_name = f"{sector.code} {sector.name}"
        tag = Tag.search([('name', '=', tag_name)], limit=1)
        if not tag:
            tag = Tag.create({'name': tag_name})
        return tag.ids

    @api.model
    def record_to_lead_vals(self, record, lead_type, team_id, user_id, tag_ids, request_id):
        return self.env['denue.lead.helpers'].lead_vals(
            record, lead_type, team_id, user_id, tag_ids, request_id)

    @api.model
    def post_filter(self, records, wizard):
        """Aplica filtros client-side de DENUE: estrato, municipio.

        En búsquedas geográficas reordena los resultados por cercanía al
        punto solicitado (usando Latitud/Longitud del registro).
        """
        filtered = list(records)
        municipio = getattr(wizard, 'municipio', None)
        if municipio and isinstance(municipio, str) and municipio.strip():
            m = municipio.strip().upper()
            helper = self.env['denue.lead.helpers']
            filtered = [
                r for r in filtered
                if (r.get('mun') or '').strip().upper() == m
                or (r.get('loc') or '').strip().upper() == m
                or m in helper.ubicacion_text(r).upper()
            ]
        estrato_min = getattr(wizard, 'estrato_min', None)
        estrato_max = getattr(wizard, 'estrato_max', None)
        if estrato_min:
            emin = int(estrato_min)
            filtered = [r for r in filtered if int(r.get('estrato') or 0) >= emin]
        if estrato_max:
            emax = int(estrato_max)
            filtered = [r for r in filtered if int(r.get('estrato') or 0) <= emax]

        return filtered

    @api.model
    def get_scan_cap(self):
        return self._get_max_records()
