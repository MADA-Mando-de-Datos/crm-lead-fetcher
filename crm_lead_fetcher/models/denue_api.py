import time
from urllib.parse import quote

from odoo import _, api, models
from ..exceptions import LeadSourceConnectionError, LeadSourceDataError, LeadSourceAuthError


class DenueApi(models.AbstractModel):
    _name = 'denue.api'
    _description = 'DENUE (INEGI) API client'

    BASE_URL = 'https://www.inegi.org.mx/app/api/denue/v1/consulta'
    PAGE_SIZE = 10000
    MAX_RETRIES = 3
    RETRY_BACKOFF = 3      # segundos base entre reintentos (crece por intento)
    REQUEST_TIMEOUT = 30

    # Endpoints oficiales verificados contra la doc de INEGI y sondas HTTP reales.
    # OJO: los nombres inventados (BuscarPorActividadYEntidad, BuscarPorNombre)
    # devuelven 404 HTML. El CLEE NO codifica el SCIAN de forma confiable;
    # usar BuscarAreaAct y sus campos *_ACTIVIDAD_ID para clasificar.
    ENDPOINTS = {
        # condicion puede ser "todos" o texto libre (actividad/palabras clave)
        'by_state': 'BuscarEntidad/{condicion}/{entidad}/{ini}/{fin}/{token}',
        'by_activity_state': 'BuscarEntidad/{condicion}/{entidad}/{ini}/{fin}/{token}',
        # búsqueda por nombre comercial o razón social
        'by_name_state': 'Nombre/{nombre}/{entidad}/{ini}/{fin}/{token}',
        # entidad/municipio/localidad/ageb/manzana/sector/subsector/rama/clase/
        # nombre/ini/fin/id/token  (0 = sin filtro en ese nivel)
        'area_act': ('BuscarAreaAct/{entidad}/{municipio}/{localidad}/{ageb}/{manzana}'
                     '/{sector}/{subsector}/{rama}/{clase}/{nombre}/{ini}/{fin}/{id}/{token}'),
        # condicion / lat,long (una sola pieza, separadas por coma) / distancia <= 5000 m
    }

    @api.model
    def _get_param(self, key, default=''):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    @api.model
    def _token(self):
        return self._get_param('crm_lead_fetcher.denue_token').strip()

    @api.model
    def _sleep_seconds(self):
        return float(self._get_param('crm_lead_fetcher.denue_sleep_seconds', '2.0'))

    @api.model
    def _q(self, text):
        """Codifica un segmento de ruta preservando las comas (multi-palabra DENUE)."""
        return quote(str(text), safe=',')

    @api.model
    def _make_request(self, url):
        """GET con reintentos ante fallas de red con backoff exponencial.
        Respuestas no JSON se consideran determinísticas y lanzan LeadSourceDataError."""
        last_error = None
        resp = None
        import requests
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = requests.get(
                    url,
                    timeout=self.REQUEST_TIMEOUT,
                    headers={'User-Agent': 'Mozilla/5.0 (crm-denue-leads)'},
                )
            except requests.exceptions.RequestException as err:
                last_error = err
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_BACKOFF * (attempt + 1))
                continue
            try:
                return resp.json()
            except ValueError as err:
                raise LeadSourceDataError(_(
                    'DENUE devolvió una respuesta no válida (HTTP %s). '
                    'Revise los filtros de búsqueda.',
                    resp.status_code)) from err
        token = self._token()
        error_msg = str(last_error)
        if token and token in error_msg:
            error_msg = error_msg.replace(token, '[TOKEN_PROTEGIDO]')
        raise LeadSourceConnectionError(_('Error de conexión con INEGI DENUE: %s', error_msg))

    @api.model
    def fetch_page(self, endpoint_key, ini=1, fin=100, **params):
        """Fetch a single page for any endpoint"""
        token = self._token()
        if not token:
            raise LeadSourceAuthError(_('Token de DENUE (INEGI) no configurado en Ajustes > CRM.'))
        if endpoint_key not in self.ENDPOINTS:
            raise ValueError(_('Unknown endpoint: %s', endpoint_key))

        path = self.ENDPOINTS[endpoint_key].format(
            token=token,
            ini=ini,
            fin=fin,
            **params,
        )
        url = f'{self.BASE_URL}/{path}'
        return self._make_request(url)

    @api.model
    def _paginate(self, endpoint_key, url_params, max_records):
        """Itera ventanas de resultados. SOLO transporte/paginación: el filtrado
        semántico (sector, estrato, municipio) lo hace el wizard con contadores
        de diagnóstico — filtrar aquí ocultaría las estadísticas al usuario."""
        page_size = self.PAGE_SIZE
        ini = 1
        scanned = 0
        while scanned < max_records and ini <= max_records:
            fin = min(ini + page_size - 1, max_records)
            records = self.fetch_page(endpoint_key, ini, fin, **url_params)
            if not records:
                return
            scanned += len(records)
            yield from records
            if len(records) < (fin - ini + 1):
                return
            ini = fin + 1
            if ini <= max_records:
                time.sleep(self._sleep_seconds())

    @api.model
    def search_by_state(self, entidad, max_records, condicion='todos'):
        """Todo el estado, opcionalmente acotado por texto (BuscarEntidad)"""
        return self._paginate(
            'by_state',
            {'condicion': self._q(condicion or 'todos'), 'entidad': entidad},
            max_records)

    @api.model
    def search_by_activity_and_state(self, actividad, entidad, max_records):
        """Búsqueda por actividad/palabra clave + estado (BuscarEntidad/<texto>)"""
        return self._paginate(
            'by_activity_state',
            {'condicion': self._q(actividad), 'entidad': entidad},
            max_records)

    @api.model
    def search_by_name_and_state(self, nombre, entidad, max_records):
        """Búsqueda por nombre comercial + estado (endpoint Nombre)"""
        return self._paginate(
            'by_name_state',
            {'nombre': self._q(nombre), 'entidad': entidad},
            max_records)

    @api.model
    def search_by_area_act(self, entidad, codigo, max_records):
        """Búsqueda quirúrgica por sector (2 dígitos) o subsector (3 dígitos) SCIAN
        vía BuscarAreaAct. Devuelve además SECTOR_/SUBSECTOR_/RAMA_/CLASE_ACTIVIDAD_ID."""
        codigo = str(codigo)
        params = {
            'entidad': entidad,
            'municipio': 0,
            'localidad': 0,
            'ageb': 0,
            'manzana': 0,
            'sector': codigo if len(codigo) == 2 else 0,
            'subsector': codigo if len(codigo) >= 3 else 0,
            'rama': 0,
            'clase': 0,
            'nombre': 0,
            'id': 0,
        }
        return self._paginate('area_act', params, max_records)

    @api.model
    def test_connection(self, entidad='24'):
        """Test API connection with a sample request"""
        token = self._token()
        if not token:
            return False, _('Token not configured')
        try:
            records = self.fetch_page('by_state', 1, 1, condicion='todos', entidad=entidad)
            count = len(records) if records else 0
            return True, _('Conexión exitosa: %d registro(s) de muestra', count)
        except Exception as e:
            return False, str(e)
