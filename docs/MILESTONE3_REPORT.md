# Milestone 3 — Lexical & Hybrid Retrieval

## Phase A audit

Đã đọc README, GUIDE, RULES, RUBRIC, BENCHMARK, SUBMISSION, starter README,
data schema, `src/dense.py`, `starter/baseline.py`, `starter/agentic.py`, tests,
dependencies và báo cáo/coverage/logs Milestone 2. Đối chiếu migration và
`starter/src/store.py` Day 06 bằng thao tác đọc, không thực thi migration.

GUIDE §2 cho phép TF-IDF và hybrid RRF; README/RUBRIC yêu cầu ít nhất ba
phương pháp, gồm dense vector store Day 06. Không bắt buộc BM25/rerank.
Starter có sẵn TF-IDF stdlib nên tái sử dụng trực tiếp, không thêm dependency.
Đây là ba phương pháp khác nhau, không chỉ thay top-k. Đánh giá dev chính thức
vẫn còn thiếu; smoke không đủ để tuyên bố hoàn thành toàn bộ rubric retrieval.

Contract giữ `search(query, *, filters, top_k) -> list[dict]`: id, text, source_id,
source, page, metadata, score; thêm rank, retrieval_method và provenance.
`strategy` tiếp tục là B (không để nhãn tfidf của baseline ghi đè provenance).
Physical page ánh xạ vào page; printed_page_label và citation giữ riêng.

Lần preflight đầu Milestone 2: chỉ còn báo cáo mã DATABASE_ERROR tổng quát,
không có SQLSTATE, exception class hoặc vị trí SQL. Phân loại được là lỗi
adapter/database trước retrieval; không đủ dữ kiện để quy cho kết nối, runtime,
quyền hoặc SQL. Lỗi LIKE trong coverage review là sự cố khác đã được sửa.
Không dùng lần chạy hiện tại để suy ngược nguyên nhân lỗi cũ.

## Kiến trúc và cấu hình

`DenseRetriever` hiện có → local query embedding E5-small 384 chiều → pgvector cosine.

`LexicalRetriever` → đọc read-only 264 chunks B → starter TF-IDF → cosine từ vựng.

`HybridRetriever` → hai retrievers trên → RRF → dedup và tie-break ID.

RRF k=60, candidate_k=20, equal weights; mỗi nhánh lấy max(candidate_k,top_k).
Các tham số được chọn trước smoke, không tuning trên evidence đã xem hoặc TEST.
Factory `create_retriever` chọn dense/lexical/hybrid, starter interfaces không đổi.
Chi tiết thuật toán, filter, tái lập và ví dụ dùng: [LEXICAL_HYBRID.md](LEXICAL_HYBRID.md).

## Rubric compliance checklist

- [x] Tái sử dụng model/vector store thật Day 06; chỉ snapshot B.
- [x] Có ba implementations: dense, TF-IDF, hybrid RRF.
- [x] Giữ IDs, metadata, nguồn, hai nhãn trang, provenance, score/rank.
- [x] Deterministic ranking, dedup, filter, lỗi không fallback giả.
- [x] Có unit tests và lệnh tái lập; không thêm dependency.
- [ ] So sánh chính thức trên cùng 17 câu dev, nhãn và metrics.
- [ ] Agent LLM thật, tool/context trace, grounded answer/citation/abstention.
- [ ] Hai cấu hình cải thiện được đánh giá trên dev và hai lỗi dev chính thức.
- [ ] Freeze cấu hình trước đánh giá 7 câu test và hoàn thiện submission.

Không tự gán điểm rubric. Các mục chưa hoàn tất thuộc milestone sau.

## Files và git diff

Files mới của Milestone 3:

- `src/retrieval.py`: snapshot loader, lexical, RRF và factory.
- `tests/test_retrieval.py`: 9 tests mới.
- `scripts/retrieval_smoke.py`: so sánh ba methods và kiểm tra integrity.
- `docs/LEXICAL_HYBRID.md`, `docs/MILESTONE3_REPORT.md`.
- `results/milestone3_unit_tests.log`, `results/milestone3_dense_regression.json`,
  `results/milestone3_retrieval_smoke.json`.

