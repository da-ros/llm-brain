## Purpose

The mobile-app capability is the Encefalus iPhone client. Free always
runs the base quantized model on the phone. Premium switches between
that user's LoRA model on the phone and cloud chat with RAG and memory.

## ADDED Requirements

### Requirement: Auth screen before the product

The app SHALL show the auth screen when the device has no access token.
The screen SHALL show the Encefalus name, the line "AI-Augmented Brain",
and the line "Your memories. Sharper decisions. A more intentional you."
It SHALL offer Sign in and Sign up. Sign in SHALL collect email and
password. Sign up SHALL collect name, email, and password. The interface
SHALL be in English. With no token, the only `/api` calls the app can
make are `POST /api/auth/signup` and `POST /api/auth/signin`.

#### Scenario: No token

- **GIVEN** no access token on the device
- **WHEN** the app opens
- **THEN** the auth screen is shown and the product screens are not

#### Scenario: Sign-up creates a free account

- **GIVEN** the auth screen on Sign up
- **WHEN** the person submits a name, email, and password
- **THEN** the app calls `POST /api/auth/signup` with `plan` equal to `"free"` and, on HTTP 201, stores `access_token` and `user` and opens Local AI Chat

#### Scenario: Sign-in opens chat

- **GIVEN** an existing account
- **WHEN** sign-in returns HTTP 200 with `access_token` and `user`
- **THEN** Local AI Chat replaces the auth screen

#### Scenario: Rejected credentials stay on auth

- **GIVEN** the auth screen
- **WHEN** sign-in returns HTTP 401 or sign-up returns HTTP 409
- **THEN** the app stays on the auth screen and shows the router error

### Requirement: Auth is email and password only

The auth screen SHALL NOT show Continue with Apple, Continue with Google,
Forgot password, or an "or continue with" divider.

#### Scenario: No third-party sign-in

- **GIVEN** the auth screen
- **WHEN** it is shown
- **THEN** Apple, Google, and Forgot password are absent

### Requirement: Local AI Chat is the signed-in home

After sign-in the app SHALL open Local AI Chat. The title SHALL be
"Local AI Chat". A control SHALL start a new empty thread. A menu SHALL
open Model & Device Status, Free vs Premium, and Settings. Those three
screens SHALL return to Local AI Chat. The composer SHALL show one
monochrome attach control and a field whose placeholder is
"Ask anything...". It SHALL NOT show a microphone. The composer SHALL
stay visible while the keyboard is open.

#### Scenario: Menu reaches the wireframe screens

- **GIVEN** a signed-in user on Local AI Chat
- **WHEN** they open the menu
- **THEN** they can reach Model & Device Status, Free vs Premium, and Settings, and each of those screens can return to chat

#### Scenario: New thread is empty

- **GIVEN** a signed-in user with an existing thread
- **WHEN** they start a new thread
- **THEN** the transcript is empty and the previous thread remains stored on the device

### Requirement: Free always uses the base on-device model

The free plan SHALL answer with the base Q4 pack only. It SHALL NOT load
a fine-tuned or LoRA pack. It SHALL NOT call `POST /api/chat` or
`POST /api/upload`. The pill SHALL read "On Device" and SHALL NOT be a
mode switch. The screen SHALL show "Runs completely on your iPhone. No
cloud required." The reply SHALL be appended to the open thread. The
runtime SHALL record elapsed time and output token count for each
completed reply.

#### Scenario: Free question uses the base pack

- **GIVEN** a signed-in free user with the base pack installed
- **WHEN** they send a text question
- **THEN** the reply is produced by the base on-device pack and the app does not call `POST /api/chat` or `POST /api/upload`

#### Scenario: Free does not load a LoRA pack

- **GIVEN** a signed-in free user and a fine-tuned pack present on the device
- **WHEN** they send a text question
- **THEN** the engine loads the base pack and not the fine-tuned pack

#### Scenario: Missing pack does not fall back to the cloud

