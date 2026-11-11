"""Generate local RSA keys without overwriting an existing pair."""
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main() -> None:
    directory = Path(__file__).resolve().parents[1] / ".keys"
    directory.mkdir(exist_ok=True)
    private_path = directory / "private.pem"
    public_path = directory / "public.pem"
    if private_path.exists() or public_path.exists():
        raise SystemExit("Key file already exists; refusing to overwrite.")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with private_path.open("xb") as file:
        file.write(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
    with public_path.open("xb") as file:
        file.write(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
    print("Created .keys/private.pem and .keys/public.pem")


if __name__ == "__main__":
    main()
