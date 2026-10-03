# Justificación — Mobile app (Frame 10)

El Frame 10 es la app de iPhone. Free responde siempre con el modelo base
cuantizado en el teléfono. Premium tiene un interruptor: On device usa el
LoRA Q4 de esa persona, y Digital Brain llama a `POST /api/chat` con RAG y
memoria. El teléfono solo habla con el API Router.

## Tres caminos de chat

| Quién | Interruptor | Quién responde |
|-------|-------------|----------------|
| Free en el iPhone | no hay | `qwen3.5-4b-base-q4` en el teléfono. Sin LoRA y sin `POST /api/chat`. |
| Premium, On device | encendido | `qwen3.5-4b-finetuned-q4` de ese `user_id`. Si el paquete no existe, el base, y la app dice que el modelo personal aún no está. |
| Premium, Digital Brain | apagado | El modelo base de la nube, con RAG y la memoria ya guardada. |

Hasta cinco archivos. En el teléfono, el texto de un archivo de texto o PDF
se queda en el hilo y entra en las preguntas siguientes. Una sexta pieza, una
imagen, o un archivo sin texto se rechaza ahí. En Digital Brain, los mismos
cinco viajan como `attachments` de `POST /api/chat`. No hay `POST /api/upload`.
La memoria de largo plazo sigue en la pantalla Memory de la web.

El paquete premium es de una persona. El router no entrega el archivo de otra
cuenta ni sustituye el base cuando el paquete personal no está listo.

## Pantallas

La bienvenida muestra Encefalus, "AI-Augmented Brain", el lema, Sign in /
Sign up, Continue, la tarjeta de privacidad y el pie Free / Premium. No hay
Continue with Apple, Continue with Google, Forgot password, ni "or continue
with". Esas piezas estaban en el dibujo y se quitaron. El compositor tiene
adjuntar e imagen, y el campo "Ask anything...". No hay micrófono.

Model & Device Status mide los bytes del paquete y de la caché contra 4.1 GB.
No fija 2.8 GB ni 320 MB. Free vs Premium es la tabla de siete filas. Memory,
Simulator, Analytics y Shield no son pantallas del teléfono. Settings guarda
el tema, y "Keep data on device" es el mismo interruptor que la pastilla del
chat. Clear All Data borra hilos, caché y paquetes en el aparato. No llama a
`DELETE /api/data`.

## Motor y paquetes

`OnDeviceEngine` expone `load`, `generate`, `cancel` y `stats`. La interfaz
no importa ExecuTorch ni MLC. El módulo iOS valida el archivo `.pte`. El
cuerpo de inferencia es el delegado Core ML / Metal de ExecuTorch; esta
compilación no lo enlaza y no inventa una latencia. Jest usa un motor falso.
La medición de ≤2 s y más de 18 tokens por segundo está descrita en
`services/finetune/experiments/on-device-q4.md` y no se corrió en un iPhone
en esta sesión.

`export_on_device.py` escribe el paquete base y, si hay un adapter de ese
usuario, el paquete premium. `--real` no toca los pesos del contenedor LLM.
El teléfono no descarga del puerto 8004.

## Bitácora

Forma real del router: `%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s`.
El servicio es `api-gateway`. La línea del teléfono usa la misma forma con
el servicio `mobile`. No se registran bytes del paquete ni la contraseña.

```text
2026-10-01T16:40:01 [mobile-signin] INFO api-gateway: POST /api/auth/signin
2026-10-01T16:40:12 [mobile-file] INFO api-gateway: GET /api/models/on-device/file
2026-10-01T16:40:20 [mobile-ab12] INFO mobile: on-device generate pack=qwen3.5-4b-base-q4
2026-10-01T16:41:02 [mobile-chat] INFO api-gateway: POST /api/chat
```

La tercera línea sale de una pregunta On device. No hay una línea de
`POST /api/chat` en ese camino. La cuarta es solo Digital Brain.
