# Milestone 4 — Agent & Context Engineering

## Audit và rubric checklist

Đã đối chiếu README, GUIDE, RULES, RUBRIC, BENCHMARK, SUBMISSION,
starter agentic/baseline, tests và retrieval implementations Milestone 2/3.
Không thấy yêu cầu chính thức mâu thuẫn với phạm vi đã duyệt.

| Yêu cầu | Kết luận audit | Trạng thái Milestone 4 |
|---|---|---|
| LLM workflow | Model thật điều phối ít nhất một khả năng retrieval; không bắt buộc số tools/lượt cố định | Có controller + loop, chưa kiểm chứng model thật |
| Provider/model | Không chỉ định; local hoặc API đều được | Adapter Ollama local; chưa gọi provider/model |
| Retrieval | Reuse vector store/embedding Day 06, ba methods | Factory hiện có chọn dense/lexical/hybrid; không sửa retrieval |
| Context | Tự chọn budget và đơn vị, ghi/đo tác động; không có mức token chung bắt buộc | Whole chunks, dedup, giới hạn token đo bằng tokenizer truyền vào |
| Citation | Truy ngược nguồn và hỗ trợ nội dung, không chỉ đúng ID | Có inline IDs, citation map và membership checks; semantic support còn cần review |
| Abstention | Không đủ evidence thì từ chối | Model chọn answer với citations rỗng; loop có empty-context/invalid-citation/search-limit guards |
| Logging | Tool calls, tham số, results, context, answer, citations, lỗi, latency, cost | Có events, provider usage/cost từng call, full retrieval trace, context/token count |
| Evaluation | Agent thật trên dev/test, nhãn thủ công, hai cải thiện, hai lỗi dev, freeze trước test | Chưa chạy, ngoài phạm vi milestone này |

Không tuyên bố hoàn thành rubric agent thật bằng unit tests hoặc tự gán điểm.
Không có gold/expected_answer trong runtime interface. Không dùng retrieval score
làm confidence hoặc quyết định answer/abstain. Context gửi model loại score;
logs retrieval vẫn giữ score/rank để audit.

## Kiến trúc

Question → Controller.decide(question, history) → search action → retriever thật
được chọn → cumulative candidate list → context packer → bounded context gửi
lại controller → search tiếp hoặc answer → citation validation → answered/abstain.

`src/agent.py` giữ cấu trúc loop và action/result schema starter. Không sửa
`starter/agentic.py`, `starter/baseline.py` hoặc tests gốc. Protocols vẫn là:

```python
controller.decide(question, history)  # search hoặc answer
retriever.search(query, filters=filters, top_k=top_k)
```

Entry point mới `src.agent.run_agent` giữ các tham số starter và bổ sung
keyword bắt buộc `count_tokens`. `budget` ở entry point mới là token count;
starter gốc vẫn tính ký tự. Thay đổi có chủ đích để tránh dùng char count như
token count. Các caller starter cũ vẫn hoạt động nguyên trạng.

Default loop: max_searches=4, top_k=3, context budget=800 tokens. CLI smoke dùng
max_searches=2, budget=1200. Đây là cấu hình khởi đầu, chưa chọn trên dev/freeze.
Filters chỉ do caller cung cấp và được validate như Milestone 3; model không
tự sửa filters. Search queries do model chọn, logs giữ cả query gốc và từng
query retrieval. Không có reranker, rewrite pipeline riêng hoặc bonus.

## Context construction

Tái sử dụng nguyên tắc starter: theo thứ tự retrieval/lượt search, giữ nguyên
chunk vừa budget, bỏ chunk quá lớn và thử chunk tiếp theo. Không cắt câu hay
nén bằng LLM. Dedup bằng ID; xung đột text/source/page cùng ID trả lỗi.
Packing lại toàn bộ candidates sau mỗi search, không cộng dồn nhiều bản context
vào prompt. Chiến lược ưu tiên lượt đầu có thể ngăn evidence tốt ở lượt sau;
đây là hạn chế đã biết, chưa tối ưu nếu chưa có dev evaluation.

