# Milestone 4B — Real LLM validation preflight

Ngày kiểm tra: 2026-11-16 (Asia/Bangkok).

**Preflight NOT READY; Phase B không chạy.** Tuân thủ yêu cầu dừng khi chưa có
model phù hợp, không tải model, không inference/cloud API. Chưa hoàn thành
real LLM validation, không coi unit tests là bằng chứng model thật.

## Đối chiếu repository và adapter

README yêu cầu agent dùng model thật để truy xuất. GUIDE yêu cầu context,
citations, abstention và trace. RUBRIC cho phép model local; không bắt buộc
provider hoặc model cụ thể. BENCHMARK yêu cầu đọc citation để kiểm tra semantic
support; chỉ khớp ID là chưa đủ. Không chạy benchmark DEV/TEST ở milestone này.

Đã đọc `src/llm.py` và `scripts/agent_smoke.py`. Static API review phù hợp
[Ollama official API](https://github.com/ollama/ollama/blob/main/docs/api.md):
POST /api/chat, messages, JSON-schema format, stream=false, options và usage
prompt_eval_count/eval_count. **Chưa xác minh runtime compatibility** do server
không hoạt động; client version không chứng minh server hỗ trợ request.

## Environment/hardware

| Kiểm tra | Kết quả thực tế |
|---|---|
| Ollama CLI WSL | Có: /usr/local/bin/ollama, client 0.40.16 |
| Service | Không có tiến trình Ollama; systemd inactive, FragmentPath rỗng |
| WSL loopback /api/version và /api/tags | Connection refused |
| Windows loopback /api/version | Không khả dụng |
| Windows install mặc định | Không tìm thấy ở LocalAppData/Programs/Ollama hoặc Program Files/Ollama |
| Model inventory qua API | Không lấy được; không báo giả danh sách rỗng |
| Model manifests mặc định WSL | Không tìm thấy ở user lyle, /usr/share/ollama, /root và các home đã kiểm tra |
| OLLAMA_MODELS của user WSL | Không đặt |
| Qwen tokenizer trong HF cache mặc định WSL user | Không tìm thấy |
| Windows RAM | TotalVisibleMemorySize 16,625,256 KiB (~15.86 GiB), free 3,105,560 KiB (~2.96 GiB) tại thời điểm đo |
| WSL RAM/swap | 7,870 MiB total, 6,870 MiB available; swap 2,048 MiB, used 0 |
| GPU | Intel UHD Graphics 620; Windows báo AdapterRAM 1 GiB |
| GPU acceleration | Có /dev/dxg; không thấy nvidia-smi; chưa xác minh backend Ollama hỗ trợ GPU này |

Không thể loại trừ model ở đường dẫn custom chưa được cung cấp. Windows
AdapterRAM của GPU tích hợp không phải phép đo dedicated VRAM hoặc khả năng
offload Ollama. Không cộng RAM host và WSL vì cùng tài nguyên vật lý.

Theo [Ollama qwen2.5:7b](https://ollama.com/library/qwen2.5:7b), artifact Q4_K_M
khoảng 4.7 GB; đây là kích thước artifact, không phải tổng RAM inference.
KV cache num_ctx=8192, runtime và dense embedding còn cần bộ nhớ. Với headroom
hiện tại không thể xác nhận 7B chạy ổn định; CPU fallback cũng chưa kiểm chứng.
Không tự đổi sang model nhỏ, giảm context hoặc chạy tải thử khi thiếu model.

## Phase B và grounding

| Case | Trạng thái | Model | LLM calls | Retrieval calls | Citations / grounding |
|---|---|---|---:|---:|---|
| Có evidence | NOT RUN — preflight failed | Không có | 0 | 0 | Chưa đánh giá |
| Không có evidence | NOT RUN — preflight failed | Không có | 0 | 0 | Chưa đánh giá |

Không có answered/abstain/error của agent để báo cáo: chưa gọi agent. Lỗi
connection ở đây là lỗi preflight, không phải kết quả abstention. Latency
inference và token usage không có; không điền 0 như dữ liệu đo. Không tạo
answers, citations hoặc model traces giả. Service/API cost phát sinh: 0 USD.

## Chuẩn bị tối thiểu trước khi tiếp tục

Không cần cài lại CLI WSL chỉ vì service chưa chạy. Trước tiên khởi động server
bằng CLI hiện có trong WSL và kiểm tra inventory:

```bash
ollama serve
# Trong terminal WSL khác:
ollama list
curl --noproxy '*' http://127.0.0.1:11434/api/version
curl --noproxy '*' http://127.0.0.1:11434/api/tags
```

Không dùng systemctl start khi chưa có service unit. `ollama serve` chạy
foreground cho đến khi dừng. Agent adapter dùng loopback WSL, nên server cần
khả dụng ở loopback đó. Không cần mở port ra mạng ngoài.

Nếu inventory không có model phù hợp, bước download cần được duyệt riêng:

```bash
# CHỈ SAU KHI ĐƯỢC DUYỆT TẢI MODEL, chưa thực hiện:
ollama pull qwen2.5:7b
```

Cần chuẩn bị đúng tokenizer local tương ứng Qwen2.5-7B-Instruct cho
`LocalTokenCounter`; không dùng E5 tokenizer. Model GGUF trong Ollama không tự
đáp ứng AutoTokenizer local path của adapter hiện tại. Không tự tải tokenizer
trong lần kiểm tra này. Nếu có sẵn model/tokenizer ở store custom, cung cấp
đường dẫn thay cho download mới.

Sau khi có service/model/tokenizer: kiểm tra digest, model local không cloud,
memory headroom/backend, API JSON schema và token counts rồi mới chạy hai cases.
Giữ tối đa 2 retrieval calls/3 LLM calls mỗi run, timeout 60s, max output 512
tokens/call theo adapter hiện tại; không retry tự động. Chọn câu evidence sau
kiểm tra corpus và câu thiếu evidence sau kiểm tra coverage, không suy ra absence
chỉ từ top-k. Đọc từng claim/citation, báo structural validity và semantic
support riêng. Không dùng các smoke cases đã xem làm held-out TEST về sau.

## Regression, files và phạm vi còn thiếu

51/51 unit tests PASS sau preflight (2.281 giây); toàn bộ calls LLM trong unit
tests là mocks. Log `results/milestone4b_unit_tests.log`.

Files thêm: báo cáo này, `results/milestone4b_preflight.json`,
`results/milestone4b_unit_tests.log`. Không sửa code, dependencies, Day 06,
database, corpus hoặc vectors. Không encode, DEV/TEST benchmark, tuning, commit
hoặc push. Không khởi động service hoặc cài/pull model trong lần này.

Rubric còn thiếu: real model điều phối retrieval được kiểm chứng; grounding,
citation và abstention thật; đánh giá dev ba methods/hai cấu hình; phân tích
hai lỗi dev; freeze rồi test và hoàn thiện submission. Không mở Milestone 5.

Evidence máy đọc được: [preflight JSON](../results/milestone4b_preflight.json).
Milestone 4B dừng ở Phase A vì điều kiện môi trường chưa đạt.
