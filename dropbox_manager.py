import dropbox
import rawpy
import io
from PIL import Image

# === Leer ACCESS_TOKEN desde un archivo externo ===
TOKEN_FILE = "dropbox_token.txt"

try:
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        ACCESS_TOKEN = f.read().strip()
except FileNotFoundError:
    raise Exception(f"❌ No se encontró el archivo {TOKEN_FILE}. Crea el archivo con tu token dentro.")
except Exception as e:
    raise Exception(f"❌ Error leyendo {TOKEN_FILE}: {e}")


# Nombre exacto de la carpeta origen en el root de Dropbox
SOURCE_FOLDER_NAME = "Camera Upload"     # 🔥 Cambia solo esto
SOURCE_FOLDER_NAME = "/Camera Uploads/Test-dng"




dbx = dropbox.Dropbox(ACCESS_TOKEN)



def get_folder_path_by_name_old(folder_name):
    result = dbx.files_list_folder("", recursive=False)
    for entry in result.entries:
        if isinstance(entry, dropbox.files.FolderMetadata) and entry.name == folder_name:
            return f"/{entry.name}"
    raise Exception(f"No se encontró la carpeta '{folder_name}' en el root del Dropbox.")

def get_folder_path_by_name(folder_path):
    """
    Si recibe una ruta completa (empieza por '/'), no la valida.
    Simplemente la devuelve directamente.
    """
    if folder_path.startswith("/"):
        return folder_path

    # Si es solo un nombre, buscarlo en el root
    result = dbx.files_list_folder("", recursive=False)
    while True:
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FolderMetadata) and entry.name == folder_path:
                return f"/{entry.name}"

        if not result.has_more:
            break

        result = dbx.files_list_folder_continue(result.cursor)

    raise Exception(f"No se encontró la carpeta '{folder_path}' en el root del Dropbox.")


def ensure_folder_exists(path):
    try:
        dbx.files_get_metadata(path)
    except dropbox.exceptions.ApiError:
        dbx.files_create_folder_v2(path)
        print(f"Carpeta creada: {path}")


def get_folder_size(path):
    """Calcula el tamaño total de una carpeta en bytes."""
    size = 0
    result = dbx.files_list_folder(path)

    for entry in result.entries:
        if isinstance(entry, dropbox.files.FileMetadata):
            size += entry.size

    return size


def human_readable_size(bytes_value):
    """Convierte bytes a MB con dos decimales."""
    return f"{bytes_value / (1024*1024):.2f} MB"


def convert_folder_dng_to_jpg():
    source_path = get_folder_path_by_name(SOURCE_FOLDER_NAME)
    print(f"Carpeta origen encontrada: {source_path}")

    # Listar archivos (debug)
    result = dbx.files_list_folder(source_path)
    print("\nArchivos en la carpeta origen:")
    for e in result.entries:
        print(" -", e.name)

    # Crear carpeta destino
    dest_path = source_path + "-jpg2"
    ensure_folder_exists(dest_path)

    # TAMAÑO ORIGINAL
    original_size = get_folder_size(source_path)

    # Convertir archivos
    for entry in result.entries:
        if not isinstance(entry, dropbox.files.FileMetadata):
            continue

        if not entry.name.lower().endswith(".dng"):
            continue

        print(f"Procesando: {entry.name}")

        original_file = f"{source_path}/{entry.name}"
        jpg_filename = entry.name[:-4] + ".jpg"
        jpg_file_path = f"{dest_path}/{jpg_filename}"

        # Saltar si ya existe
        try:
            dbx.files_get_metadata(jpg_file_path)
            print(f"→ Saltado (ya existe): {jpg_filename}")
            continue
        except:
            pass

        # Descargar archivo DNG
        _, response = dbx.files_download(original_file)
        dng_bytes = io.BytesIO(response.content)

        try:
            with rawpy.imread(dng_bytes) as raw:
                rgb = raw.postprocess()

            img = Image.fromarray(rgb)
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=90)
            output.seek(0)

            dbx.files_upload(
                output.read(),
                jpg_file_path,
                mode=dropbox.files.WriteMode("overwrite")
            )

            print(f"→ JPG creado: {jpg_filename}")

        except Exception as e:
            print(f"ERROR al procesar {entry.name}: {e}")

    # TAMAÑO JPG
    jpg_size = get_folder_size(dest_path)

    # CALCULAR AHORRO
    saved = original_size - jpg_size
    percent = (saved / original_size * 100) if original_size > 0 else 0

    print("\n=== SIZE REPORT ===")
    print(f"Original folder size: {human_readable_size(original_size)}")
    print(f"JPG folder size: {human_readable_size(jpg_size)}")
    print(f"Space saved: {human_readable_size(saved)} ({percent:.2f}% reduction)")

def listar_todas_carpetas_root():
    print("📂 Carpetas en el root del Dropbox (todas):")

    result = dbx.files_list_folder("", recursive=False)

    # Procesamos la primera página
    for entry in result.entries:
        if isinstance(entry, dropbox.files.FolderMetadata):
            print(" -", entry.name)

    # Mientras haya más páginas, seguir listando
    while result.has_more:
        result = dbx.files_list_folder_continue(result.cursor)
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FolderMetadata):
                print(" -", entry.name)


if __name__ == "__main__":
    #listar_todas_carpetas_root()

    convert_folder_dng_to_jpg()