# Kamus & Definisi Metrik Finansial — Bakery Data Platform V4

Dokumen ini mendokumentasikan definisi resmi, formula kalkulasi, pemetaan kolom sumber ESB (*Enterprise Service Bus* Toko Roti Pagi), serta aturan audit rekonsiliasi data pada lapisan **Silver** dan **Gold Layer**.

---

## 1. Pemetaan Kolom Sumber ESB ke Model Data

Berdasarkan audit komprehensif pada data transaksi aktual Toko Roti Pagi (TRP), berikut adalah pemetaan atribut sumber ke lapisan data:

| Kolom Sumber ESB | Tipe Data Asli | Kolom Silver Layer (`silver_sales_items`) | Kolom Gold Layer | Definisi & Penjelasan Bisnis |
| :--- | :--- | :--- | :--- | :--- |
| `Sales Number` | String | `sales_number` | - | Nomor identifikasi transaksi penjualan. |
| `Bill Number` | String | `bill_number` | - | Nomor struk/bill unik per transaksi. |
| `Sales Date` / `Sales Date Out` | String (WIB) | `sales_date` / `sales_date_out` | `sales_date` / `sales_hour` | Tanggal transaksi bisnis & timestamp checkout selesai (WIB). |
| `Branch` | String | `branch` | `branch` | Cabang Toko Roti Pagi (misal: `TRP G-WALK`). |
| `Payment Method` | String | `payment_method` | `payment_method` | Metode pembayaran transaksi (CASH, QRIS BRI, dll.). |
| `Menu Code` | String | `menu_code` | `menu_key` (fallback) | Kode SKU menu (bisa bernilai `NULL` pada sistem kasir). |
| `Menu` | String | `menu` | `menu_name` | Nama produk roti/minuman. |
| `Menu Category` | String | `menu_category` | `menu_category` | Kategori produk (`BEVERAGE`, `PASTRY`, dll.). |
| `Qty` | String/Float | `qty` (DECIMAL(12,2)) | `total_qty_sold` / `qty_sold` | Kuantitas unit produk yang dibeli. |
| `Price` | String/Float | `price` (DECIMAL(14,2)) | `master_standard_price` | Harga satuan menu sebelum diskon. |
| `Subtotal` | String/Float | `subtotal` (DECIMAL(14,2)) | `gross_sales` | Nilai penjualan kotor: $Price \times Qty$. |
| `Discount` | String/Float | `discount` (DECIMAL(14,2)) | `total_discount` | Potongan diskon promosi tingkat item. |
| `Nett Sales` | String/Float | `nett_sales` (DECIMAL(14,2)) | `net_sales` | Penjualan bersih: $Subtotal - Discount$. |
| `Total` | String/Float | `total` (DECIMAL(14,2)) | - | Nilai total transaksi setelah pajak & servis (di TRP identik dengan `nett_sales`). |
| `Bill Discount` | String/Float | `bill_discount` (DECIMAL(14,2)) | - | Diskon tingkat tagihan/bill. |
| `Service Charge` | String/Float | `service_charge` (DECIMAL(14,2)) | - | Biaya layanan (aktual bernilai `0.00`). |
| `Tax` / `VAT` | String/Float | `tax` / `vat` (DECIMAL(14,2)) | - | Pajak pertambahan nilai (aktual bernilai `0.00`). |
| `DPP` | String/Float | `dpp` (DECIMAL(14,2)) | - | Dasar Pengenaan Pajak (aktual bernilai `0.00`). |

---

## 2. Definisi Resmi Metrik Finansial

### A. Gross Sales (Penjualan Kotor)
- **Definisi:** Akumulasi nilai penjualan kotor seluruh produk sebelum dikenakan potongan harga atau diskon apapun.
- **Formula:**
  $$\text{Gross Sales} = \sum (\text{Subtotal}) = \sum (\text{Price} \times \text{Qty})$$
- **Grain:** Dihitung dari baris item valid (`silver_sales_items`).

### B. Discount (Potongan Harga)
- **Definisi:** Total nilai potongan promosi atau voucher yang diaplikasikan pada baris menu.
- **Formula:**
  $$\text{Total Discount} = \sum (\text{Discount})$$
- **Catatan:** Jika terdapat `Bill Discount`, sistem Silver menghitung `total_after_bill_discount` = $\text{Total} - \text{Bill Discount}$. Pada data aktual TRP, diskon diaplikasikan langsung pada baris item (`Discount`).

### C. Net Sales (Penjualan Bersih / Revenue Utama)
- **Definisi:** Nilai penjualan riil yang menjadi pendapatan bersih bagi Toko Roti Pagi setelah seluruh diskon dikurangkan. Ini adalah **Single Source of Truth** untuk seluruh laporan performa dan monitoring eksekutif.
- **Formula:**
  $$\text{Net Sales} = \sum (\text{Nett Sales}) = \text{Gross Sales} - \text{Total Discount}$$
- **Konsistensi Lintas Mart:**
  Nilai `Net Sales` wajib menghasilkan angka yang sama persis (selisih `0.00`) antara:
  - `gold_sales_daily.net_sales`
  - `gold_sales_hourly.net_sales`
  - `gold_menu_performance_daily.net_sales`
  - `gold_category_performance_daily.net_sales`
  - `gold_payment_daily.net_sales`

### D. Total Bills (Jumlah Transaksi Unik)
- **Definisi:** Jumlah transaksi/bill unik yang sah dan terkonfirmasi.
- **Formula:**
  $$\text{Total Bills} = \text{COUNT}(\text{DISTINCT } \text{event\_id})$$