- **GIVEN** a signed-in free user with no base pack installed
- **WHEN** they send a text question
- **THEN** the app does not call `POST /api/chat` and tells them to download the model

#### Scenario: Short reply reports timing

- **GIVEN** a completed on-device reply
- **WHEN** Model & Device Status reads recent short replies
- **THEN** it shows the average elapsed time from those recorded replies

### Requirement: On-device latency target

A short on-device reply, measured on an iPhone with the Q4 pack loaded,
SHALL finish within 2 seconds and SHALL exceed 18 tokens per second.
This measurement is a device check. A test double MAY supply elapsed time
and token count so screen tests do not require a handset.

#### Scenario: Device check

- **GIVEN** the Q4 pack loaded on an iPhone
- **WHEN** a short text reply completes
- **THEN** elapsed time is at most 2 seconds and the token rate is above 18 tokens per second

### Requirement: On-device questions accept five local files

An on-device question SHALL accept at most five files. The phone SHALL
extract text from plain text and PDF files and include that text in the
local prompt. The bytes and the extracted text SHALL stay on the phone,
stored with the thread, and SHALL be included in later on-device
questions in that same thread. A sixth file SHALL be refused. An image
or any file with no extractable text SHALL be refused on the phone. The
app SHALL NOT call `POST /api/upload` or `POST /api/chat` for these files.

#### Scenario: Five files stay on the phone

- **GIVEN** a signed-in user in on-device mode
- **WHEN** they attach five text or PDF files and send a question
- **THEN** the local model receives the question plus the extracted text, and the app does not call `POST /api/chat` or `POST /api/upload`

#### Scenario: Sixth file is refused

- **GIVEN** a question that already has five files
- **WHEN** the person attaches another file
- **THEN** the app refuses it and still has five files

#### Scenario: Later question keeps the files

- **GIVEN** an on-device thread whose first question included files
- **WHEN** the person asks a later question in that thread
- **THEN** the local prompt still includes the extracted text from those files

#### Scenario: Image is not uploaded

- **GIVEN** on-device mode
- **WHEN** the person attaches an image
- **THEN** the app refuses it on the phone and does not upload it

### Requirement: Threads stay on the device

Threads SHALL be stored on the device and scoped to the signed-in user
id. One user SHALL NOT see another user's threads. An on-device turn
SHALL NOT be written to the server chat store.

#### Scenario: Threads follow the account

- **GIVEN** two accounts that have each used chat on this phone
- **WHEN** the second account is signed in
- **THEN** only that account's threads are listed

### Requirement: Model and device status

Model & Device Status SHALL show the label "Qwen 3.5 4B", the line
"Open source LLM · 4.0B parameters", and the line "A capable, efficient
model for everyday questions, writing, and analysis." It SHALL show
model-file bytes and cache bytes against a 4.1 GB budget, using sizes
measured on the device. It SHALL show whether the pack is ready, whether
chat can run offline, and the average response time of short replies.
It SHALL offer "Reinstall Model" with the line "Download or update model
files" and "Clear Cache".

#### Scenario: Sizes are measured

- **GIVEN** a signed-in user on Model & Device Status
- **WHEN** the screen loads
- **THEN** model-file bytes, cache bytes, and the 4.1 GB budget are shown from the device, and the screen does not invent a fixed 2.8 GB or 320 MB

#### Scenario: Ready and offline

- **GIVEN** a pack installed and no network
- **WHEN** the screen loads
- **THEN** it shows the model ready on device and that chat works without internet

#### Scenario: Clear cache keeps the pack and threads

- **GIVEN** an installed pack, cache bytes, and a stored thread
- **WHEN** the person clears the cache
- **THEN** cache bytes drop, the pack remains, and the thread remains

### Requirement: Reinstall downloads the plan pack

Reinstall Model SHALL download the pack from
`GET /api/models/on-device/file` after reading
`GET /api/models/on-device`. The app SHALL verify `sha256` before
replacing the installed pack. A failed or incomplete download SHALL
leave the previous pack in place. The request SHALL send `X-Request-ID`
and the access token, and SHALL go to the API Router only.

