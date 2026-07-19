"""
Genera el par de llaves VAPID que necesitas para Web Push (notificaciones
push del navegador / PWA).

Uso:
    python scripts/generate_vapid_keys.py

Copia el resultado a config.yaml -> notifications.webpush
"""
from py_vapid import Vapid02


def main():
    vapid = Vapid02()
    vapid.generate_keys()
    print("Agrega esto a config.yaml (notifications.webpush):\n")
    print(f'  vapid_public_key: "{vapid.public_key_bytes().decode() if hasattr(vapid, "public_key_bytes") else "(ver README)"}"')
    print("\nNota: py_vapid expone las llaves en distintos formatos según versión.")
    print("Si el comando de arriba falla, usa la utilidad de línea de comandos:")
    print("  vapid --gen -f private_key.pem")
    print("y extrae la pública/privada en formato base64url con:")
    print("  npx web-push generate-vapid-keys   (requiere Node.js, alternativa más simple)")


if __name__ == "__main__":
    main()