Không sửa starter, dense, dependencies, benchmark/gold hoặc files Day 06.
Working tree trước Milestone 3 đã có `.gitignore` modified cùng các files untracked
Milestone 1/2. `git diff --stat` mặc định chỉ hiện `.gitignore` (+1 dòng từ trước),
không bao gồm files mới chưa stage. Không git add, commit hoặc push.

## Giới hạn và việc còn thiếu trước Milestone 4

Corpus chỉ gồm 40 trang chọn; lexical khớp từ không suy luận ngữ nghĩa, không
tách từ tiếng Việt chuyên dụng. RRF có thể giữ lại lỗi ranking dense và bỏ sót
evidence ngoài candidate pool. Không có bảo đảm hybrid tốt hơn từng nhánh.
Similarity/RRF score không phải chất lượng trả lời hoặc xác suất đúng.
Index lexical nằm trong RAM, cố định trong lifetime; nếu dữ liệu bị thay đổi
bởi tiến trình ngoài thì cần khởi tạo lại và kiểm tra provenance.

Thống nhất phạm vi Milestone 4 khi review: nối LLM controller thật và formatter
hai số trang, xác định context/trace/error/cost policy. Còn phải xây/kiểm tra split
17 dev + 7 test, đánh giá dev ba phương pháp và hai cấu hình, phân tích hai lỗi dev,
chọn/freeze rồi mới chạy test trong milestone được duyệt. Các smoke queries và
evidence đã xem không thể dùng làm held-out test độc lập về sau.

## Kết quả kiểm thử và smoke

37/37 unit tests PASS (28 cũ + 9 mới); 11/11 integration checks Milestone 2 PASS.
Smoke ba methods: 9 query traces PASS, deterministic repeat và empty section PASS.
Fingerprint bốn bảng (gồm vectors) trước/sau giống nhau; 3903 files Day 06 không đổi.
Không LLM calls, không encode corpus, service/API cost 0 USD; chi phí compute local chưa đo.

Nguồn mọi hit: source_id `postgresql-16.16-a4`, source `https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf`.
Các trang dưới đây là physical / printed. Full text, metadata, context và component ranks có trong `results/milestone3_retrieval_smoke.json`.

### dense: What does a foreign key constraint require of values in the referencing table?

Latency 4519.32 ms; context 1870/2400 ký tự.

| Rank | Full chunk ID | Score | Physical / printed |
|---:|---|---:|---|
| 1 | `B:5eca19774a3207be84e60d022777b88b7e1a694d19f1a61464e559bac7f985a1` | 0.899458 | 109 / 71 |
| 2 | `B:cce353e962fc4ad207b117999efbfce3aa4f97242edba8c0999a3cc1161b053e` | 0.894646 | 106 / 68 |
| 3 | `B:8d705238424708d176ff653f64babe94fc932277c7f84a79d733f5f79ad47b92` | 0.894517 | 109 / 71 |

### dense: How does INSERT ON CONFLICT DO UPDATE handle a conflicting row?

Latency 917.98 ms; context 1759/2400 ký tự.

| Rank | Full chunk ID | Score | Physical / printed |
|---:|---|---:|---|
| 1 | `B:8a94f492356f15698408dc61dab6b6c5f87b32d9d1f60b2ca70e82b3ba6a5773` | 0.860316 | 114 / 76 |
| 2 | `B:da54a0cddc83ca17504e10c42d4da816f7266e07e93bf67d50065bb7d0fb9726` | 0.860122 | 102 / 64 |
| 3 | `B:6bccd282720b5c8fe523ba778c28f55ad6ee0352478e5311e337d90e56702455` | 0.860040 | 149 / 111 |

### dense: How does a CHECK constraint treat a null result?

Latency 881.15 ms; context 1857/2400 ký tự.

