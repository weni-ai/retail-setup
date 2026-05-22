"""RSA key-pair generator used by the One-Click Payment configuration.

The PEM output mirrors ``openssl genrsa -out private.pem 2048``
followed by ``openssl rsa -in private.pem -pubout`` — PKCS#1
(``BEGIN RSA PRIVATE KEY``) for the private key and
SubjectPublicKeyInfo (``BEGIN PUBLIC KEY``) for the public key.
"""

from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


DEFAULT_KEY_SIZE = 2048
DEFAULT_PUBLIC_EXPONENT = 65537


@dataclass(frozen=True)
class RSAKeyPair:
    """PEM-encoded RSA key pair."""

    private_key_pem: str
    public_key_pem: str


class RSAKeyGeneratorService:
    """Generates PEM-encoded RSA key pairs for WhatsApp Business Encryption."""

    def __init__(
        self,
        key_size: int = DEFAULT_KEY_SIZE,
        public_exponent: int = DEFAULT_PUBLIC_EXPONENT,
    ):
        self.key_size = key_size
        self.public_exponent = public_exponent

    def generate(self) -> RSAKeyPair:
        private_key = rsa.generate_private_key(
            public_exponent=self.public_exponent,
            key_size=self.key_size,
        )
        return RSAKeyPair(
            private_key_pem=self._serialize_private_key(private_key),
            public_key_pem=self._serialize_public_key(private_key),
        )

    @staticmethod
    def _serialize_private_key(private_key: rsa.RSAPrivateKey) -> str:
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

    @staticmethod
    def _serialize_public_key(private_key: rsa.RSAPrivateKey) -> str:
        return (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )
