from markupsafe import Markup, escape
from odoo import _, api, models
from odoo.exceptions import UserError


class LeadSourceYelp(models.AbstractModel):
    """Implementación Yelp Fusion API de lead source."""

    _name = 'lead.source.yelp'
    _inherit = 'lead.source'
    _description = 'Yelp Fusion API - Directorio de negocios con reseñas'

    @api.model
    def _get_api(self):
        return self.env['yelp.api']

    @api.model
    def validate_filters(self, wizard):
        """Valida filtros específicos para Yelp."""
        if not (wizard.yelp_location or '').strip():
            raise UserError(_('Capture una ubicación para la búsqueda Yelp.'))

    @api.model
    def build_filters(self, wizard):
        """Construye parámetros para el cliente Yelp API."""
        return {
            'term': (wizard.yelp_term or '').strip(),
            'location': (wizard.yelp_location or '').strip(),
            'categories': [c.alias for c in wizard.yelp_categories],
        }

    @api.model
    def search(self, filters, max_records):
        api = self._get_api()
        location = filters.get('location') or api._location()
        params = {
            'term': filters.get('term', ''),
            'location': location,
            'categories': filters.get('categories', []),
        }
        records, total = api.paginate(
            term=params['term'],
            location=params['location'],
            categories=params['categories'],
            max_results=max_records,
        )
        return records

    @api.model
    def test_connection(self, config=None):
        api_key = ((config.yelp_api_key if config and hasattr(config, 'yelp_api_key') else None) or self._get_api()._api_key() or '').strip()
        if not api_key:
            return False, _('Configure la API Key de Yelp en Ajustes > CRM > Minado de Leads.')
        url = 'https://api.yelp.com/v3/businesses/search'
        params = {'term': 'restaurant', 'location': 'Mexico', 'limit': 1}
        headers = {'Authorization': f'Bearer {api_key}'}
        import requests
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 401:
                return False, _('API Key de Yelp inválida. Verifique su clave en https://www.yelp.com/developers/v3/manage_app')
            resp.raise_for_status()
            data = resp.json()
            total = data.get('total', 0)
            return True, _('Conexión exitosa. Yelp encontró %d negocios. Cuota restante: %s.',
                           total, resp.headers.get('RateLimit-Remaining', '?'))
        except Exception as e:
            return False, _('Error de conexión con Yelp: %s', e)

    @api.model
    def get_available_filters(self):
        return [
            {'field': 'yelp_term', 'label': 'Término de búsqueda', 'type': 'char',
             'help': 'Palabra clave para buscar (ej: "restaurante italiano", "plomería")'},
            {'field': 'yelp_location', 'label': 'Ubicación', 'type': 'char', 'required': True,
             'help': 'Ciudad o dirección (ej: "CDMX", "Monterrey, Nuevo León")'},
            {'field': 'yelp_categories', 'label': 'Categorías', 'type': 'many2many',
             'model': 'crm.yelp.category',
             'help': 'Categorías Yelp (ej: restaurants, plumbing)'},
        ]

    @api.model
    def get_external_id(self, record):
        return str(record.get('id') or '').strip()

    @api.model
    def get_automatic_tag_names(self, record):
        """Genera nombres de etiquetas a partir de las categorías de Yelp."""
        cats = record.get('categories', [])
        cat_aliases = [c.get('alias', '') for c in cats if c.get('alias')]
        return [f"Yelp: {alias}" for alias in cat_aliases[:3]]

    @api.model
    def record_to_lead_vals(self, record, lead_type, team_id, user_id, tag_ids, request_id):
        """Convierte un registro Yelp a vals de lead CRM."""
        cats = record.get('categories', [])
        cat_names = [c.get('title', '') for c in cats if c.get('title')]
        loc = record.get('location', {})
        coords = record.get('coordinates', {}) or {}
        price_int = int(str(record.get('price', '0')).replace('$', '') or '0')
        country_id = self.env.ref('base.mx').id if loc.get('country') == 'MX' else False
        state_id = self._resolve_state_id(loc.get('state'), country_id)
        ext_id = self.get_external_id(record)

        vals = {
            'name': record.get('name', 'Sin nombre'),
            'type': lead_type,
            'street': (', '.join(loc.get('display_address', []))) or False,
            'city': loc.get('city', False),
            'state_id': state_id,
            'zip': loc.get('zip_code', False),
            'country_id': country_id,
            'email_from': False,
            'phone': record.get('phone', False),
            'mobile': record.get('display_phone', False),
            'website': record.get('url', False),
            'external_id': ext_id,
            'source_rating': record.get('rating'),
            'source_reviews': record.get('review_count'),
            'yelp_price': price_int or None,
            'latitude': coords.get('latitude'),
            'longitude': coords.get('longitude'),
            'description': Markup(
                '<p><strong>Giro:</strong> %s</p>'
                '<p><strong>Reseñas:</strong> %s de 5 (%s opiniones)</p>'
                '%s'
            ) % (
                escape(', '.join(cat_names) or 'General'),
                escape(str(record.get('rating') or '0.0')),
                escape(str(record.get('review_count') or 0)),
                Markup('<p><a href="%s" target="_blank" rel="noopener noreferrer">Abrir ficha en Yelp</a></p>') % escape(record.get('url', '')) if record.get('url') else Markup(''),
            ),
        }

        if team_id:
            vals['team_id'] = team_id
        if user_id:
            vals['user_id'] = user_id
        if tag_ids:
            vals['tag_ids'] = [(6, 0, tag_ids)]
        if request_id:
            vals['lead_request_id'] = request_id

        return vals

    @api.model
    def post_filter(self, records, wizard):
        """Devuelve registros Yelp sin filtrado secundario innecesario."""
        return records

    @api.model
    def _resolve_state_id(self, state_raw, country_id=None):
        if not state_raw:
            return False
        state_str = str(state_raw).strip()
        domain = [('country_id', '=', country_id)] if country_id else []
        state_rec = self.env['res.country.state'].search(domain + [('code', '=ilike', state_str)], limit=1)
        if not state_rec:
            state_rec = self.env['res.country.state'].search(domain + [('name', 'ilike', state_str)], limit=1)
        return state_rec.id if state_rec else False

    @api.model
    def get_scan_cap(self):
        val = int(self.env['ir.config_parameter'].sudo()
                  .get_param('crm_lead_fetcher.yelp_max_results', '240'))
        return min(val, self._get_api().MAX_OFFSET)
