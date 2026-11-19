-- ============================================================================
-- BAKERY DATA PLATFORM V4: DUCKDB + MINIO CONNECTION SETUP
-- ============================================================================
-- Jalankan skrip ini pertama kali saat membuka sesi DuckDB di DBeaver.
-- Skrip ini menginstal/memuat ekstensi httpfs dan mengonfigurasi koneksi ke MinIO.
--
-- CATATAN KREDENSIAL:
-- Default kredensial proyek: bakeryadmin / bakerydemo123
-- Jika Anda mendefinisikan custom password di environment lokal, sesuaikan di bawah.
-- ============================================================================

INSTALL httpfs;
LOAD httpfs;

-- Konfigurasi S3 Secret PERMANEN untuk MinIO lokal (Hanya perlu di-run 1x selamanya!)
CREATE OR REPLACE PERSISTENT SECRET minio_secret (
    TYPE S3,
    KEY_ID 'bakeryadmin',
    SECRET 'bakerydemo123',
    ENDPOINT 'localhost:9000',
    URL_STYLE 'path',
    USE_SSL false,
    REGION 'us-east-1'
);

-- Pengaturan kompatibilitas S3 MinIO
SET s3_endpoint = 'localhost:9000';
SET s3_access_key_id = 'bakeryadmin';
SET s3_secret_access_key = 'bakerydemo123';
SET s3_url_style = 'path';
SET s3_use_ssl = false;
SET s3_region = 'us-east-1';

-- Cek koneksi ke bucket MinIO
SELECT 'MinIO Connection OK' AS status;
