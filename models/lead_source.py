from odoo import _, api, fields, models

# Labels estáticos para estratos DENUE (evitan import circular/frágil)
ESTRATO_LABELS = {
    1: '0 a 5 personas',
    2: '6 a 10 personas',
    3: '11 a 30 personas',
    4: '31 a 50 personas',
    5: '51 a 100 personas',
    6: '101 a 250 personas',
    7: '251 y más personas',
}


class LeadSource(models.AbstractModel):
    """Base abstracta para todas las fuentes de leads.

    Para agregar una nueva fuente:
    1. Crear modelo heredando de LeadSource (o _inherit='lead.source')
    2. Implementar search(), test_connection(), get_available_filters(), record_to_lead_vals()
    3. Registrar en _get_sources()
    """

    _name = 'lead.source'
    _description = 'Fuente de datos de leads (abstracta)'

    source_key = fields.Char(string='Clave técnica', required=True)
    name = fields.Char(string='Nombre', required=True)
    description = fields.Text(string='Descripción')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    def search(self, filters, max_records):
        raise NotImplementedError()

    def test_connection(self, config=None):
        raise NotImplementedError()

    def get_available_filters(self):
        raise NotImplementedError()

    def record_to_lead_vals(self, record, lead_type, team_id, user_id, tag_ids, request_id):
        raise NotImplementedError()

    def validate_filters(self, wizard):
        """Valida que los campos requeridos para esta fuente estén completos en el wizard."""
        pass

    def build_filters(self, wizard):
        """Construye y retorna el diccionario de filtros para el cliente API."""
        return {}

    def get_external_id(self, record):
        """Extrae el identificador único del registro para deduplicación."""
        return str(record.get('external_id') or record.get('place_id') or record.get('id') or record.get('Id') or '').strip()

    def get_automatic_tag_ids(self, record):
        """Retorna IDs de etiquetas crm.tag a asignar automáticamente al lead."""
        return []

    def post_filter(self, records, wizard):
        """Filtra registros después de la búsqueda (opcional). Devuelve records filtrados."""
        return records

    def get_scan_cap(self):
        """Máximo de registros que esta fuente puede escanear."""
        return 50000


class LeadSourceRegistry(models.AbstractModel):
    _name = 'lead.source.registry'
    _description = 'Registro de fuentes de leads'

    @api.model
    def get_source(self, source_key):
        """Obtiene modelo de fuente por clave"""
        sources = self._get_sources()
        model_name = sources.get(source_key)
        if not model_name:
            raise ValueError(_('Fuente de datos desconocida: %s', source_key))
        return self.env[model_name]

    @api.model
    def _get_sources(self):
        """Una sola fuente de verdad para el registro de fuentes."""
        return {
            'denue': 'lead.source.denue',
            'yelp': 'lead.source.yelp',
            'google': 'lead.source.google',
        }

    @api.model
    def list_sources(self):
        """Lista de (key, nombre) de fuentes disponibles."""
        sources = self._get_sources()
        result = []
        for k, v in sources.items():
            if v in self.env:
                result.append((k, self.env[v]._description))
            else:
                result.append((k, k))
        return result

    @api.model
    def _normalize_dedup_key(self, name='', city='', phone=''):
        """Normaliza nombre + ciudad + teléfono para reconciliar negocios entre fuentes."""
        def norm(s):
            return ' '.join((s or '').lower().split())
        return '|'.join([norm(name), norm(city), norm(phone)])

    @api.model
    def find_existing_by_fingerprint(self, vals):
        """Reconcilia un candidato de lead contra leads existentes por nombre+ciudad o teléfono.

        Devuelve el lead existente (recordset) o un recordset vacío si no hay coincidencia.
        """
        Lead = self.env['crm.lead']
        name = (vals.get('name') or vals.get('partner_name') or '').strip()
        phone = (vals.get('phone') or '').strip()
        city = (vals.get('city') or '').strip()

        if not name:
            return Lead

        domain = ['|', ('name', 'ilike', name)]
        if phone:
            domain = ['|', '|', ('name', 'ilike', name), ('phone', '=', phone),
                      ('mobile', '=', phone)]
        elif city:
            domain = ['|', ('name', 'ilike', name), ('city', '=', city)]

        return Lead.search(domain, limit=1)
