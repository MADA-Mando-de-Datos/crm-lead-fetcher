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
            'radius': wizard.yelp_radius or None,
            'price': wizard.yelp_price or None,
            'sort_by': wizard.yelp_sort_by or 'best_match',
            'open_now': wizard.yelp_open_now,
            'transactions': wizard.yelp_transactions,
            'attributes': wizard.yelp_attributes,
            'latitude': wizard.yelp_latitude or None,
            'longitude': wizard.yelp_longitude or None,
        }

    @api.model
    def search(self, filters, max_records):
        api = self._get_api()
        location = filters.get('location') or api._location()
        latitude = filters.get('latitude')
        longitude = filters.get('longitude')
        sort_by = filters.get('sort_by', 'best_match')
        if sort_by == 'distance' and latitude and longitude:
            location = None
        params = {
            'term': filters.get('term', ''),
            'location': location,
            'categories': filters.get('categories', []),
            'radius': filters.get('radius'),
            'price': filters.get('price'),
            'sort_by': sort_by,
            'open_now': filters.get('open_now'),
            'transactions': filters.get('transactions'),
            'attributes': filters.get('attributes'),
            'latitude': latitude,
            'longitude': longitude,
        }
        records, total = api.paginate(
            term=params['term'],
            location=params['location'],
            categories=params['categories'],
            radius=params['radius'],
            price=params['price'],
            sort_by=params['sort_by'],
            max_results=max_records,
            open_now=params['open_now'],
            transactions=params['transactions'],
            attributes=params['attributes'],
            latitude=params['latitude'],
            longitude=params['longitude'],
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
            {'field': 'yelp_radius', 'label': 'Radio (metros)', 'type': 'integer',
             'help': 'Radio de búsqueda en metros (máximo 40,000)'},
            {'field': 'yelp_price', 'label': 'Nivel de precio', 'type': 'selection',
             'selection': [('1', '$ (Económico)'), ('2', '$$ (Moderado)'),
                           ('3', '$$$ (Caro)'), ('4', '$$$$ (Muy caro)')],
             'help': 'Filtrar por nivel de precio'},
            {'field': 'yelp_sort_by', 'label': 'Ordenar por', 'type': 'selection',
             'selection': [('best_match', 'Mejor coincidencia'),
                           ('rating', 'Mejor calificación'),
                           ('review_count', 'Más reseñas'),
                           ('distance', 'Más cercano')],
             'default': 'best_match'},
            {'field': 'yelp_open_now', 'label': 'Solo abiertos ahora', 'type': 'boolean'},
            {'field': 'yelp_transactions', 'label': 'Servicios disponibles', 'type': 'selection',
             'selection': [('delivery', 'Con entrega a domicilio'),
                           ('pickup', 'Con recogida en tienda'),
                           ('restaurant_reservation', 'Con reservación')]},
            {'field': 'yelp_attributes', 'label': 'Atributos especiales', 'type': 'selection',
             'selection': [('hot_and_new', 'Nuevos y populares'),
                           ('deals', 'Con ofertas'),
                           ('reservation', 'Con reservación'),
                           ('request_a_quote', 'Cotización bajo solicitud'),
                           ('cashback', 'Devolución de dinero')]},
            {'field': 'yelp_min_rating', 'label': 'Rating mínimo', 'type': 'float'},
            {'field': 'yelp_min_reviews', 'label': 'Reseñas mínimas', 'type': 'integer'},
            {'field': 'yelp_latitude', 'label': 'Latitud (orden por distancia)', 'type': 'float'},
            {'field': 'yelp_longitude', 'label': 'Longitud (orden por distancia)', 'type': 'float'},
        ]

    @api.model
    def get_external_id(self, record):
        return str(record.get('id') or '').strip()

    @api.model
    def get_automatic_tag_ids(self, record):
        """Genera y asigna etiquetas a partir de las categorías de Yelp."""
        cats = record.get('categories', [])
        cat_aliases = [c.get('alias', '') for c in cats if c.get('alias')]
        if not cat_aliases:
            return []

        Tag = self.env['crm.tag'].sudo()
        tag_ids = []
        for alias in cat_aliases[:3]:
            tag_name = f"Yelp: {alias}"
            tag = Tag.search([('name', '=', tag_name)], limit=1)
            if not tag:
                tag = Tag.create({'name': tag_name})
            tag_ids.append(tag.id)
        return tag_ids

    @api.model
    def record_to_lead_vals(self, record, lead_type, team_id, user_id, tag_ids, request_id):
        """Convierte un registro Yelp a vals de lead CRM."""
        cats = record.get('categories', [])
        cat_names = [c.get('title', '') for c in cats if c.get('title')]
        loc = record.get('location', {})
        coords = record.get('coordinates', {}) or {}
        price_int = int(str(record.get('price', '0')).replace('$', '') or '0')
        ext_id = self.get_external_id(record)

        vals = {
            'name': record.get('name', 'Sin nombre'),
            'type': lead_type,
            'street': (', '.join(loc.get('display_address', []))) or False,
            'city': loc.get('city', False),
            'state': loc.get('state', False),
            'zip': loc.get('zip_code', False),
            'country_id': self.env.ref('base.mx').id if loc.get('country') == 'MX' else False,
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
            'description': (
                'Fuente: Yelp\n'
                'Categorías: %s\n'
                'Rating: %s (%s reseñas)\n'
                'Precio: %s\n'
                'Estado: %s\n'
                'URL: %s'
            ) % (
                ', '.join(cat_names) or 'N/A',
                record.get('rating', 'N/A'),
                record.get('review_count', 0),
                '$' * price_int or 'N/A',
                'Abierto' if record.get('is_closed') is False else 'Cerrado',
                record.get('url', 'N/A'),
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
        """Filtra registros Yelp por rating mínimo y review count."""
        filtered = list(records)
        min_rating = getattr(wizard, 'yelp_min_rating', None)
        min_reviews = getattr(wizard, 'yelp_min_reviews', None)
        if min_rating:
            filtered = [r for r in filtered if (r.get('rating') or 0) >= min_rating]
        if min_reviews:
            filtered = [r for r in filtered if (r.get('review_count') or 0) >= min_reviews]
        return filtered

    @api.model
    def get_scan_cap(self):
        val = int(self.env['ir.config_parameter'].sudo()
                  .get_param('crm_lead_fetcher.yelp_max_results', '240'))
        return min(val, self._get_api().MAX_OFFSET)