| Rank | Full chunk ID | Score | Physical / printed |
|---:|---|---:|---|
| 1 | `B:5b3f300cc4864fada187774e2557a17ab9c3b765b2ecc14734a97e90431e2771` | 0.898248 | 102 / 64 |
| 2 | `B:62a492e48171e5ddfc4bba91d1f7c2a96afe1d6d0181020f20d070e943892b52` | 0.892856 | 102 / 64 |
| 3 | `B:f619e42075c0d7b00078f8ff401575e3e173ec99da456a30899beb1450874af0` | 0.884652 | 103 / 65 |

### lexical: What does a foreign key constraint require of values in the referencing table?

Latency 1.46 ms; context 1709/2400 ký tự.

| Rank | Full chunk ID | Score | Physical / printed |
|---:|---|---:|---|
| 1 | `B:e579274f8d3d0bce7efc4250a53f86be0f0c659954cb4ff218ef28b234bf5915` | 0.373319 | 109 / 71 |
| 2 | `B:5da3f1e559edbc53a1ffaca2e9b5d87644eea1f1feca1db48a6f70425490ff19` | 0.368577 | 106 / 68 |
| 3 | `B:adef0380979d8bc0756eb7ffc1736531150ec53b8a8d9e30c161466ae9598a69` | 0.342706 | 109 / 71 |

### lexical: How does INSERT ON CONFLICT DO UPDATE handle a conflicting row?

Latency 1.21 ms; context 1805/2400 ký tự.

| Rank | Full chunk ID | Score | Physical / printed |
|---:|---|---:|---|
| 1 | `B:0b747a57c6fa2087b0c31e8c9375f420c908135dd2502a829b7de40e82083c36` | 0.196157 | 148 / 110 |
| 2 | `B:fca70a91803dece927b839920ac6e4161132cd8da452d0a198ec707a8187818a` | 0.190636 | 148 / 110 |
| 3 | `B:f651d27b56c39e4b2e8a85adbcf97744587623dad51b1717fb15683699eaead0` | 0.169324 | 150 / 112 |

### lexical: How does a CHECK constraint treat a null result?

Latency 1.16 ms; context 1848/2400 ký tự.

| Rank | Full chunk ID | Score | Physical / printed |
|---:|---|---:|---|
| 1 | `B:f619e42075c0d7b00078f8ff401575e3e173ec99da456a30899beb1450874af0` | 0.378028 | 103 / 65 |
| 2 | `B:0eb1f0653dacd4c6ec6755fc2dce7af63e2e4bd5c3fb8cafb47269de2728e15f` | 0.321460 | 103 / 65 |
| 3 | `B:62a492e48171e5ddfc4bba91d1f7c2a96afe1d6d0181020f20d070e943892b52` | 0.303001 | 102 / 64 |

### hybrid: What does a foreign key constraint require of values in the referencing table?

Latency 59.39 ms; context 1797/2400 ký tự.

| Rank | Full chunk ID | Score | Physical / printed |
|---:|---|---:|---|
| 1 | `B:5eca19774a3207be84e60d022777b88b7e1a694d19f1a61464e559bac7f985a1` | 0.031778 | 109 / 71 |
| 2 | `B:8d705238424708d176ff653f64babe94fc932277c7f84a79d733f5f79ad47b92` | 0.031498 | 109 / 71 |
| 3 | `B:e579274f8d3d0bce7efc4250a53f86be0f0c659954cb4ff218ef28b234bf5915` | 0.031099 | 109 / 71 |

### hybrid: How does INSERT ON CONFLICT DO UPDATE handle a conflicting row?

Latency 55.49 ms; context 1812/2400 ký tự.

| Rank | Full chunk ID | Score | Physical / printed |
|---:|---|---:|---|
| 1 | `B:0b747a57c6fa2087b0c31e8c9375f420c908135dd2502a829b7de40e82083c36` | 0.030679 | 148 / 110 |
| 2 | `B:8a94f492356f15698408dc61dab6b6c5f87b32d9d1f60b2ca70e82b3ba6a5773` | 0.030478 | 114 / 76 |
| 3 | `B:546326f5aad0123ca8f25d00dff5f3410e8d811d496aa348eb7b3097e5618593` | 0.030310 | 149 / 111 |

