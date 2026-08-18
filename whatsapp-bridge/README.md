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
Con el puente corriendo (y todavía no conectado), pedí el QR como imagen:
```bash
curl -H "Authorization: Bearer TU_BRIDGE_TOKEN" http://localhost:3001/qr --output qr.png
```
Abrí `qr.png`, y desde el celular que vas a usar para el bot: WhatsApp →
**Ajustes → Dispositivos vinculados → Vincular un dispositivo** → escaneá.
El QR rota cada ~20s, así que si tarda en escanear volvé a pedir `/qr` para
tener uno fresco. La sesión queda guardada en `auth_info/` (no se sube a
git), así que no hace falta re-escanear cada vez que reinicies.

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

## Comandos escritos en el grupo

Además de reenviar avisos (Discord → WhatsApp), el puente escucha lo que se
escribe en el grupo configurado. Si alguien tipea `/miembros`, `/guerra`,
etc., el puente le pregunta la respuesta al bot de Discord (que es el único
que habla con la API de Clash y con la base de datos — este puente nunca
duplica esa lógica) y contesta en el grupo citando el mensaje original.

Por diseño, **solo funcionan los comandos de solo lectura** (los mismos que
`/comandos` lista desde WhatsApp). Los que cambian estado, como
`/clangames iniciar` / `/clangames cerrar`, quedan exclusivos de Discord a
propósito — así nadie los dispara sin querer escribiendo en el grupo.

La única excepción es `/vincular <tag>`, que asocia el número de quien lo
escribe con un tag de jugador del clan (y `/desvincular` para deshacerlo).
Se permite porque vincularse no afecta al clan en nada — en el peor caso
alguien se vincula con el tag equivocado y lo corrige mandando el comando
de nuevo. Sirve para que `/recordar` (quién le falta atacar en la guerra
activa) pueda etiquetar directo a la persona en vez de solo nombrarla. Si
la respuesta de un comando trae `@numero`, el puente arma la lista de
menciones automáticamente para que WhatsApp le mande notificación de
verdad, no solo lo muestre como texto.

Esto necesita `BOT_API_URL` / `BOT_API_TOKEN` en `.env` (ver
`.env.example`), y que el bot de Discord tenga configurado `BOT_API_TOKEN`
en su propio `.env` con el mismo valor. Sin esto, los comandos del grupo se
ignoran silenciosamente (queda un aviso en los logs), pero `/enviarwsp`
desde Discord sigue andando igual.

**Importante:** el puente solo procesa mensajes del grupo exacto en
`WHATSAPP_GROUP_ID`. Si el número vinculado está en otros grupos (como pasa
si usás tu WhatsApp personal para probar), esos otros grupos se ignoran por
completo — nunca les contesta nada.

Cada remitente tiene un cooldown (`COMANDO_COOLDOWN_MS`, default 5s) entre
un comando y el siguiente — si insiste antes de que pase ese tiempo, el
puente lo ignora en silencio (no manda ningún aviso, para no sumar más
mensajes al ruido).

**Ojo si probás con tu WhatsApp personal:** mientras el número vinculado
sea el tuyo, los mensajes que escribís vos mismo en el grupo llegan como
`fromMe: true` (WhatsApp no distingue "el bot lo mandó" de "yo lo escribí
desde el celu", porque es la misma cuenta) — el puente los ignora a
propósito para no auto-responderse en loop. Esto se resuelve solo en
cuanto vinculen el número dedicado: ahí los mensajes de miembros reales del
grupo no son `fromMe` y sí disparan los comandos.

## Endpoints

Todos requieren el header `Authorization: Bearer <BRIDGE_TOKEN>`.

- `POST /send` — body `{"text": "...", "mentions": ["jid1", "jid2"]}` (`mentions` opcional), manda el mensaje al grupo configurado.
- `GET /status` — `{"conectado": true|false}`.
- `GET /grupos` — lista `{id, nombre}` de todos los grupos donde está el número vinculado.
- `GET /qr` — imagen PNG del QR pendiente de escanear (404/409 si ya está conectado, 503 si todavía no se generó ninguno).

## Si deja de andar

- **"Sesion cerrada desde el telefono"** en la consola: alguien desvinculó
  el dispositivo desde WhatsApp, o pasaron muchos días sin que el celular se
  conecte a internet. Borrá `auth_info/` y volvé a escanear el QR (paso 3).
- El celular vinculado necesita internet de vez en cuando (WhatsApp
  multi-dispositivo no depende de que esté siempre encendido, pero sí de que
  se conecte cada tanto).
