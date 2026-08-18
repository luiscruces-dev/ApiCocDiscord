require("dotenv").config();
const express = require("express");
const qrcode = require("qrcode-terminal");
const { Boom } = require("@hapi/boom");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
} = require("@whiskeysockets/baileys");

const PORT = process.env.PORT || 3001;
const BRIDGE_TOKEN = process.env.BRIDGE_TOKEN;
const GROUP_ID = process.env.WHATSAPP_GROUP_ID;

if (!BRIDGE_TOKEN) {
  console.error(
    "Falta BRIDGE_TOKEN en .env — no arranco sin eso, si no cualquiera en internet podria mandar mensajes al grupo."
  );
  process.exit(1);
}

let sock = null;
let conectado = false;

async function iniciarWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState("auth_info");
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("\nEscanea este QR desde WhatsApp -> Dispositivos vinculados -> Vincular un dispositivo:\n");
      qrcode.generate(qr, { small: true });
    }

    if (connection === "close") {
      conectado = false;
      const statusCode = lastDisconnect?.error instanceof Boom ? lastDisconnect.error.output?.statusCode : null;
      const cerroSesion = statusCode === DisconnectReason.loggedOut;
      if (cerroSesion) {
        console.log("Sesion cerrada desde el telefono. Borra la carpeta auth_info/ y volve a arrancar para re-vincular.");
      } else {
        console.log("Conexion cortada, reintentando...");
        iniciarWhatsApp();
      }
    } else if (connection === "open") {
      conectado = true;
      console.log("Conectado a WhatsApp.");
    }
  });
}

iniciarWhatsApp();

const app = express();
app.use(express.json());

function autenticar(req, res, next) {
  if (req.headers.authorization !== `Bearer ${BRIDGE_TOKEN}`) {
    return res.status(401).json({ error: "Token invalido" });
  }
  next();
}

app.post("/send", autenticar, async (req, res) => {
  const { text } = req.body || {};
  if (!text || typeof text !== "string") {
    return res.status(400).json({ error: 'Falta "text" (string) en el body' });
  }
  if (!conectado || !sock) {
    return res.status(503).json({ error: "WhatsApp no esta conectado todavia" });
  }
  if (!GROUP_ID) {
    return res.status(500).json({ error: "Falta WHATSAPP_GROUP_ID en .env (usa GET /grupos para encontrarlo)" });
  }

  try {
    await sock.sendMessage(GROUP_ID, { text });
    res.json({ ok: true });
  } catch (err) {
    console.error("Error enviando mensaje:", err);
    res.status(500).json({ error: "No se pudo enviar el mensaje" });
  }
});

app.get("/status", autenticar, (req, res) => {
  res.json({ conectado });
});

app.get("/grupos", autenticar, async (req, res) => {
  if (!sock || !conectado) {
    return res.status(503).json({ error: "WhatsApp no esta conectado todavia" });
  }
  try {
    const grupos = await sock.groupFetchAllParticipating();
    const lista = Object.values(grupos).map((g) => ({ id: g.id, nombre: g.subject }));
    res.json({ grupos: lista });
  } catch (err) {
    console.error("Error listando grupos:", err);
    res.status(500).json({ error: "No se pudo listar los grupos" });
  }
});

app.listen(PORT, () => {
  console.log(`Puente de WhatsApp escuchando en puerto ${PORT}`);
});