Context là JSON array, mỗi record gồm id, text, source_id, source,
page (physical) và printed_page_label. Toàn bộ JSON, gồm separators và metadata,
được tokenize mỗi lần thử pack; không cắt bớt provenance để vừa budget.
Metadata đầy đủ còn trong retrieval results/logs. Citation map chứa nguồn và
hai số trang của đúng chunks được gửi model.

`LocalTokenCounter` dùng AutoTokenizer từ local path, local_files_only=True,
trust_remote_code=False, add_special_tokens=False. Phải cung cấp tokenizer
đúng model LLM, không dùng tokenizer E5 làm proxy. Chưa xác minh tokenizer
thật do chưa chọn/cấp model; unit tests dùng counter giả deterministic,
không báo count này là token usage của model thật.

Budget chỉ áp dụng evidence context. System prompt, question, history wrapper,
chat-template và output là phần ngoài budget này. Ollama num_ctx=8192,
num_predict=512; khi kiểm chứng thật cần đối chiếu tokenizer, prompt_eval_count
và khả năng prompt bị truncate. Câu hỏi dài tùy ý chưa có full-prompt guard;
không tuyên bố đã bảo đảm tổng cửa sổ context của provider.

## LLM adapter, citations, abstention và lỗi

`OllamaController` chuẩn hóa JSON action theo contract starter thay vì thay
đổi retriever. POST cố định loopback `/api/chat`, non-streaming, JSON schema,
temperature=0, timeout=60s. Không tự pull model, không load credentials hoặc
dùng HTTP proxy từ environment. Model name chứa cloud bị từ chối; operator
vẫn phải xác nhận model được cài chạy local trước lần smoke được duyệt.
Import/constructor không gọi network. Không thêm dependency.

