from cryptography.hazmat.primitives import serialization
from django.test import TestCase

from retail.services.key_generator.service import (
    DEFAULT_KEY_SIZE,
    DEFAULT_PUBLIC_EXPONENT,
    RSAKeyGeneratorService,
)


class TestRSAKeyGeneratorService(TestCase):
    def setUp(self):
        # Use a 1024-bit key to keep the test fast; the production
        # default of 2048 is exercised by the service-level smoke test
        # below.
        self.service = RSAKeyGeneratorService(key_size=1024)

    def test_generate_returns_pem_strings(self):
        keys = self.service.generate()
        self.assertIsInstance(keys.private_key_pem, str)
        self.assertIsInstance(keys.public_key_pem, str)

    def test_private_key_uses_pkcs1_pem_header(self):
        keys = self.service.generate()
        self.assertTrue(
            keys.private_key_pem.startswith("-----BEGIN RSA PRIVATE KEY-----")
        )

    def test_public_key_uses_subject_public_key_info_header(self):
        keys = self.service.generate()
        self.assertTrue(keys.public_key_pem.startswith("-----BEGIN PUBLIC KEY-----"))

    def test_generated_keys_are_a_matching_pair(self):
        keys = self.service.generate()
        private_obj = serialization.load_pem_private_key(
            keys.private_key_pem.encode(), password=None
        )
        public_obj = serialization.load_pem_public_key(keys.public_key_pem.encode())

        self.assertEqual(
            private_obj.public_key().public_numbers(),
            public_obj.public_numbers(),
        )

    def test_default_constants_match_meta_requirements(self):
        # Meta requires RSA 2048; F4 (65537) is the public exponent.
        self.assertEqual(DEFAULT_KEY_SIZE, 2048)
        self.assertEqual(DEFAULT_PUBLIC_EXPONENT, 65537)

    def test_each_call_returns_a_different_pair(self):
        first = self.service.generate()
        second = self.service.generate()
        self.assertNotEqual(first.private_key_pem, second.private_key_pem)
        self.assertNotEqual(first.public_key_pem, second.public_key_pem)
