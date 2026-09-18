from odoo import api, fields, models


class CrmDenueSector(models.Model):
    _name = "crm.denue.sector"
    _description = "Sector económico DENUE (SCIAN 2023)"
    _order = "code"

    code = fields.Char(string="Código SCIAN", required=True, index=True)
    name = fields.Char(string="Nombre del sector", required=True)
    sector_code = fields.Char(
        string="Código sector (2 dígitos)", index=True, help="Código del sector padre en la jerarquía SCIAN"
    )
    sector_name = fields.Char(string="Sector padre", help="Nombre del sector de 2 dígitos (ej. Información en medios)")
    description = fields.Text(
        string="Descripción", help="Descripción en lenguaje claro del tipo de negocios que incluye"
    )
    keywords = fields.Char(string="Palabras clave", help="Términos de búsqueda separados por comas")

    def _compute_display_name(self):
        """Muestra 'Código - Nombre' para que el usuario sepa qué sector elige."""
        for rec in self:
            base = rec.name or ""
            code = (rec.code or "").strip()
            rec.display_name = f"{code} - {base}" if code else base

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        """Búsqueda mejorada (Odoo 18): código SCIAN, nombre, sector padre y keywords.

        Busca sobre una cadena combinada (código + nombre + sector padre + keywords)
        para que términos cotidianos (ej. "abogados", "despacho") encuentren el
        sector correcto sin importar dónde esté la palabra.
        """
        if not name:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)
        name = name.strip()
        if not name:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        term = name.lower()
        domain = [
            "|",
            "|",
            "|",
            ("code", operator, name),
            ("name", operator, name),
            ("sector_name", operator, name),
            ("keywords", operator, name),
        ]
        # Encuentra todos los IDs que matchean (respeta el limit con holgura)
        ids = self.search((args or []) + domain, limit=max(limit, 100)).ids

        # Reordena por relevancia: primero coincidencias exactas/principales
        def _score(rec_id):
            rec = self.browse(rec_id)
            blob = " ".join(
                filter(
                    None,
                    [
                        rec.code or "",
                        rec.name or "",
                        rec.sector_name or "",
                        rec.keywords or "",
                    ],
                )
            ).lower()
            if blob == term or rec.name and rec.name.lower() == term:
                return 0
            if any(w == term for w in blob.split(",")):
                return 1
            if rec.name and term in rec.name.lower():
                return 2
            if rec.sector_name and term in rec.sector_name.lower():
                return 3
            return 4

        ids.sort(key=_score)
        recs = self.browse(ids[:limit])
        return [(r.id, r.display_name) for r in recs]
