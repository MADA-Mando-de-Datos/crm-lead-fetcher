from odoo import api, models

from .lead_source import ESTRATO_LABELS

ESTRATO_MAP = {
    '0 a 5 personas': 1,
    '6 a 10 personas': 2,
    '11 a 30 personas': 3,
    '31 a 50 personas': 4,
    '51 a 100 personas': 5,
    '101 a 250 personas': 6,
    '251 y más personas': 7,
}


class DenueLeadHelpers(models.AbstractModel):
    _name = 'denue.lead.helpers'
    _description = 'Mapeo de registros DENUE a valores de lead CRM'

    @api.model
    def estrato_to_int(self, estrato_text):
        return ESTRATO_MAP.get((estrato_text or '').strip(), 0)

    @api.model
    def estrato_label(self, estrato_int):
        return ESTRATO_LABELS.get(estrato_int, '')

    @api.model
    def _get_city(self, record):
        """Extrae ciudad/municipio/localidad del registro DENUE"""
        # Prioridad: Localidad > Municipio > Ciudad
        city = (record.get('Localidad') or
                record.get('Municipio') or
                record.get('Ciudad') or '')
        if city:
            return city
        # BuscarAreaAct no trae Municipio/Localidad: 'Ubicacion' tiene la forma
        # "ASIENTO<padding>, Municipio, ESTADO"
        ubicacion = record.get('Ubicacion') or ''
        parts = [p.strip() for p in ubicacion.split(',') if p.strip()]
        if len(parts) >= 2:
            return parts[1]
        return parts[0] if parts else ''

    @api.model
    def ubicacion_text(self, record):
        """Texto de ubicación para filtros 'contiene' (municipio/localidad)."""
        return ' '.join(filter(None, [
            record.get('Municipio') or '',
            record.get('Localidad') or '',
            record.get('Ciudad') or '',
            (record.get('Ubicacion') or '').replace(',', ' '),
        ]))

    @api.model
    def lead_vals(self, record, lead_type, team_id, user_id, tag_ids, request_id):
        name = (record.get('Nombre') or record.get('Razon_social') or '').strip()
        phone = (record.get('Telefono') or '').strip()
        email = (record.get('Correo_e') or '').strip()
        website = (record.get('Sitio_internet') or '').strip()
        if website and not website.startswith(('http://', 'https://')):
            website = 'https://%s' % website
        street = ' '.join(
            filter(None, [
                record.get('Calle') or '',
                record.get('Num_Exterior') or '',
                record.get('Num_Interior') or '',
            ])
        ).strip()
        return {
            'type': lead_type,
            'team_id': team_id,
            'user_id': user_id,
            'tag_ids': [(6, 0, tag_ids)],
            'external_id': str(record.get('Id') or ''),
            'lead_request_id': request_id,
            'name': name,
            'partner_name': record.get('Razon_social') or name,
            'email_from': email,
            'phone': phone,
            'website': website,
            'street': street,
            'street2': record.get('Colonia') or '',
            'city': self._get_city(record),
            'zip': record.get('CP') or '',
            'description': record.get('Clase_actividad') or '',
            'latitude': record.get('Latitud'),
            'longitude': record.get('Longitud'),
        }