## Purpose

The on-device-model capability builds the Q4 packs the iPhone app
downloads. Free gets base Qwen3.5-4B. Premium gets that user's LoRA
adapter merged into the same model and quantized the same way. The
cloud container stays on the base weights.

## ADDED Requirements

### Requirement: Base pack is quantized Qwen3.5-4B

The export SHALL write a base pack for the free plan. The pack SHALL be
Qwen3.5-4B base weights quantized to Q4, without a LoRA adapter. Its
manifest `id` SHALL be `qwen3.5-4b-base-q4`, `family` SHALL be
`Qwen3.5-4B`, `tier` SHALL be `free`, `quantization` SHALL be `Q4`, and
`parameters` SHALL be `4.0B`. The manifest SHALL include `filename`,
`bytes`, and `sha256` of the file. The checksum SHALL match the file.

#### Scenario: Base manifest

- **GIVEN** base Qwen3.5-4B weights available to the export
- **WHEN** the base pack is built
- **THEN** the manifest id is `qwen3.5-4b-base-q4`, quantization is `Q4`, tier is `free`, and `sha256` matches the file

### Requirement: Premium pack merges the adapter then quantizes

The export SHALL write a premium pack for a user only when that user's
LoRA adapter is present at the Fine-Tune adapter directory for their
`user_id`. It SHALL merge that adapter into Qwen3.5-4B and then quantize
to Q4. The manifest `id` SHALL be `qwen3.5-4b-finetuned-q4`, `tier`
SHALL be `premium`, and the manifest SHALL include that `user_id`. One
user's pack SHALL NOT be readable as another user's pack.

#### Scenario: Adapter present

- **GIVEN** a LoRA adapter stored for user A
- **WHEN** the premium pack for user A is built
- **THEN** the manifest id is `qwen3.5-4b-finetuned-q4`, tier is `premium`, quantization is `Q4`, `user_id` is A, and the file is A's merged model at Q4

#### Scenario: Adapter absent

- **GIVEN** user B has no LoRA adapter
- **WHEN** the premium export runs for user B
- **THEN** it does not write a fine-tuned pack for B and the base pack is left as it was

#### Scenario: Users do not share a pack

- **GIVEN** a fine-tuned pack for user A and none for user B
- **WHEN** the packs are listed
- **THEN** A's file is tied to A and B has no fine-tuned file

### Requirement: The cloud container stays base

Building either pack SHALL NOT replace the weights served by the LLM
container. The container SHALL keep serving base Qwen3.5-4B.

#### Scenario: Export does not publish into the container

- **GIVEN** a successful premium pack build
- **WHEN** the export finishes
- **THEN** the LLM container's loaded weights are still the base model

### Requirement: Manifest is enough for the app to verify a download

Each pack directory SHALL contain the weight file and a manifest the
router can return as JSON. `sha256` SHALL be lowercase hex of the weight
file. A manifest whose checksum does not match the file SHALL be treated
as not ready.

#### Scenario: Checksum mismatch

- **GIVEN** a manifest whose `sha256` does not match the weight file
- **WHEN** the pack is validated
- **THEN** the pack is not ready for download

### Requirement: The phone does not download from the Fine-Tune Service

The export SHALL read the LoRA adapter from the directory the Fine-Tune
Service already writes. It SHALL NOT add a download route on port 8004.
The phone SHALL receive the pack only through the API Router.

#### Scenario: Adapter is an input, not a download

- **GIVEN** a completed LoRA job that wrote an adapter
- **WHEN** the premium pack is built
- **THEN** the export reads that adapter locally and port 8004 does not stream the Q4 file