- **Pencegahan Double-Counting:** Satu bill dapat memiliki banyak item. Total bills dihitung menggunakan `COUNT(DISTINCT event_id)` atau dari tabel agregat bill (`silver_sales_bills`), **bukan** dari `COUNT(item_id)`.

### E. Average Order Value (AOV / Rata-Rata Nilai Belanja)
- **Definisi:** Rata-rata nominal belanja bersih yang dibelanjakan pelanggan dalam satu kali kunjungan transaksi.
- **Formula:**
  $$\text{Average Order Value (AOV)} = \begin{cases} \text{ROUND}\left(\frac{\text{Net Sales}}{\text{Total Bills}}, 2\right) & \text{jika } \text{Total Bills} > 0 \\ 0.00 & \text{jika } \text{Total Bills} = 0 \end{cases}$$
- **Penanganan Zero Division:** Dilindungi dengan ekspresi kondisional `CASE WHEN total_bills > 0` / `NULLIF(total_bills, 0)` sehingga aman saat tidak ada transaksi.

### F. Sales Contribution Percentage (Persentase Kontribusi Penjualan)
- **Definisi:** Porsi kontribusi pendapatan bersih kategori produk atau metode pembayaran tertentu terhadap total penjualan harian cabang.
- **Formula:**
  $$\text{Contribution \%} = \text{ROUND}\left(\frac{\text{Net Sales}_{\text{dimensi}} \times 100.00}{\text{Net Sales}_{\text{branch\_daily}}}, 2\right)$$
- **Penanganan Zero Total:** Jika total penjualan cabang pada hari tersebut nol, persentase disetel aman ke `0.00%`.

---

## 3. Penanganan Kasus Khusus & Edge Cases

### 1. Item Harga Nol (`price == 0.00` / Free Promo)
- **Kasus:** Produk roti atau kopi promosi kasir (misalnya *welcome bread*, bonus pembelian, atau *buy 1 get 1*).
- **Aturan:**
  - **TIDAK BOLEH DIHAPUS** karena merefleksikan pergerakan stok inventori riil.
  - Ditandai di Silver dengan `is_zero_price = True`.
  - Di Mart Harian dihitung dalam kolom `zero_price_item_count`.
  - Di Mart Menu dihitung dalam kolom `zero_price_qty`.
  - Berkontribusi terhadap `total_qty_sold` namun menambah `0.00` pada `net_sales`.

### 2. Menu Code Kosong & Ambigu
- **Kasus:** Transaksi kasir mencatat `Menu Code` bernilai string kosong `""` atau `NULL`.
- **Aturan:**
  - `menu_key` diturunkan secara deterministik dengan slugifikasi nama menu:
    $$\text{menu\_key} = \text{COALESCE}(\text{NULLIF}(\text{TRIM}(\text{menu\_code}), ''), \text{LOWER}(\text{REGEXP\_REPLACE}(\text{TRIM}(\text{menu}), '[\text{\textasciicircum a-zA-Z0-9}]+', '\_')))$$
  - Menu di-join ke `master_menu` menggunakan `UPPER(TRIM(menu_name))` pada view deduplikasi snapshot terbaru.
  - Ditambahkan kolom `is_master_matched` (Boolean) dan `master_match_status` (`'MATCHED'` / `'UNMATCHED'`).
  - Menu yang belum terdaftar di Master Menu tetap dipertahankan dan **tidak boleh hilang** dari Gold Mart.

### 3. Distribusi Jam Transaksi (`sales_hour`)
- **Kasus:** Penentuan jam transaksi penjualan.
- **Aturan:**
  - **DILARANG** menggunakan `kafka_timestamp`, `producer_sent_at`, atau `bronze_ingested_at`.
  - **WAJIB** menggunakan `sales_date_out` (timestamp struk dicetak/selesai kasir di zona waktu WIB).
  - Jam diekstrak sebagai integer $0 \le \text{sales\_hour} \le 23$.

### 4. Split Payment & Payment Mart
- **Kasus:** Pencatatan metode pembayaran (CASH, QRIS BRI, dll.).
- **Aturan:**
  - Dihitung dari level **Bill Grain** (`silver_sales_bills`), bukan dari level item untuk mencegah pelipatgandaan omzet.
  - Jika metode pembayaran tidak terdefinisi/kosong, dikategorikan sebagai `'UNKNOWN'`.

---

## 4. Hasil Rekonsiliasi Finansial Terverifikasi

Hasil audit pada dataset historis Toko Roti Pagi menunjukkan akurasi matematis 100%:

| Tanggal | Cabang | Total Bills | Total Qty | Gross Sales (IDR) | Total Discount (IDR) | Net Sales (IDR) | AOV (IDR) | Zero Price Qty |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2026-10-18** | TRP G-WALK | 145 | 730.00 | 16,365,000.00 | 0.00 | 16,365,000.00 | 112,862.07 | 21.00 |
| **2026-10-19** | TRP G-WALK | 44 | 168.00 | 3,745,000.00 | 0.00 | 3,745,000.00 | 85,113.64 | 6.00 |
| **TOTAL** | | **189** | **898.00** | **20,110,000.00** | **0.00** | **20,110,000.00** | **106,402.12** | **27.00** |

*Selisih finansial antar-mart: **Rp 0,00 (100% Rekonsiliasi Sempurna)**.*
