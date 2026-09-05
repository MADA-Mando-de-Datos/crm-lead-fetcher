from odoo import _, api, models
from odoo.exceptions import UserError


class LeadSourceGoogle(models.AbstractModel):
    """Implementación Google Places API de lead source."""

    _name = 'lead.source.google'
    _inherit = 'lead.source'
    _description = 'Google Places API - Directorio global de comercios y servicios'

    @api.model
    def _get_api(self):
        return self.env['google.places.api']

    @api.model
    def validate_filters(self, wizard):
        """Valida filtros específicos para Google Places."""
        if not (wizard.google_query or '').strip() and not wizard.google_place_type_ids:
            raise UserError(_('Capture un término de búsqueda o seleccione un tipo de establecimiento para Google Places.'))
        if not (wizard.google_location or '').strip():
            raise UserError(_('Capture una ubicación o ciudad para la búsqueda de Google Places.'))

    @api.model
    def build_filters(self, wizard):
        return {
            'query': (wizard.google_query or '').strip(),
            'location': (wizard.google_location or '').strip(),
            'place_types': [t.code for t in wizard.google_place_type_ids],
        }

    @api.model
    def search(self, filters, max_records):
        api = self._get_api()
        records, total = api.paginate(
            query=filters.get('query', ''),
            location=filters.get('location') or api._location(),
            place_types=filters.get('place_types', []),
            max_results=max_records,
            fetch_details=True,
        )
        return records

    @api.model
    def test_connection(self, config=None):
        api_key = ((config.google_places_api_key if config and hasattr(config, 'google_places_api_key') else None) or self._get_api()._api_key() or '').strip()
        if not api_key:
            return False, _('Configure la API Key de Google Places en Ajustes > CRM > Minado de Leads.')
        url = 'https://maps.googleapis.com/maps/api/place/textsearch/json'
        params = {'query': 'restaurantes en Mexico', 'key': api_key, 'language': 'es'}
        import requests
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            status = data.get('status')
            if status == 'OK':
                results = data.get('results', [])
                return True, _('Conexión exitosa con Google Places. Se obtuvieron %d resultado(s) de prueba.', len(results))
            elif status == 'REQUEST_DENIED':
                err_msg = data.get('error_message') or _('Clave inválida o API Places no habilitada.')
                return False, _('Google Places rechazó la petición: %s', err_msg)
            elif status == 'OVER_QUERY_LIMIT':
                return False, _('Límite de cuota excedido en Google Cloud Console.')
            else:
                return False, _('Respuesta de Google: %s', data.get('error_message', status))
        except Exception as e:
            return False, _('Error de conexión con Google Places: %s', e)

    @api.model
    def get_available_filters(self):
        return [
            {'field': 'query', 'label': 'Término de búsqueda', 'type': 'char',
             'help': 'Palabra clave o giro (ej: "consultoría contable", "restaurante", "dentista")'},
            {'field': 'location', 'label': 'Ubicación', 'type': 'char', 'required': True,
             'help': 'Ciudad, zona o estado (ej: "San Luis Potosí, SLP", "Guadalajara")'},
            {'field': 'place_types', 'label': 'Tipo de establecimiento', 'type': 'many2many',
             'model': 'crm.google.place.type',
             'help': 'Filtro por tipo de negocio según Google Places'},
        ]

    @api.model
    def get_external_id(self, record):
        return str(record.get('place_id') or record.get('id') or '').strip()

    @api.model
    def get_automatic_tag_names(self, record):
        """Genera nombres de etiquetas basadas en los tipos de Google Places."""
        types = record.get('types', [])
        return [
            f"Google: {t.replace('_', ' ')}"
            for t in types[:3]
            if t not in ('point_of_interest', 'establishment')
        ]

    @api.model
    def record_to_lead_vals(self, record, lead_type, team_id, user_id, tag_ids, request_id):
        """Convierte un registro de Google Places a vals de lead CRM."""
        place_id = self.get_external_id(record)
        name = record.get('name', 'Sin nombre')
        formatted_address = record.get('formatted_address', '')
        phone = record.get('formatted_phone_number') or record.get('international_phone_number') or False
        mobile = record.get('international_phone_number') or False
        website = record.get('website') or False
        maps_url = record.get('url') or (f"https://maps.google.com/?q=place_id:{place_id}" if place_id else False)
        rating = record.get('rating')
        reviews = record.get('user_ratings_total') or 0
        price_level = record.get('price_level')
        business_status = record.get('business_status', 'OPERATIONAL')
        types = record.get('types', [])
        geometry = record.get('geometry', {}) or {}
        location = geometry.get('location', {}) or {}
        latitude = location.get('lat')
        longitude = location.get('lng')

        # Desglose de componentes de dirección
        components = record.get('address_components', [])
        street = formatted_address
        city = False
        state = False
        zip_code = False
        country_code = 'MX'

        if components:
            route = ''
            street_number = ''
            for comp in components:
                c_types = comp.get('types', [])
                if 'route' in c_types:
                    route = comp.get('long_name', '')
                elif 'street_number' in c_types:
                    street_number = comp.get('long_name', '')
                elif 'locality' in c_types or 'sublocality' in c_types:
                    if not city:
                        city = comp.get('long_name', '')
                elif 'administrative_area_level_1' in c_types:
                    state = comp.get('long_name', '')
                elif 'postal_code' in c_types:
                    zip_code = comp.get('long_name', '')
                elif 'country' in c_types:
                    country_code = comp.get('short_name', 'MX')

            if route:
                street = f"{route} {street_number}".strip()

        price_str = ('$' * price_level) if isinstance(price_level, int) and price_level > 0 else 'N/A'
        status_str = 'Operativo' if business_status == 'OPERATIONAL' else business_status

        description = (
            'Fuente: Google Places\n'
            'Giro / Tipos: %s\n'
            'Calificación: %s estrellas (%s opiniones)\n'
            'Nivel de Precio: %s\n'
            'Estado del Negocio: %s\n'
            'Google Maps: %s'
        ) % (
            ', '.join([t.replace('_', ' ').capitalize() for t in types if t not in ('point_of_interest', 'establishment')][:4]) or 'General',
            rating or 'N/A',
            reviews,
            price_str,
            status_str,
            maps_url or 'N/A',
        )

        vals = {
            'name': name,
            'type': lead_type,
            'street': street or formatted_address or False,
            'city': city or False,
            'state': state or False,
            'zip': zip_code or False,
            'country_id': self.env.ref('base.mx').id if country_code == 'MX' else False,
            'email_from': False,
            'phone': phone,
            'mobile': mobile,
            'website': website or maps_url,
            'external_id': place_id,
            'source_rating': rating,
            'source_reviews': reviews,
            'source_price_level': str(price_level) if isinstance(price_level, int) else False,
            'latitude': latitude,
            'longitude': longitude,
            'description': description,
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
        return records

    @api.model
    def get_scan_cap(self):
        val = int(self.env['ir.config_parameter'].sudo()
                  .get_param('crm_lead_fetcher.google_max_results', '60'))
        return min(val, self._get_api().MAX_RESULTS_LIMIT)