#### Scenario: Successful reinstall swaps the pack

- **GIVEN** a signed-in user and a metadata response with `ready` true
- **WHEN** the file download finishes and the checksum matches `sha256`
- **THEN** the new pack becomes the installed pack

#### Scenario: Failed download keeps the old pack

- **GIVEN** an installed pack
- **WHEN** the download fails or the checksum does not match
- **THEN** the installed pack is unchanged

### Requirement: Free versus Premium comparison

Free vs Premium SHALL show "Go further with Encefalus" and the line
"Keep using local AI, or upgrade to the full Digital Brain on the web."
The table SHALL list these rows, with a mark for included and a dash
for absent:

| Feature | Free (Local AI) | Premium (Digital Brain) |
| --- | --- | --- |
| General Chat | included | included |
| On-device Privacy | included | included |
| Lifelong Memory | absent | included |
| RAG over files | absent | included |
| Decision Simulator | absent | included |
| Analytics & Insights | absent | included |
| Shield (Safety layer) | absent | included |

The screen SHALL show "Use the web app for memory, RAG, analytics and
more." Lifelong Memory, RAG over files, Decision Simulator, Analytics &
Insights, and Shield SHALL NOT open as phone screens.

#### Scenario: Free user sees the table

- **GIVEN** a signed-in free user
- **WHEN** they open Free vs Premium
- **THEN** the seven rows match the table above and Upgrade to Premium is available

#### Scenario: Premium rows do not open phone modules

- **GIVEN** a signed-in user on Free vs Premium
- **WHEN** they look for Memory, Decisions, Analytics, or Shield
- **THEN** those modules are described as the web Digital Brain and no phone screen loads their data

### Requirement: Upgrade changes the plan

On the free plan, Upgrade to Premium SHALL call `PATCH /api/account`
with `plan` equal to `"premium"`. On HTTP 200 the app SHALL store the
new `access_token` and `user`. On the premium plan the same control
SHALL explain that the Digital Brain is the web app and SHALL NOT send
another plan change.

#### Scenario: Free upgrade

- **GIVEN** a signed-in free user
- **WHEN** they confirm Upgrade to Premium and the router returns HTTP 200
- **THEN** the stored plan is `"premium"` and the new access token replaces the old one

#### Scenario: Already premium

- **GIVEN** a signed-in premium user
- **WHEN** they open Free vs Premium or Settings
- **THEN** the app does not call `PATCH /api/account`

### Requirement: Settings matches the wireframe

Settings SHALL show Appearance with Theme defaulting to System, and
SHALL allow System, Light, and Dark. The choice SHALL persist across
launches. Privacy SHALL show "Keep data on device". While the switch is
On device, the line SHALL be "Conversations and files stay on this
iPhone. Nothing is sent to the cloud." While the switch is Digital Brain,
the line SHALL say that turns use the Digital Brain with RAG and memory.
The toggle SHALL default on. On
the free plan it SHALL stay on. On the premium plan it SHALL be the
same switch as the chat pill: on means On device, off means Digital
Brain. Local Data SHALL show measured app storage and Clear All Data
with the line "Remove conversations, cache,
and model files from this device." Support SHALL show Help & FAQ and
"About Encefalus" with version "v1.0.0". The footer SHALL include
"Premium runs in your secure web app with memory, RAG, analytics,
simulator and shield." Help and About SHALL be local English text and
SHALL NOT call `/api`.

#### Scenario: Theme persists

- **GIVEN** a signed-in user on Settings
- **WHEN** they set Theme to Dark and relaunch the app
- **THEN** Theme is still Dark

#### Scenario: Free cannot turn privacy off

- **GIVEN** a signed-in free user
- **WHEN** they try to turn "Keep data on device" off
- **THEN** the toggle stays on and the next question still uses the base on-device pack

#### Scenario: Premium toggle matches the chat pill

