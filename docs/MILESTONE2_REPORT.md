# Milestone 2 — PostgreSQL Adapter & Dense Retrieval Smoke Test

Đã hoàn tất bằng `.venv` Day 07, WSL CPython 3.12.3. Đây là kiểm thử tích hợp, chưa phải benchmark chất lượng trả lời.

## Kiến trúc

Đã đối chiếu README, GUIDE, RULES, RUBRIC, BENCHMARK, SUBMISSION và contract `Retriever.search(query, *, filters, top_k)`. Không có xung đột với phạm vi đã duyệt. Không sửa starter hoặc 15 tests gốc.

`src/dense.py` tái sử dụng MyEmbedder Day 06: kiểm tra SHA-256 model artifacts, revision, library/runtime profile, prefix `query: `, 384 chiều, normalize và giới hạn 512 tokens. Subclass chặn document encoding và ghi cache Day 06. Query lặp dùng cache RAM. Model chỉ nạp local, offline.

Adapter dùng REPEATABLE READ READ ONLY; connect timeout 5 giây, statement timeout mặc định 10 giây; rollback/close. Mỗi search xác minh snapshot B complete, 264 chunks, 40 trang, profile và hashes. SQL dùng bind parameters, cosine similarity, top-k và chunk ID tie-break. Chỉ hỗ trợ filter section equality; filter lạ bị từ chối.

- Dataset: `day06-postgresql`
- Model: `intfloat/multilingual-e5-small`
- Revision: `fd1525a9fd15316a2d503bf26ab031a61d056e98`
- Profile: `528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651`
- Snapshot B: `c7d9d92e6695709595d044e5a5a09bb8f91826fb692474c7b1806751015ec1e0`

Mapping: chunk_id→id, document_id→source_id, physical_page→page. Giữ text, metadata, source, printed_page_label, section, offsets, page ID và profile/snapshot/hash provenance. Structured citation tách physical/printed page. Context budget thuộc lớp context; pack_dense_context tái sử dụng logic starter với hai nhãn trang rõ ràng. Smoke dùng 2400 ký tự.

## Kiểm thử

| Kiểm tra | Kết quả |
|---|---|
| Baseline gốc | 15/15 PASS |
| Unit tests mới | 13/13 PASS |
| Tổng unit tests sau cài runtime | 28/28 PASS |
| Live integration/smoke | 11/11 PASS |
| pip check | PASS |
| Hash-locked offline install dry-run | PASS |
| Fingerprint bốn bảng trước/sau | Giống nhau |
| Hash file Day 06 sau smoke | 3903/3903 không đổi |

Live checks gồm profile/snapshot/read-only, empty query, invalid config, model checksum sai, snapshot mismatch thật, timeout thật, SQL error thật được lọc thông tin, empty result, ba query top-3/context/metadata, cache/top_k=1 và fingerprint toàn bộ bảng. Log/trace nằm trong results/milestone2_*; trace có text, metadata, scores, context, latency và service cost. Dependency lock có 37 packages và hashes.

Lần thử sớm bằng runtime Stage 4 gặp DATABASE_ERROR trước retrieval, chưa xác định nguyên nhân. SELECT chẩn đoán và toàn bộ lần chạy Day 07 sau đó thành công. SELECT coverage review ban đầu sai định dạng tham số LIKE đã được sửa thành bind parameter; không thay adapter hoặc ranking. Không thay lỗi bằng mock.

## Đọc đối chiếu smoke

1. Foreign key: hạng 2 có ví dụ cho thấy giá trị khác NULL phải xuất hiện trong bảng được tham chiếu. Hạng 1/3 thiên về index.
2. ON CONFLICT DO UPDATE: top-3 không có evidence trả lời. Kiểm tra literal sau smoke trên 264 chunks B không tìm thấy cụm ON CONFLICT; không suy ra chắc chắn vắng mặt ngữ nghĩa.
3. CHECK/NULL: hạng 2 có nội dung liên quan nhưng context thiếu câu nêu đầy đủ CHECK được thỏa khi TRUE hoặc NULL. Kiểm tra sau smoke tìm câu đó tại `B:7c3322cc1c9ad1b3f2ae10b481e43270f2c37c80cf1dc0097b74e96bf361ce73`, physical 102 / printed 64; chunk này không có trong top-3.

Coverage review ở results/milestone2_coverage_review.json thực hiện sau retrieval, không đưa vào query/filter/ranking hoặc dùng tuning. Query được viết trực tiếp trong script; không mở benchmark/gold, không tạo benchmark labels. Đây chưa phải phân tích hai lỗi dev chính thức. Không coi smoke queries/nội dung đã xem là held-out test độc lập sau này.

## Tính toàn vẹn và bảo mật

Fingerprint trước/sau giống nhau: chunks 510 rows (gồm vectors), embedding_profiles 1, strategy_snapshots 2, schema_migrations 1. Fingerprint đọc A/B chỉ để kiểm tra; retrieval chỉ dùng B. Kiểm tra 3903 file Day 06 sau smoke không phát hiện thay đổi. Danh mục loại trừ runtime environments/caches/bytecode/Git internals ghi rõ trong results/milestone2_day6_integrity.json. Manifest chi tiết ở ignored data/local.

