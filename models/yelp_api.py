import time

from odoo import _, api, models
from odoo.exceptions import UserError


class YelpAPI(models.AbstractModel):
    _name = 'yelp.api'
    _description = 'Cliente API Yelp Fusion'

    MAX_RETRIES = 3
    RETRY_BACKOFF = 3
    PAGE_SIZE = 50
    MAX_OFFSET = 240

    @api.model
    def _api_key(self):
        return (self.env['ir.config_parameter'].sudo()
                .get_param('crm_lead_fetcher.yelp_api_key', '')).strip()

    @api.model
    def _location(self):
        return (self.env['ir.config_parameter'].sudo()
                .get_param('crm_lead_fetcher.yelp_location', 'San Luis Potosí, México')).strip()

    @api.model
    def _max_results(self):
        val = self.env['ir.config_parameter'].sudo().get_param('crm_lead_fetcher.yelp_max_results', '240')
        return min(int(val or 240), self.MAX_OFFSET)

    @api.model
    def _q(self, text):
        from requests.utils import quote
        return quote(str(text), safe=',')

    @api.model
    def _get(self, url, params=None):
        """GET con reintentos ante fallas de red."""
        import requests
        api_key = self._api_key()
        if not api_key:
            raise UserError(_('Configure la API Key de Yelp en Ajustes > CRM > Minado de Leads.'))
        headers = {'Authorization': f'Bearer {api_key}'}
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get('Retry-After', 60))
                    time.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as err:
                last_error = err
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_BACKOFF * (attempt + 1))
                continue
        raise UserError(_('Yelp API error: %s', last_error))

    def search(self, term=None, location=None, categories=None,
               radius=None, price=None, sort_by='best_match',
               limit=50, offset=0, open_now=None, transactions=None,
               attributes=None, latitude=None, longitude=None):
        """Busca negocios en Yelp. Devuelve lista de records normalizados."""
        params = {
            'limit': min(limit, self.PAGE_SIZE),
            'offset': offset,
            'sort_by': sort_by,
            'locale': 'es_MX',
        }
        if term:
            params['term'] = term
        if location:
            params['location'] = location
        if categories:
            params['categories'] = ','.join(categories) if isinstance(categories, list) else categories
        if radius:
            params['radius'] = min(int(radius), 40000)
        if price:
            if isinstance(price, list):
                params['price'] = ','.join(str(p) for p in price)
            else:
                params['price'] = str(price)
        if open_now:
            params['open_now'] = 'true' if open_now is True else 'false'
        if transactions:
            params['transactions'] = transactions
        if attributes:
            params['attributes'] = attributes
        if latitude:
            params['latitude'] = latitude
        if longitude:
            params['longitude'] = longitude

        data = self._get('https://api.yelp.com/v3/businesses/search', params)
        return data.get('businesses', []), data.get('total', 0)

    def paginate(self, term=None, location=None, categories=None,
                 radius=None, price=None, sort_by='best_match',
                 max_results=None, open_now=None, transactions=None,
                 attributes=None, latitude=None, longitude=None):
        """Pagina todas las páginas disponibles (max 240)."""
        max_results = max_results or self._max_results()
        all_records = []
        for offset in range(0, max_results, self.PAGE_SIZE):
            records, total = self.search(
                term=term, location=location, categories=categories,
                radius=radius, price=price, sort_by=sort_by,
                limit=self.PAGE_SIZE, offset=offset,
                open_now=open_now, transactions=transactions,
                attributes=attributes, latitude=latitude, longitude=longitude)
            all_records.extend(records)
            if len(records) < self.PAGE_SIZE:
                break
            if offset + self.PAGE_SIZE >= self.MAX_OFFSET:
                break
            time.sleep(0.5)
        return all_records, total