### hybrid: How does a CHECK constraint treat a null result?

Latency 40.61 ms; context 1848/2400 ký tự.

| Rank | Full chunk ID | Score | Physical / printed |
|---:|---|---:|---|
| 1 | `B:f619e42075c0d7b00078f8ff401575e3e173ec99da456a30899beb1450874af0` | 0.032266 | 103 / 65 |
| 2 | `B:62a492e48171e5ddfc4bba91d1f7c2a96afe1d6d0181020f20d070e943892b52` | 0.032002 | 102 / 64 |
| 3 | `B:0eb1f0653dacd4c6ec6755fc2dce7af63e2e4bd5c3fb8cafb47269de2728e15f` | 0.031754 | 103 / 65 |

Latency chỉ để chẩn đoán: dense chạy trước, hybrid dùng query cache đã warm, không phải so sánh hiệu năng công bằng hoặc benchmark chính thức.

## Đọc đối chiếu evidence sau retrieval

| Query | Dense top-3 | TF-IDF top-3 | Hybrid top-3 |
|---|---|---|---|
| Foreign key | Hạng 2 có ví dụ non-NULL phải xuất hiện ở bảng tham chiếu; hạng 1/3 nói về index | Hạng 2 có định nghĩa values phải match bảng khác; hạng 1/3 cung cấp điều kiện NULL/MATCH FULL | Hạng 1/2 thiên về index, hạng 3 chỉ có NULL/MATCH FULL; không giữ đoạn định nghĩa trực tiếp |
| ON CONFLICT DO UPDATE | Privileges, cross-row check và UPDATE thường; thiếu cơ chế conflict | INSERT/UPDATE thường; thiếu cơ chế conflict | INSERT, privileges và UPDATE thường; vẫn thiếu cơ chế conflict |
| CHECK/NULL | Có giải thích liên quan ở hạng 2 nhưng thiếu câu quy tắc TRUE hoặc NULL | Hạng 1/2 nhiều NOT NULL, hạng 3 giải thích liên quan; thiếu câu quy tắc đầy đủ | Tương tự lexical: liên quan nhưng thiếu câu quy tắc đầy đủ |

ON CONFLICT: inspection literal sau retrieval trên 264 chunks không trả chunk
chứa `on conflict`, phù hợp coverage review Milestone 2. Không suy ra vắng mặt
ngữ nghĩa trên toàn tài liệu PostgreSQL, và không gán nhãn unanswerable chính
thức từ top-3. Cả ba phương pháp không thể tạo evidence chưa có trong corpus.

CHECK/NULL: câu quy tắc rõ nằm trong chunk
`B:7c3322cc1c9ad1b3f2ae10b481e43270f2c37c80cf1dc0097b74e96bf361ce73`,
physical 102 / printed 64. Trace candidate của hybrid cho thấy chunk đó có dense
rank 10 (0.858824) và lexical rank 7 (0.253993); đã vào cả hai candidate pools
nhưng RRF score 1/70 + 1/67 = 0.029211 thấp hơn top-3. Đây là lỗi ranking,
không phải thiếu corpus hoặc candidate pool. Chunk chứa nhiều SQL ví dụ trước
câu quy tắc; TF-IDF ưu tiên đoạn lặp CHECK/NULL hơn, dense ưu tiên đoạn cùng chủ
đề. Đây là giả thuyết nguyên nhân, không phải kết quả ablation đã xác nhận.
Không điều chỉnh tokenizer, trọng số, candidates hay RRF sau khi xem evidence.

Budget context không làm mất các hit top-3 trong chín traces: tất cả ba IDs
đều được pack. Missing evidence ở đây xuất hiện trước bước context packing.
Hai trường hợp này là phân tích smoke, không thay thế hai lỗi dev chính thức;
không tính Hit@1, Evidence Hit@3, Context Evidence Rate hoặc answer metrics.