Không DDL/DML, migration, ingestion, encode corpus, index mới, LLM API, official benchmark, commit hoặc push. Service/API cost = 0 USD; không khẳng định chi phí tính toán local bằng 0. Toàn smoke gồm cold import/model init: 259.23 giây; artifact verification 16.51 giây; model load sau import 11.90 giây. Không dùng các số này làm benchmark so sánh.

Sự cố Milestone 1: password PostgreSQL local dạng literal trong Compose xuất hiện trong output công cụ. Không có API key hoặc toàn bộ .env được in trong sự cố đó. Khuyến nghị người dùng tự rotate password, cập nhật cấu hình liên quan và hạn chế chia sẻ transcript. Không tự đổi credential hoặc xóa lịch sử. Kết quả quét file Milestone 2 so với password thật, không in giá trị, ở results/milestone2_secret_scan.json.

## Rubric và rủi ro

- Đã có bằng chứng kết nối Day 06, model/vector thật, nguồn/trang, dense retrieval, top-k, context budget, trace latency/cost và tái lập. Không tự gán điểm rubric.
- Chưa đủ ba retrieval methods; chưa có lexical/hybrid, LLM controller, grounded answers/abstention, benchmark 17 dev/7 test, hai cấu hình cải thiện, phân tích lỗi dev hoặc freeze/test chính thức.
- Dense-only có kết quả nhiễu/thiếu evidence. Corpus chỉ có 40 trang chọn của một tài liệu.
- Runtime phụ thuộc checkout/model local Day 06 và Linux CPython/profile đã pin; cold start trên ổ Windows/WSL chậm.
- Role day6 có quyền rộng hơn nhu cầu; milestone chỉ dùng read-only transaction, không sửa grants.
- Starter run_agent chưa tự dùng pack_dense_context; milestone agent cần nối formatter này để model thấy cả hai số trang.

## Files và Git diff summary

Tracked file sửa: .gitignore (+1 dòng ignore data/local). Files mới:

- requirements-dense.txt; requirements-dense.lock
- src/__init__.py; src/dense.py
- scripts/prepare_dense_runtime.py; scripts/dense_smoke.py; scripts/check_day6_files.py
- tests/test_dense.py
- docs/DENSE_RETRIEVAL.md; docs/MILESTONE2_REPORT.md
- results/milestone2_unit_tests.log; results/milestone2_dense_smoke.json; results/milestone2_day6_integrity.json
- results/milestone2_runtime.json; results/milestone2_install_check.log; results/milestone2_secret_scan.json; results/milestone2_coverage_review.json

Files mới chưa git add; git diff --stat mặc định chỉ thấy .gitignore. AGENTS.md và results/baseline_tests.log đã có từ trước. Local wheelhouse/manifests/.venv bị ignore. Hướng dẫn chạy ở docs/DENSE_RETRIEVAL.md. Milestone 2 dừng chờ review.

## Dense smoke — query và top-3 đầy đủ

Mọi hit có source_id postgresql-16.16-a4, metadata version 16.16, strategy B và profile/snapshot nêu trên. Score là cosine similarity, không phải xác suất trả lời đúng.

Nguồn: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

### Query 1

What does a foreign key constraint require of values in the referencing table?

Search latency: 8428.41 ms; context 1870 / 2400 chars.

| Rank | Full chunk ID | Score | Physical page | Printed page | Section |
|---:|---|---:|---:|---|---|
| 1 | `B:5eca19774a3207be84e60d022777b88b7e1a694d19f1a61464e559bac7f985a1` | 0.899458 | 109 | 71 | Data Definition |
| 2 | `B:cce353e962fc4ad207b117999efbfce3aa4f97242edba8c0999a3cc1161b053e` | 0.894646 | 106 | 68 | Data Definition |
| 3 | `B:8d705238424708d176ff653f64babe94fc932277c7f84a79d733f5f79ad47b92` | 0.894517 | 109 | 71 | Data Definition |

### Query 2

How does INSERT ON CONFLICT DO UPDATE handle a conflicting row?

Search latency: 1695.92 ms; context 1759 / 2400 chars.

| Rank | Full chunk ID | Score | Physical page | Printed page | Section |
|---:|---|---:|---:|---|---|
| 1 | `B:8a94f492356f15698408dc61dab6b6c5f87b32d9d1f60b2ca70e82b3ba6a5773` | 0.860316 | 114 | 76 | Data Definition |
| 2 | `B:da54a0cddc83ca17504e10c42d4da816f7266e07e93bf67d50065bb7d0fb9726` | 0.860122 | 102 | 64 | Data Definition |
| 3 | `B:6bccd282720b5c8fe523ba778c28f55ad6ee0352478e5311e337d90e56702455` | 0.860040 | 149 | 111 | Data Manipulation |

### Query 3

How does a CHECK constraint treat a null result?

Search latency: 510.97 ms; context 1857 / 2400 chars.

| Rank | Full chunk ID | Score | Physical page | Printed page | Section |
|---:|---|---:|---:|---|---|
| 1 | `B:5b3f300cc4864fada187774e2557a17ab9c3b765b2ecc14734a97e90431e2771` | 0.898248 | 102 | 64 | Data Definition |
| 2 | `B:62a492e48171e5ddfc4bba91d1f7c2a96afe1d6d0181020f20d070e943892b52` | 0.892856 | 102 | 64 | Data Definition |
| 3 | `B:f619e42075c0d7b00078f8ff401575e3e173ec99da456a30899beb1450874af0` | 0.884652 | 103 | 65 | Data Definition |