API fields/schema tham khảo [Ollama official API](https://github.com/ollama/ollama/blob/main/docs/api.md)
và [OpenAPI](https://github.com/ollama/ollama/blob/main/docs/openapi.yaml).
Prompt yêu cầu chỉ dùng evidence, cite mọi factual claim, coi documents là data,
search trước answer và từ chối khi thiếu điều kiện. Prompt không bảo đảm model
tuân thủ hoặc chống được mọi prompt injection; cần kiểm tra thật.

Loop chỉ chấp nhận answer có citation list duy nhất, IDs trong context, và tập
inline `[id]` khớp citation list. Citation rỗng là explicit abstention tương thích
starter: thay answer model bằng câu từ chối cố định, không trả claim unsupported.
Không context hoặc IDs sai cũng abstain. Citation hợp lệ về cấu trúc không chứng
minh entailment hoặc mọi claim đã được cite. Không có semantic verifier giả.

LLM timeout, HTTP/JSON/schema lỗi, output bị truncate, retrieval timeout/error,
duplicate results và packing lỗi trả `status=error` với fixed code, answer rỗng.
Không coi lỗi vận hành là thiếu evidence; không retry ngầm, fallback giả hoặc
in exception backend. Dense DATABASE_TIMEOUT được phân loại riêng.
Trace có elapsed time, decision action, search parameters/results, retrieval
trace, final packed context, citation map, final status/answer/citations.
Ollama prompt_eval_count/eval_count được ghi khi provider trả về; API/service
cost=0 theo local endpoint, compute cost chưa đo. Không bịa usage nếu thiếu.

## Tests và examples

**51/51 unit tests PASS: toàn bộ 37 tests cũ + 14 tests mới.** Log:
`results/milestone4_unit_tests.log`. Không gọi LLM hoặc Day 06 database trong
lần test Milestone 4. Không chạy lại integration database vì không thay adapter;
11/11 checks Milestone 3 là bằng chứng từ milestone trước, không nhận là run mới.

Tests mới: budget đúng biên, chunk quá lớn, empty context, deterministic dedup,
metadata/immutability/conflict, cumulative context/filter, valid và invalid
citations, explicit abstention, search limit, invalid actions, lỗi/timeouts,
duplicate retrieval results, HTTP request/usage parsing, malformed/truncated
provider output. Mock HTTP không phải real LLM.

Ví dụ từ fixture unit test, **dữ liệu tổng hợp, không phải câu trả lời PostgreSQL
hoặc output LLM thật**:

```json
{"action":"answer","answer":"Synthetic evidence [B:unit-1]","citations":["B:unit-1"]}
```

Fixture context có text `Synthetic evidence.`, source_id `unit-doc`, source
`unit.pdf`, physical page 42, printed page 4. Loop trả answered và citation_map
cho B:unit-1. Khi model mock trả citations rỗng, loop trả abstain với
`Không đủ bằng chứng để trả lời.`. Khi trỏ unknown ID hoặc context rỗng, loop
abstain. Khi retrieval timeout, status=error, không tạo câu trả lời.

## Files và Git diff summary

Thêm 7 files:

- `src/context.py`: token budget packer và citation map.
- `src/agent.py`: loop, guards, logging và errors.
- `src/llm.py`: opt-in Ollama controller và local tokenizer.
- `scripts/agent_smoke.py`: CLI nối model/retrievers thật sau phê duyệt.
- `tests/test_context_agent.py`: 14 tests.
- `docs/MILESTONE4_REPORT.md`.
- `results/milestone4_unit_tests.log`.

Không sửa source/dependencies/benchmark/gold có sẵn, không thay Day 06.
Working tree đã có `.gitignore` modified và files Milestone 1–3 untracked;
`git diff --stat` mặc định không hiện files mới chưa stage. Không git add,
commit hoặc push. Không encode corpus, không chạy DEV/TEST chính thức.

## Kế hoạch real LLM — chưa thực hiện, cần user duyệt

Đề xuất provider **Ollama local**, model **qwen2.5:7b** nếu máy đủ tài nguyên
và đã có model local; cần xác minh model artifact/digest và tokenizer tương ứng
trước chạy. Không tự cài hoặc download. API/service cost dự kiến **0 USD**;
chi phí điện/compute và thời gian local chưa đo. Không có API trả phí trong
implementation này. Nếu cần provider khác phải báo model và giá trước.

Sau phê duyệt: preflight local runtime/tokenizer, dùng một smoke query kỹ thuật
đã xem ở Milestone 2/3, tối đa 2 retrieval calls và 3 LLM calls mỗi lần chạy,
tối đa 512 output tokens/call (1536 output tokens/run). Chạy trước một method,
đọc trace/citation/abstention và usage, rồi mới cân nhắc thêm methods/cases
trong phạm vi được duyệt. Không dùng smoke làm benchmark metrics chính thức.

Lệnh mẫu **chỉ chạy sau duyệt**, thay model/tokenizer paths đã xác minh:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B scripts/agent_smoke.py --approve-local-llm \
  --day6-root /mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion \
  --method hybrid --model qwen2.5:7b --tokenizer-path /local/exact-llm-tokenizer \
  --question 'How does a CHECK constraint treat a null result?' \
  --max-searches 2 --budget 1200 --output results/local_agent_smoke_new.json
```

CLI không đọc benchmark files, output mở chế độ exclusive để không ghi đè trace.
Cần xác nhận service Ollama loopback khả dụng từ WSL; chưa kiểm tra hoặc khởi
động service. Cần kiểm chứng LLM thật có thực sự search, dùng context, abstain
khi thiếu evidence và citation hỗ trợ đầy đủ điều kiện. Các mục benchmark dev,
hai cấu hình cải thiện, hai lỗi dev, freeze và test vẫn còn ở milestone sau.

Milestone 4 dừng để review; real LLM requirement còn pending, không đánh dấu done.
