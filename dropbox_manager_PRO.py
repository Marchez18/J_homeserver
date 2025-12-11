import dropbox
import rawpy
import io
from PIL import Image
import time
import tracemalloc
import os

# ======================================
# CONFIGURACIÓN
# ======================================

# === Leer ACCESS_TOKEN desde un archivo externo ===
TOKEN_FILE = "dropbox_token.txt"

try:
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        ACCESS_TOKEN = f.read().strip()
except FileNotFoundError:
    raise Exception(f"❌ No se encontró el archivo {TOKEN_FILE}. Crea el archivo con tu token dentro.")
except Exception as e:
    raise Exception(f"❌ Error leyendo {TOKEN_FILE}: {e}")


SOURCE_FOLDER_NAME = "/Camera Uploads/Test-dng"  # Carpeta origen en Dropbox (sin subcarpetas)
SOURCE_FOLDER_NAME = "/Camera Uploads/2025"  # Carpeta origen en Dropbox (sin subcarpetas)


# Carpeta destino = origen + "-jpg"
# Ej: "/Camera Uploads/2025-jpg"
DEST_SUFFIX = "-jpg"

# Velocidad de referencia (tu dato): 260 MB -> 100 s
# => ~0.3846 s/MB
SECONDS_PER_MB = 100 / 260.0

# Extensiones tratadas como RAW (rawpy)
RAW_EXTS = {".dng", ".nef", ".cr2", ".arw", ".rw2"}

# Extensiones de vídeo (se copian tal cual)
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv"}

# ======================================
# INICIALIZACIÓN DROPBOX
# ======================================

dbx = dropbox.Dropbox(ACCESS_TOKEN)


def get_folder_path_by_name(folder_path: str) -> str:
    """
    Si recibe una ruta completa (empieza por '/'), no la valida.
    Simplemente la devuelve directamente.
    """
    if folder_path.startswith("/"):
        return folder_path

    # Si es solo un nombre, buscarlo en el root (por compatibilidad)
    result = dbx.files_list_folder("", recursive=False)
    while True:
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FolderMetadata) and entry.name == folder_path:
                return f"/{entry.name}"

        if not result.has_more:
            break

        result = dbx.files_list_folder_continue(result.cursor)

    raise Exception(f"No se encontró la carpeta '{folder_path}' en el root del Dropbox.")


def ensure_folder_exists(path: str):
    try:
        dbx.files_get_metadata(path)
    except dropbox.exceptions.ApiError:
        dbx.files_create_folder_v2(path)
        print(f"Carpeta creada: {path}")


def get_folder_size(path: str) -> int:
    """Calcula el tamaño total de una carpeta en bytes (sin recursividad)."""
    size = 0
    result = dbx.files_list_folder(path)

    while True:
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                size += entry.size

        if not result.has_more:
            break

        result = dbx.files_list_folder_continue(result.cursor)

    return size


def human_readable_size(bytes_value: int) -> str:
    """Convierte bytes a MB con dos decimales."""
    return f"{bytes_value / (1024 * 1024):.2f} MB"


