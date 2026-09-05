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
