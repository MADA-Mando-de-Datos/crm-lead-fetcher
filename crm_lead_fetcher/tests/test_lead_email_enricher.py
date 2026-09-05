import unittest
from unittest.mock import patch
from odoo.tests.common import TransactionCase


class TestLeadEmailEnricher(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enricher = cls.env['lead.email.enricher']

    def test_anti_ssrf_rejects_loopback(self):
        with patch('socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(None, None, None, None, ('127.0.0.1', 80))]
            self.assertFalse(self.enricher._is_safe_url('http://internal.example.org'))

    def test_anti_ssrf_rejects_rfc1918_private_ranges(self):
        private_test_ips = ['10.0.0.1', '172.16.0.1', '192.168.0.1']
        with patch('socket.getaddrinfo') as mock_dns:
            for test_ip in private_test_ips:
                mock_dns.return_value = [(None, None, None, None, (test_ip, 80))]
                self.assertFalse(self.enricher._is_safe_url('http://intranet.example.org'))

    def test_anti_ssrf_allows_public_domain(self):
        with patch('socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(None, None, None, None, ('93.184.216.34', 80))]
            self.assertTrue(self.enricher._is_safe_url('https://example.com'))

    def test_email_regex_extracts_contact_address(self):
        html_sample = '<div><p>Contact us at info@acme-corp.com for inquiries</p></div>'
        result = self.enricher._extract_email(html_sample)
        self.assertEqual(result, 'info@acme-corp.com')

    def test_email_regex_discards_image_asset_patterns(self):
        html_sample = '<img src="icon@2x.png"><a href="mailto:support@example.org">Support</a>'
        result = self.enricher._extract_email(html_sample)
        self.assertEqual(result, 'support@example.org')

    def test_email_regex_discards_telemetry_addresses(self):
        html_sample = '<span>Tracker key js@sentry.io initialized</span>'
        result = self.enricher._extract_email(html_sample)
        self.assertIsNone(result)

    def test_mailto_extraction_with_query_params(self):
        html_sample = '<p>Escríbenos a <a href="mailto:hola@empresa.com?subject=Informacion">Contacto</a></p>'
        result = self.enricher._extract_email(html_sample)
        self.assertEqual(result, 'hola@empresa.com')

    def test_dynamic_contact_links_discovery(self):
        base_url = 'https://miempresa.com'
        html_sample = '''
        <html>
        <body>
            <nav>
                <a href="/nosotros">Quiénes somos</a>
                <a href="/contacto-directo">Contacto</a>
                <a href="https://externo.com/contacto">Externo</a>
            </nav>
        </body>
        </html>
        '''
        links = self.enricher._find_contact_links(base_url, html_sample)
        self.assertIn('https://miempresa.com/contacto-directo', links)
        self.assertIn('https://miempresa.com/nosotros', links)
        # Debe descartar enlaces externos
        self.assertNotIn('https://externo.com/contacto', links)

    def test_social_and_whatsapp_extraction(self):
        html_sample = '''
        <footer>
            <a href="https://api.whatsapp.com/send?phone=524441112233">Escríbenos por WhatsApp</a>
            <a href="https://www.facebook.com/miempresa">Facebook</a>
            <a href="https://www.facebook.com/sharer/sharer.php?u=foo">Compartir</a>
        </footer>
        '''
        channels = self.enricher._extract_social_and_whatsapp(html_sample)
        self.assertEqual(channels.get('whatsapp'), 'https://api.whatsapp.com/send?phone=524441112233')
        self.assertEqual(channels.get('facebook'), 'https://www.facebook.com/miempresa')

    def test_crm_lead_batch_enrichment(self):
        lead_1 = self.env['crm.lead'].create({
            'name': 'Empresa Batch Uno',
            'website': 'https://batch-uno.com',
        })
        lead_2 = self.env['crm.lead'].create({
            'name': 'Empresa Batch Dos',
        })

        leads = lead_1 | lead_2

        # Mockear enrich_url y discover_website_by_query
        with patch.object(type(self.enricher), 'enrich_url', return_value='contacto@batch-uno.com'):
            with patch.object(type(self.enricher), 'discover_website_by_query', return_value='https://batch-dos.com'):
                res = leads.action_enrich_email_batch()
                self.assertEqual(res['type'], 'ir.actions.client')
                self.assertEqual(lead_1.email_from, 'contacto@batch-uno.com')
                self.assertEqual(lead_2.website, 'https://batch-dos.com')