- **GIVEN** a signed-in premium user
- **WHEN** they turn "Keep data on device" off
- **THEN** the chat pill shows Digital Brain, and turning it back on shows On Device

#### Scenario: Clear all data is on-device

- **GIVEN** local threads, cache, and an installed pack
- **WHEN** the person confirms Clear All Data
- **THEN** those local items are removed, the account remains, and the app does not call `DELETE /api/data`

### Requirement: Premium switches between the local LoRA model and cloud chat

A premium user SHALL have one inference switch, defaulting to On device.
The chat pill and Settings "Keep data on device" SHALL show that same
state.

While the switch is On device, a question SHALL be answered by that
user's fine-tuned Q4 pack. When that pack is not ready, the phone SHALL
use the base Q4 pack and SHALL say the personal model is not built yet.
The screen SHALL show "On Device" and "Runs completely on your iPhone.
No cloud required." The question SHALL NOT call `POST /api/chat`. Local
files follow the five-file on-device rule.

While the switch is Digital Brain, a text question SHALL call
`POST /api/chat` on the API Router with retrieval enabled, so the answer
uses the cloud base model, RAG, and that user's stored memory. The first
cloud question in a thread SHALL create a server chat and reuse its id.
Up to five files on that question SHALL be sent as chat attachments and
SHALL NOT be a separate memory upload. A sixth file SHALL be refused.
The screen SHALL show Digital Brain and SHALL NOT show "Runs completely
on your iPhone. No cloud required." The app SHALL NOT call a service
port directly.

#### Scenario: Premium on device uses the LoRA pack

- **GIVEN** a signed-in premium user with the switch On device and that user's fine-tuned pack installed
- **WHEN** they send a question
- **THEN** the reply comes from the fine-tuned on-device pack and `POST /api/chat` is not called

#### Scenario: Personal pack missing uses base

- **GIVEN** a signed-in premium user with the switch On device and no fine-tuned pack
- **WHEN** they send a question and the base pack is installed
- **THEN** the reply comes from the base pack and the app says the personal model is not built yet

#### Scenario: Digital Brain uses RAG and memory

- **GIVEN** a signed-in premium user with the switch on Digital Brain
- **WHEN** they send a text question
- **THEN** the app calls `POST /api/chat` on the router with retrieval enabled and shows Digital Brain

#### Scenario: Digital Brain files ride on the chat request

- **GIVEN** a signed-in premium user with the switch on Digital Brain
- **WHEN** they attach up to five files and send a question
- **THEN** those files are sent as attachments on `POST /api/chat` and the app does not call `POST /api/upload`

#### Scenario: Digital Brain refuses a sixth file

- **GIVEN** a Digital Brain question that already has five attachments
- **WHEN** the person attaches another file
- **THEN** the app refuses it and still sends five attachments

#### Scenario: Switch returns to the LoRA model

- **GIVEN** a premium user whose switch is Digital Brain
- **WHEN** they set it back to On device and send a question
- **THEN** the reply comes from the on-device pack and `POST /api/chat` is not called

### Requirement: Sign out

Settings SHALL offer sign out. Sign out SHALL remove the access token
and return to the auth screen. It SHALL remove that account's local
threads and the fine-tuned pack if that pack is installed. It MAY leave
the base pack on the device.

#### Scenario: Sign out returns to auth

- **GIVEN** a signed-in user
- **WHEN** they sign out
- **THEN** the token is gone, Local AI Chat is not shown, and the auth screen is shown

### Requirement: The phone calls only the API Router

Every product HTTP call SHALL use an `/api` path on the API Router.
The app SHALL NOT call ports 8001, 8002, 8003, 8004, 8005, 8006, 8007,
or 8008. Each router call SHALL send `X-Request-ID`.

#### Scenario: No direct service port

- **GIVEN** any screen
- **WHEN** the app sends a product HTTP request
- **THEN** the request uses the router `/api` origin and does not use ports 8001 through 8008
