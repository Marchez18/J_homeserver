import dropbox
import os
import time

# ==========================
# CONFIGURACIÓN
# ==========================

SOURCE_FOLDER = "/Camera Uploads/2019"
DEST_FOLDER = "/Camera Uploads/2019-jpg"

RAW_EXTS = {".dng", ".nef", ".cr2", ".arw", ".rw2", ".png", ".webp"}
JPG_EXTS = {".jpg", ".jpeg"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv"}

# ==========================
# CREDENCIALES
# ==========================

def read_secret(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

print("🔐 Cargando credenciales...")
dbx = dropbox.Dropbox(
    oauth2_refresh_token=read_secret("dropbox_token_NEW.txt"),
    app_key=read_secret("dropbox_app_key.txt"),
    app_secret=read_secret("dropbox_app_secret.txt"),
)
print("🔓 Credenciales OK\n")

# ==========================
# UTILIDADES
# ==========================

def list_files(path: str) -> dict:
    """
    Devuelve dict: {filename_lower: FileMetadata}
    """
    files = {}
    result = dbx.files_list_folder(path)

    while True:
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                files[entry.name.lower()] = entry

        if not result.has_more:
            break
        result = dbx.files_list_folder_continue(result.cursor)

    return files


def expected_dest_name(src_name: str) -> str:
    name, ext = os.path.splitext(src_name)
    ext = ext.lower()

    if ext in RAW_EXTS:
        return name + ".jpg"
    else:
        return src_name


# ==========================
# VERIFICACIÓN
# ==========================

print("📂 Leyendo carpeta ORIGEN...")
src_files = list_files(SOURCE_FOLDER)
print(f"   → {len(src_files)} archivos encontrados\n")

print("📂 Leyendo carpeta DESTINO...")
dst_files = list_files(DEST_FOLDER)
print(f"   → {len(dst_files)} archivos encontrados\n")

missing = []
ok = []
unexpected = []

for src_name, src_meta in src_files.items():
    expected = expected_dest_name(src_name)

    if expected.lower() in dst_files:
        ok.append(src_name)
    else:
        missing.append({
            "origen": src_name,
            "esperado": expected
        })

# Archivos en destino que no corresponden a nada en origen
expected_dest_set = {expected_dest_name(name) for name in src_files}
for dst_name in dst_files:
    if dst_name not in expected_dest_set:
        unexpected.append(dst_name)

# ==========================
# REPORTE FINAL
# ==========================

print("\n================= VERIFICATION REPORT =================")
print(f"Archivos origen totales : {len(src_files)}")
print(f"Archivos verificados OK : {len(ok)}")
print(f"❌ Faltantes en destino : {len(missing)}")
print(f"⚠️ Sobrantes en destino : {len(unexpected)}")

if missing:
    print("\n❌ ARCHIVOS FALTANTES:")
    for item in missing[:20]:
        print(f" - {item['origen']}  → esperado: {item['esperado']}")
    if len(missing) > 20:
        print(f"   ... y {len(missing) - 20} más")

if unexpected:
    print("\n⚠️ ARCHIVOS EXTRA EN DESTINO:")
    for name in unexpected[:20]:
        print(f" - {name}")
    if len(unexpected) > 20:
        print(f"   ... y {len(unexpected) - 20} más")

print("\n✅ Verificación completada.")
print("========================================================\n")