def human_readable_time(seconds: float) -> str:
    """Convierte segundos a formato legible (Hh Mm Ss)."""
    seconds = int(max(0, seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"


def listar_archivos_y_subcarpetas_old(path: str):
    """
    Lista todos los archivos y subcarpetas del directorio (solo primer nivel).
    Devuelve (files, subfolders)
    """
    files = []
    subfolders = []

    result = dbx.files_list_folder(path)

    while True:
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                files.append(entry)
            elif isinstance(entry, dropbox.files.FolderMetadata):
                subfolders.append(entry)

        if not result.has_more:
            break

        result = dbx.files_list_folder_continue(result.cursor)

    return files, subfolders


def listar_archivos_y_subcarpetas(path: str):
    files = []
    subfolders = []

    result = dbx.files_list_folder(path)

    while True:
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                files.append(entry)
            elif isinstance(entry, dropbox.files.FolderMetadata):
                subfolders.append(entry)

        if not result.has_more:
            break

        result = dbx.files_list_folder_continue(result.cursor)

    return files, subfolders



def pre_scan_report(source_path: str, files, subfolders):
    """
    Hace el análisis previo: cuenta archivos, tamaños, extensiones,
    detecta subcarpetas y estima tiempo usando factores calibrados.
    """
    print("📊 PRE-PROCESSING REPORT")
    print("----------------------------------------")

    if subfolders:
        print("⚠ Se han detectado subcarpetas en la ruta indicada:")
        for folder in subfolders:
            print(f" - {source_path}/{folder.name}")
        print("\n❌ Por seguridad, el proceso se detiene. El script solo trabaja con carpetas sin subcarpetas.")
        return False  # No continuar

    total_files = len(files)
    print(f"Archivos totales: {total_files}")

    if total_files == 0:
        print("❌ No hay archivos en la carpeta. Nada que hacer.")
        return False

    total_size = 0
    ext_counts = {}
    video_count = 0

    print("\nDetalle de archivos:")
    for entry in files:
        size_mb = entry.size / (1024 * 1024)
        total_size += entry.size
        name = entry.name
        ext = os.path.splitext(name)[1].lower()

        ext_counts[ext] = ext_counts.get(ext, 0) + 1

        if ext in VIDEO_EXTS:
            video_count += 1

        print(f" - {name} — {size_mb:.2f} MB")

    print("\nExtensiones detectadas:")
    for ext, count in sorted(ext_counts.items(), key=lambda x: x[0]):
        print(f" - {ext if ext else '(sin extensión)'} : {count}")

    print(f"\nVídeos detectados (se copiarán sin convertir): {video_count}")

    print(f"\nTamaño total: {human_readable_size(total_size)}")

    # ============================
    # NUEVA ESTIMACIÓN DE TIEMPO
    # ============================

    # Factores calibrados con tus pruebas reales
    FACTOR_DNG_PER_MB = 0.20      # segundos por MB
    FACTOR_PNG_PER_MB = 1.50      # segundos por MB
    FACTOR_JPG_COPY   = 0.05      # segundos por archivo
    FACTOR_VIDEO_COPY = 0.30      # segundos por archivo
    OVERHEAD_RATIO    = 0.05      # +5% extra

    total_dng_mb = 0
    total_png_mb = 0
    num_jpg = ext_counts.get(".jpg", 0) + ext_counts.get(".jpeg", 0)
    num_videos = video_count

    for entry in files:
        ext = os.path.splitext(entry.name)[1].lower()
        size_mb = entry.size / (1024 * 1024)

        if ext == ".dng":
            total_dng_mb += size_mb
        elif ext == ".png":
            total_png_mb += size_mb

    # Tiempos por categoría
    time_dng = total_dng_mb * FACTOR_DNG_PER_MB
    time_png = total_png_mb * FACTOR_PNG_PER_MB
    time_jpg = num_jpg * FACTOR_JPG_COPY
    time_vid = num_videos * FACTOR_VIDEO_COPY

    estimated_seconds = (time_dng + time_png + time_jpg + time_vid)
    estimated_seconds *= (1 + OVERHEAD_RATIO)  # overhead

    # Mostrar desglose
    print("\n⏱ Estimación refinada del tiempo total:")
    print(f" - Conversión DNG : {human_readable_time(time_dng)}")
    print(f" - Conversión PNG : {human_readable_time(time_png)}")
    print(f" - Copia JPG      : {human_readable_time(time_jpg)}")
    print(f" - Copia vídeos   : {human_readable_time(time_vid)}")
    print(f" - Overhead (5%)  : incluido")

    print(f"\n⏳ Tiempo estimado TOTAL: {human_readable_time(estimated_seconds)}")

    print("----------------------------------------")
    if False:
        
        choice = input("¿Deseas continuar con la conversión? (yes/no): ").strip()
        if choice != "yes":
            print("Operación cancelada por el usuario.")
            return False
        else:
            return True

    # Pausa breve antes de la cuenta atrás
    time.sleep(2)

    # ======== CUENTA ATRÁS DE 15 SEGUNDOS ========
    print("\n🔔 La migración comenzará automáticamente en 15 segundos.\n")

    for i in range(15, 0, -1):
        print(f"Iniciando en {i} segundos...")
        time.sleep(1)

    print("\n🚀 Iniciando conversión...\n")
    # ============================================

    return True



def convert_folder_to_jpg():
    source_path = get_folder_path_by_name(SOURCE_FOLDER_NAME)
    print(f"Carpeta origen encontrada: {source_path}")

    # Listar archivos y subcarpetas
    files, subfolders = listar_archivos_y_subcarpetas(source_path)

    # Informe previo y confirmación
    if not pre_scan_report(source_path, files, subfolders):
        return

    # Carpeta destino
    dest_path = source_path + DEST_SUFFIX
    ensure_folder_exists(dest_path)

    total_files = len(files)

    # Estadísticas de proceso
    images_converted = 0
    videos_copied = 0
    unsupported_skipped = 0
    unsupported_exts = set()

    # Medición de tiempo y memoria
    tracemalloc.start()
    start_time = time.time()

    print("\n🚀 Iniciando conversión...\n")

    for idx, entry in enumerate(files, start=1):
        name = entry.name
        ext = os.path.splitext(name)[1].lower()
        original_file = f"{source_path}/{name}"

        # Progreso básico
        elapsed = time.time() - start_time
        avg_per_file = elapsed / idx if idx > 0 else 0
        est_total = avg_per_file * total_files
        remaining = est_total - elapsed
        percent = (idx / total_files) * 100

        print(f"[{idx}/{total_files}] ({percent:.2f}%) — Procesando: {name}")
        print(f"   Tiempo transcurrido: {human_readable_time(elapsed)}")
        print(f"   Tiempo estimado restante: {human_readable_time(remaining)}")
        print(f"   Tiempo total estimado: {human_readable_time(est_total)}")

        # 1) Si es vídeo → copiar directamente
        if ext in VIDEO_EXTS:
            dest_video_path = f"{dest_path}/{name}"
            try:
                # Intentar copia directa en Dropbox
                try:
                    dbx.files_copy_v2(original_file, dest_video_path)
                except dropbox.exceptions.ApiError:
                    # Si ya existe, lo dejamos
                    pass
                videos_copied += 1
            except Exception as e:
                print(f"   ERROR al copiar vídeo {name}: {e}")
            print()
            continue

        # 2) Si es JPG/JPEG → copiar sin recomprimir
        if ext in {".jpg", ".jpeg"}:
            dest_jpg_path = f"{dest_path}/{name}"
            try:
                try:
                    dbx.files_copy_v2(original_file, dest_jpg_path)
                except dropbox.exceptions.ApiError:
                    # Si ya existe, lo dejamos
                    pass
                images_converted += 1
            except Exception as e:
                print(f"   ERROR al copiar JPG {name}: {e}")
            print()
            continue

        # 3) El resto, intentamos convertir a JPG
        jpg_filename = os.path.splitext(name)[0] + ".jpg"
        jpg_file_path = f"{dest_path}/{jpg_filename}"

        # Saltar si ya existe
        try:
            dbx.files_get_metadata(jpg_file_path)
            print(f"   → Saltado (ya existe): {jpg_filename}\n")
            images_converted += 1
            continue
        except dropbox.exceptions.ApiError:
            pass  # No existe, seguimos

        # Descargar archivo original
        try:
            _, response = dbx.files_download(original_file)
            file_bytes = io.BytesIO(response.content)
        except Exception as e:
            print(f"   ERROR al descargar {name}: {e}\n")
            unsupported_skipped += 1
            unsupported_exts.add(ext)
            continue

        # Convertir a RGB usando rawpy o PIL
        img = None
        try:
            if ext in RAW_EXTS:
                with rawpy.imread(file_bytes) as raw:
                    rgb = raw.postprocess()
                img = Image.fromarray(rgb)
            else:
                img = Image.open(file_bytes)
                img = img.convert("RGB")
        except Exception as e:
            print(f"   ERROR al procesar {name} ({ext}): {e}")
            print("   → Marcado como no soportado.\n")
            unsupported_skipped += 1
            unsupported_exts.add(ext)
            continue

        # Guardar como JPG en memoria
        try:
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=90)
            output.seek(0)

            dbx.files_upload(
                output.read(),
                jpg_file_path,
                mode=dropbox.files.WriteMode("overwrite")
            )
            images_converted += 1
            print(f"   → JPG creado: {jpg_filename}\n")
        except Exception as e:
            print(f"   ERROR al subir JPG {jpg_filename}: {e}\n")
            unsupported_skipped += 1
            unsupported_exts.add(ext)
            continue

    # Medidas finales
    end_time = time.time()
    elapsed_total = end_time - start_time
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    original_size = get_folder_size(source_path)
    final_size = get_folder_size(dest_path)
    saved = original_size - final_size
    percent_reduction = (saved / original_size * 100) if original_size > 0 else 0.0

    peak_mb = peak_mem / (1024 * 1024)

    print("\n======== FINAL REPORT ========")
    print(f"Original files: {total_files}")
    print(f"Processed images (JPG/copied): {images_converted}")
    print(f"Videos copied: {videos_copied}")
    if unsupported_skipped > 0:
        exts_str = ", ".join(sorted(unsupported_exts)) if unsupported_exts else "desconocidas"
        print(f"Unsupported files skipped: {unsupported_skipped} (extensiones: {exts_str})")
    else:
        print("Unsupported files skipped: 0")

    print(f"\nTiempo total: {human_readable_time(elapsed_total)}")
    print(f"Pico de memoria (tracemalloc): {peak_mb:.2f} MB")

    print("\n=== SIZE REPORT ===")
    print(f"Original folder size: {human_readable_size(original_size)}")
    print(f"JPG folder size: {human_readable_size(final_size)}")
    print(f"Space saved: {human_readable_size(saved)} ({percent_reduction:.2f}% reduction)")
    print(f"Ruta destino: {dest_path}")
    print("================================\n")


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
    # listar_todas_carpetas_root()

    convert_folder_to_jpg()
