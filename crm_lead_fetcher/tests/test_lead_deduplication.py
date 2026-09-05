from odoo.tests.common import TransactionCase


class TestLeadDeduplication(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source_registry = cls.env['lead.source.registry']
        cls.denue_source = cls.env['lead.source.denue']

    def test_fingerprint_normalization_whitespace_and_case(self):
        fp_a = self.source_registry._normalize_dedup_key(
            name="Comercializadora del Centro S.A.",
            city="San Luis Potosí",
            phone="4441112233"
        )
        fp_b = self.source_registry._normalize_dedup_key(
            name="  comercializadora  del centro s.a. ",
            city="san luis potosí",
            phone="4441112233"
        )
        self.assertEqual(fp_a, fp_b)

    def test_external_id_extraction_denue(self):
        record = {'Id': 123456, 'Nombre': 'Sample Business'}
        ext_id = self.denue_source.get_external_id(record)
        self.assertEqual(ext_id, '123456')

    def test_create_leads_from_response_batch_and_dedup(self):
        # Crear un lead previo con teléfono
        self.env['crm.lead'].create({
            'name': 'Pre-existing Business',
            'phone': '4449998877',
        })

        # Crear solicitud de prueba
        request = self.env['crm.lead.request'].create({
            'source_key': 'denue',
            'lead_number': 10,
        })

        sample_records = [
            # 1. Lead normal
            {
                'Id': 90001,
                'Nombre': 'Negocio Uno',
                'Telefono': '4441110001',
                'Ubicacion': 'Centro',
            },
            # 2. Duplicado por mismo teléfono que lead preexistente (debe descartarse)
            {
                'Id': 90002,
                'Nombre': 'Negocio Dos',
                'Telefono': '4449998877',
                'Ubicacion': 'Norte',
            },
            # 3. Duplicado interno en el mismo payload (debe descartarse)
            {
                'Id': 90003,
                'Nombre': 'Negocio Uno',
                'Telefono': '4441110001',
                'Ubicacion': 'Centro',
            },
        ]

        count = request._create_leads_from_response(sample_records)
        self.assertEqual(count, 1)

        created_lead = self.env['crm.lead'].search([('external_id', '=', '90001')])
        self.assertTrue(created_lead.exists())
        self.assertEqual(created_lead.phone, '4441110001')
