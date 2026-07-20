# OCR Candidate Research and Execution Decisions

Research reviewed on 2026-07-14. The benchmark unit is an isolated 512-by-512
handwritten prescription word crop, not a full prescription page. “Best OCR” is
therefore not a single universal model: page parsers, scene-text recognizers,
handwriting recognizers, and commercial document APIs solve different input
problems.

## Decision Rules

- Prefer a handwriting-recognition checkpoint for word-level handwriting.
- Use a recognition-only model when text detection has already been done by the
  dataset.
- Test preprocessing and model size on official training rows only.
- Promote a configuration only after it repeats its gain on a disjoint train
  validation subset.
- Keep the official test split untouched until model/configuration selection is
  frozen.
- Report a provider as blocked, not as zero accuracy, when credentials, billing,
  hardware, privacy approval, or model access are missing.
- Never treat a full-page model and a word-crop recognizer as equivalent systems.

## Candidate Matrix

| System | Intended input and evidence | Local fit on Apple M4 Max | Access / license consideration | Data 3 decision |
| --- | --- | --- | --- | --- |
| PaddleOCR PP-OCRv6 medium recognition | Current PaddleOCR release includes a compact English/Latin recognition model; official release notes report PP-OCRv6 in June 2026. [Official repository](https://github.com/PaddlePaddle/PaddleOCR) | Runs locally on CPU; recognition-only mode matches isolated word crops. | Open-source PaddleOCR repository; model is downloadable without sending images to a provider. | Full baseline completed. Raw plus crop/contrast variants receive paired train-only screening and validation. |
| Microsoft TrOCR Base Handwritten | Transformer OCR checkpoint fine-tuned on IAM handwriting. [Official model card](https://huggingface.co/microsoft/trocr-base-handwritten), [official TrOCR repository](https://github.com/microsoft/unilm/tree/master/trocr) | Runs locally through Transformers; MPS works with normal macOS hardware access. | Public model checkpoint. | Full baseline completed; preprocessing variants screened and validated. |
| Microsoft TrOCR Large Handwritten | Larger handwriting-specialized TrOCR checkpoint, also fine-tuned on IAM. [Official model card](https://huggingface.co/microsoft/trocr-large-handwritten) | Expected to fit 36 GB unified memory, but latency and MPS behavior must be measured rather than assumed. | Public model checkpoint; multi-gigabyte local download. | Download, smoke test, then locked 600-row screening against Base and Paddle. |
| GOT-OCR 2.0 | General OCR model supporting plain/formatted OCR and multi-page inputs. [Transformers documentation](https://huggingface.co/docs/transformers/model_doc/got_ocr2), [paper](https://arxiv.org/abs/2409.01704) | Transformers supports it, but it is a general OCR VLM rather than a handwriting-specialized recognizer. | Public checkpoint; substantially heavier than compact recognition models. | Bounded compatibility pilot only. Promote only if word-crop output is stable and screening quality is competitive. |
| Qwen2.5-VL 3B | General vision-language model with document and structured-image understanding. [Technical report](https://arxiv.org/abs/2502.13923), [official announcement](https://qwenlm.github.io/blog/qwen2.5-vl/) | A 3B model may fit unified memory, but generation latency and OCR formatting make it a secondary candidate. | Public model; checkpoint size and runtime are materially larger. | Small compatibility pilot after handwriting-specialized models. It is not assumed to be better because it is larger. |
| DeepSeek-OCR / DeepSeek-OCR2 | Document OCR and visual compression architecture. [Official repository](https://github.com/deepseek-ai/DeepSeek-OCR), [paper](https://arxiv.org/abs/2510.18234) | Official instructions target CUDA 11.8 and PyTorch 2.6. The available machine has Apple MPS, not CUDA. | Public code/model, but official local runtime is hardware-incompatible here. | Blocked for a valid local benchmark unless a supported CUDA environment is supplied. Do not invent an Apple result. |
| PaddleOCR-VL 1.6 | Page/document parsing pipeline with layout and element recognition. [Official repository and release notes](https://github.com/PaddlePaddle/PaddleOCR), [pipeline documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.md) | Can be investigated locally, but a page parser adds stages that isolated word crops do not require. | Open-source local pipeline; heavier than PP-OCR recognition. | Compatibility pilot only; keep separate from the primary word-recognition ranking. |
| Donut medical-prescription checkpoint | End-to-end document model trained for full prescription images. [Model card](https://huggingface.co/chinmays18/medical-prescription-ocr) | Runs locally, but the model expects page structure and task prompts, while RxHandBD supplies one word. | Public checkpoint. | A 30-image pilot was completed: 0% exact and very high latency. Excluded from the primary ranking as an input mismatch, not hidden. |
| Medical TrOCR checkpoint (`khedim`) | Prescription-specific TrOCR checkpoint. [Model card](https://huggingface.co/khedim/Medical-Prescription-OCR) | Architecture is relevant and compact. | Gated model; access conditions must be accepted by an authenticated Hugging Face account. | Blocked until authorized model access is available. |
| Google Cloud Vision handwriting | Managed OCR explicitly supporting handwriting and handwriting language hints. [Official documentation](https://cloud.google.com/vision/docs/handwriting) | No local inference; network API. | Requires project credentials, billing, and approval to transmit prescription images. | Provider adapter can be implemented, but execution remains blocked without credentials and privacy approval. |
| Azure Vision Read | Managed Read OCR supports printed and handwritten text. [Official documentation](https://learn.microsoft.com/azure/ai-services/computer-vision/concept-ocr) | No local inference; network API. | Requires endpoint/key, billing, and privacy approval. | Same-image provider benchmark is blocked until those requirements are supplied. |
| Mistral OCR 4 | Current managed document OCR model. [Official model card](https://docs.mistral.ai/models/model-cards/ocr-4-0), [OCR API documentation](https://docs.mistral.ai/capabilities/document_ai/basic_ocr/) | No local inference; document API rather than a crop-specialized recognizer. | Requires API credentials and transmits images to a provider. | Candidate for a separately approved commercial comparison, not silently assigned a score. |

## Why Domain Fine-Tuning Is a Separate Experiment

RxHandBD provides an official training split, so a fine-tuned handwriting model
is a legitimate experiment. It is not directly comparable to zero-shot systems
unless the report makes training exposure explicit. The final dataset audit found
that 691 of 1,111 reliable official-test rows have labels seen somewhere in
training, while 420 use unseen labels. A fine-tuned model must therefore report
at least:

- official-test exact accuracy and character error rate;
- seen-label official-test accuracy;
- unseen-label official-test accuracy;
- validation checkpoint selection performed without official-test feedback;
- the exact train rows, seed, optimizer, epochs, and checkpoint hash.

This split distinguishes learning handwriting features from memorizing the finite
medicine vocabulary.

## Final Executed Outcome

1. PP-OCRv6 crop+autocontrast improved from 25.30% to 27.40% exact on the
   disjoint 1,000-row validation set.
2. TrOCR Base autocontrast improved CER but not exact accuracy materially on that
   validation set: 23.20% exact and 0.3605 CER.
3. TrOCR Large reached 27.60% exact and 0.2931 CER on the same validation set.
4. GOT-OCR2 completed the locked 600-row screen at 23.33% exact, 0.3390 CER,
   and about 744 ms/image; it was not promoted.
5. Domain-fine-tuned TrOCR Base reached 56.10% exact and 0.1509 CER on the
   disjoint validation set, so it alone passed the final five-point/unique-gain
   promotion rule.
6. The frozen promoted checkpoint completed all 5,577 OCR-eligible images with
   zero runtime errors. On 5,568 reliable scored rows it reached 60.65% exact and
   0.1492 CER.
7. On the untouched 1,111-row official test it reached 45.36% exact. Seen-label
   accuracy was 52.97%; unseen-label accuracy was 32.86%, compared with 28.81%
   for zero-shot PaddleOCR on the same reliable unseen rows.
8. Search-recovery and end-to-end metrics were regenerated from five complete OCR
   configurations. No official-test result influenced model selection.
