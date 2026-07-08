# NKG Element ID Rules (Canonical)

Dokumen ini jadi aturan baku penamaan `elements[].id` agar konsisten untuk:
- ekstraksi NKG,
- validasi coverage,
- dan script highlighting di browser.

## 1) Kalau elemen punya DOM `id`

- `id` NKG harus **sama persis** dengan DOM id.
- `selector` harus **`#<id>`**.

Contoh:
- HTML: `<button id="btn_favorite">...`
- NKG:
  - `id`: `btn_favorite`
  - `selector`: `#btn_favorite`

## 2) Kalau elemen tidak punya DOM `id`

- Pakai format:
  - `id = <page_slug>__<deskripsi_singkat_snake_case>`
- `page_slug` diambil dari segmen terakhir `page_url`.
- `selector` harus selector yang stabil (hindari selector rapuh).

Contoh:
- `page_url`: `/customer/dashboard` → `page_slug = dashboard`
- NKG:
  - `id`: `dashboard__btn_apply_range`
  - `selector`: `.applyBtn`

## 3) Prioritas pemilihan selector

1. `#dom_id` (kalau ada id)
2. selector berbasis atribut yang stabil (mis. `a[onclick*="billing_info"]`)
3. kombinasi class/tag yang cukup spesifik

Hindari selector terlalu umum yang mudah tabrakan.

## 4) Kapan pakai prefix slug

- **Wajib** untuk elemen tanpa DOM id.
- Tidak perlu prefix untuk elemen yang sudah punya DOM id.

## 5) Apa yang boleh dihapus

- Elemen dekoratif murni / clone library (mis. banyak `select2-data-*`) boleh dihapus jika tidak dipakai untuk navigasi.
- Elemen yang actionable / target guidance jangan dihapus walau awalnya hidden.

## 6) Dampak ke highlighting

- Script highlight akan cari elemen berdasarkan:
  1) `id` DOM (`document.getElementById`), lalu fallback ke
  2) `selector` (`querySelector`).
- Jadi elemen generated id tetap bisa di-highlight selama `selector` valid.

## 7) Checklist cepat saat add/edit element

- [ ] `id` unik di dalam page
- [ ] Kalau ada DOM id → pakai id verbatim
- [ ] Kalau tanpa DOM id → pakai `<slug>__...`
- [ ] `selector` benar-benar menemukan elemen target
- [ ] `type` dan `desc` relevan (action-oriented)
