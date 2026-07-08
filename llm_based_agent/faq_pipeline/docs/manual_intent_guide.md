# Running the FAQ Ingestion Pipeline with Manual Custom Intents

This guide walks you through loading and running the FAQ ingestion pipeline with your own custom FAQ intents (such as [tambah_jari.json](file:///c:/Documents/Kuliah/Skripsi/in-app-navigational-agent/llm_based_agent/faq_pipeline/manual_custom_intents/tambah_jari.json)).

---

## 1. Pipeline Improvements Made

To support custom manual intents seamlessly without risk of overwriting your core pipeline results, we have made the following improvements to [pipeline.py](file:///c:/Documents/Kuliah/Skripsi/in-app-navigational-agent/llm_based_agent/faq_pipeline/pipeline.py):

1. **`--faq-file <path>`**: Specifying a custom JSON file to load (instead of defaulting to `help_center_faq.json`).
2. **`--output-dir <path>`**: Specifying a custom output directory to isolate results (instead of defaulting to `faq_pipeline/output`).
3. **Robustness Fix**: Initialized `result_file = None` inside the main orchestration loop to eliminate potential `UnboundLocalError` when running without manual loading.

---

## 2. Command Reference

All commands must be executed from the `llm_based_agent` directory using the Conda environment's Python (`..\.conda\python.exe`).

### Option A: Isolated Dry Run (Verify Loading & DB Connection)
To verify that the custom file is loaded correctly and that the Neo4j database is accessible, without making any LLM API requests:
```powershell
..\.conda\python.exe -m faq_pipeline.pipeline --faq-file faq_pipeline/manual_custom_intents/tambah_jari.json --output-dir faq_pipeline/output_manual --dry-run
```

### Option B: Isolated Standard Run (Phases 1-4)
To process the intent through all phases (Classification, Drafting, Element Matching, Paraphrase/Embedding Generation) and save the files in an isolated folder (`output_manual/`) for review, without writing to Neo4j:
```powershell
..\.conda\python.exe -m faq_pipeline.pipeline --faq-file faq_pipeline/manual_custom_intents/tambah_jari.json --output-dir faq_pipeline/output_manual
```

### Option C: Isolated & Push to Neo4j (Phases 1-5)
To process the intent and **push it directly into your local Neo4j database**:
```powershell
..\.conda\python.exe -m faq_pipeline.pipeline --faq-file faq_pipeline/manual_custom_intents/tambah_jari.json --output-dir faq_pipeline/output_manual --push
```

### Option D: Merge and Append to Main `final_intents.json`
If you want to merge this custom intent directly into your main `final_intents.json` file along with the other 110 pre-existing intents, use the default output directory and pass `--resume`:
```powershell
..\.conda\python.exe -m faq_pipeline.pipeline --faq-file faq_pipeline/manual_custom_intents/tambah_jari.json --resume
```
> [!NOTE]
> Since `tambah_sidik_jari_melalui_web_1` does not yet exist in your main `final_intents.json`, `--resume` will keep the 110 existing intents intact, process this new custom intent, and write all 111 intents into the file. Add `--push` to this command if you also want it written to Neo4j.

### Option E: Push Pre-Processed JSON Directly to Neo4j (Fastest)
If you have already run the pipeline and have generated the `final_intents.json` in your custom output directory, you can push the results directly to Neo4j in milliseconds (avoiding any re-running of LLMs or embedding generations) by running:
```powershell
..\.conda\python.exe -m faq_pipeline.push_json faq_pipeline/output_manual/final_intents.json
```

---

## 3. Custom Intent JSON Structure

Your JSON file must contain a `"faq"` array of objects matching the `FAQEntry` model schema:

```json
{
    "faq": [
        {
            "faq_id": "tambah_sidik_jari_melalui_web_1",
            "question": "Menambahkan sidik jari karyawan melalui web",
            "answer": "1. Masuk to halaman karyawan. 2. Lihat tabel karyawan dan klik karyawan yang ingin ditambahkan sidik jari. 3. Klik tombol yang kalau diklik akan memunculkan (mentrigger) Info Umum, Turunkan Data ke mesin absensi, dan Tambah Verifikasi. 4. Klik Tambah Verifikasi dan ikuti panduan dari sistem.",
            "category": "karyawan",
            "subcategory": "daftar_karyawan",
            "subsubcategory": "",
            "source": "manual"
        }
    ]
}
```

---

## 4. Verification Check

To confirm that the database is running correctly and view your current nodes count, run:
```powershell
..\.conda\python.exe faq_pipeline/verify_db.py
```
