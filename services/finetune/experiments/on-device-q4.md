# On-device Q4 check

This note is the device check for a short reply from Qwen3.5-4B Q4 on an iPhone.
Jest does not measure it. The fake engine returns 40 ms and 12 tokens so the
status screen can render a number. That number is not this check.

## Not run on a handset

This session did not install a real Q4 pack on an iPhone and did not record
elapsed time or tokens per second from a handset. No latency figure below
should be treated as a measurement.

## Procedure

1. On the laptop, export the base pack with `services/finetune/export_on_device.py base --real`.
   `--real` quantizes base Qwen3.5-4B. It does not write the LLM container weights.
   CI uses `--fixture` and does not download the 4B weights.
2. Install the Encefalus iOS app on an iPhone and sign in with a free account.
3. On Model & Device Status, run Reinstall Model. The phone downloads
   `GET /api/models/on-device` and `GET /api/models/on-device/file` from the
   API Router and swaps the pack only after `sha256` matches.
4. Ask one short text question in Local AI Chat, with the base pack loaded
   and no image attached.
5. Read the engine's elapsed milliseconds and output token count for that reply.

Pass when elapsed time is at most 2 seconds and the rate is above 18 tokens
per second. Images and video are outside this check. The screen shows the
average only for replies of 64 output tokens or fewer.
