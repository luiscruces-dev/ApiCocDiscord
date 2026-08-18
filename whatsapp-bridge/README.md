# whatsapp-bridge

Puentecito HTTP que reenvía mensajes al grupo de WhatsApp. Usa
[Baileys](https://github.com/WhiskeySockets/Baileys), que automatiza una
sesión de WhatsApp Web (no es la API oficial de Meta — esa no soporta
grupos). Está pensado para correr en un servidor propio 24/7, separado del
bot de Discord.

## Por qué así

La API oficial de WhatsApp (Cloud API de Meta) no permite mandar mensajes a
grupos, solo chats 1:1 o plantillas aprobadas. Baileys sí, porque simula un
dispositivo vinculado a un WhatsApp normal. La contra: no es oficial, viola
los términos de servicio de WhatsApp, y si se abusa (spam, volumen alto) el
número puede terminar baneado. Para un grupo chico de ~10 personas que solo
recibe avisos puntuales del bot, el riesgo es bajo — pero usa un número que
no te importe perder, no tu número personal si podés evitarlo.

## Setup

### 1. Instalar
```bash
cd whatsapp-bridge
npm install
```

### 2. Configurar
Copiá `.env.example` a `.env` y generá un `BRIDGE_TOKEN` random:
```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```
Dejá `WHATSAPP_GROUP_ID` vacío por ahora, lo llenás en el paso 4.

### 3. Vincular WhatsApp
```bash
npm start
```
Va a imprimir un QR en la terminal. Abrí WhatsApp en el celular que vas a
usar para el bot → **Ajustes → Dispositivos vinculados → Vincular un
dispositivo** → escaneá el QR. La sesión queda guardada en `auth_info/` (no
se sube a git), así que no hace falta re-escanear cada vez que reinicies.

### 4. Encontrar el ID del grupo
Con el puente corriendo y ya conectado (dice "Conectado a WhatsApp." en la
consola), pedí:
```bash
curl -H "Authorization: Bearer TU_BRIDGE_TOKEN" http://localhost:3001/grupos
```
Copiá el `id` (termina en `@g.us`) del grupo que quieras y pegalo en
`WHATSAPP_GROUP_ID` dentro de `.env`. Reiniciá el puente (`npm start`).

### 5. Probar el envío
```bash
curl -X POST http://localhost:3001/send \
  -H "Authorization: Bearer TU_BRIDGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "Probando el puente 🚀"}'
```
Si todo salió bien, el mensaje aparece en el grupo de WhatsApp.

## Dejarlo corriendo 24/7

Esto tiene que quedar vivo todo el tiempo para mantener la sesión de
WhatsApp activa. En Linux, la forma más simple es `pm2`:
```bash
npm install -g pm2
pm2 start index.js --name whatsapp-bridge
pm2 save
pm2 startup   # deja el proceso arrancando solo si el servidor reinicia
```

## Endpoints

Todos requieren el header `Authorization: Bearer <BRIDGE_TOKEN>`.

- `POST /send` — body `{"text": "..."}`, manda el mensaje al grupo configurado.
- `GET /status` — `{"conectado": true|false}`.
- `GET /grupos` — lista `{id, nombre}` de todos los grupos donde está el número vinculado.

## Si deja de andar

- **"Sesion cerrada desde el telefono"** en la consola: alguien desvinculó
  el dispositivo desde WhatsApp, o pasaron muchos días sin que el celular se
  conecte a internet. Borrá `auth_info/` y volvé a escanear el QR (paso 3).
- El celular vinculado necesita internet de vez en cuando (WhatsApp
  multi-dispositivo no depende de que esté siempre encendido, pero sí de que
  se conecte cada tanto).
