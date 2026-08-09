"""
Script para purgar y eliminar automáticamente los mensajes de prueba
enviados a tu canal de Discord vía Webhook.

Uso:
    python scripts/clear_discord_chat.py
"""
import asyncio
import os
import sys
from pathlib import Path

# Agregar el directorio raíz al path de importación
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import yaml
from core import storage

def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    webhook_env = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook_env:
        cfg["notifications"]["discord"]["webhook_url"] = webhook_env
    return cfg

async def clear_discord_messages():
    print("Iniciando purga de mensajes de Discord enviados durante pruebas...")
    cfg = load_config()
    webhook_url = cfg["notifications"]["discord"]["webhook_url"]

    if not webhook_url or "TU_WEBHOOK_AQUI" in webhook_url:
        print("Error: No se encontró una URL de Webhook de Discord válida en config.yaml ni en DISCORD_WEBHOOK_URL.")
        return

    # Limpiar cualquier parámetro de la URL
    base_webhook_url = webhook_url.split("?")[0].rstrip("/")

    # Obtener los IDs de mensajes guardados en la BD
    storage.init_db()
    msg_ids = storage.get_all_discord_message_ids()

    if not msg_ids:
        print("No hay IDs de mensajes registrados en la base de datos local para eliminar.")
        print("Si deseas limpiar un canal entero en Discord, puedes usar el truco de 'Clonar Canal' en Discord:")
        print("  1. Haz clic derecho sobre el canal de Discord -> 'Clonar canal'.")
        print("  2. Elimina el canal viejo con los mensajes de prueba.")
        return

    print(f"Encontrados {len(msg_ids)} mensajes registrados para eliminar...")

    deleted_count = 0
    async with httpx.AsyncClient(timeout=10) as client:
        for mid in msg_ids:
            delete_url = f"{base_webhook_url}/messages/{mid}"
            try:
                resp = await client.delete(delete_url)
                if resp.status_code in (200, 204):
                    deleted_count += 1
                    print(f"  [+] Mensaje {mid} eliminado correctamente.")
                elif resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 1.5))
                    await asyncio.sleep(retry_after)
                    resp = await client.delete(delete_url)
                    if resp.status_code in (200, 204):
                        deleted_count += 1
                        print(f"  [+] Mensaje {mid} eliminado correctamente tras reintento.")
                else:
                    print(f"  [-] No se pudo eliminar mensaje {mid} (Status {resp.status_code}).")
            except Exception as e:
                print(f"  [-] Error eliminando mensaje {mid}: {e}")

    print(f"\n¡Purga completada! {deleted_count} mensajes de prueba eliminados de Discord.")

if __name__ == "__main__":
    asyncio.run(clear_discord_messages())
