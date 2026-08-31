from odoo import http

from odoo.addons.web.controllers.home import Home


class CrmLeadFetcherController(http.Controller):

    @http.route('/crm_lead_fetcher/export_csv', type='http', auth='user', website=False)
    def export_csv(self, request_id=None, **kw):
        """Descarga los leads de una solicitud en formato CSV."""
        if not request_id:
            return Home().web_client()

        request_model = http.request.env['crm.lead.request']
        request_rec = request_model.browse(int(request_id))
        if not request_rec.exists():
            return Home().web_client()

        leads = http.request.env['crm.lead'].search(
            [('lead_request_id', '=', request_rec.id)], order='id')

        header = ['Nombre', 'Tipo', 'Teléfono', 'Email', 'Sitio Web', 'Calle',
                  'Ciudad', 'Estado', 'CP', 'Calificación', 'Reseñas',
                  'Nivel Precio', 'Latitud', 'Longitud', 'Fuente', 'ID Externo',
                  'Descripción']
        rows = []
        for lead in leads:
            rows.append([
                lead.name or '',
                'Lead' if lead.type == 'lead' else 'Oportunidad',
                lead.phone or '',
                lead.email_from or '',
                lead.website or '',
                lead.street or '',
                lead.city or '',
                lead.state_id.name or (lead.state or ''),
                lead.zip or '',
                lead.source_rating,
                lead.source_reviews,
                lead.source_price_level or '',
                lead.latitude,
                lead.longitude,
                lead.source_key or '',
                lead.external_id or '',
                (lead.description or '').replace('\n', ' '),
            ])

        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(header)
        writer.writerows(rows)
        csv_bytes = buf.getvalue().encode('utf-8-sig')

        filename = 'leads_%s.csv' % (request_rec.name or request_rec.id)
        return http.request.make_response(
            csv_bytes,
            headers=[
                ('Content-Type', 'text/csv; charset=utf-8'),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ],
        )
