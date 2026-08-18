require("dotenv").config();
const express = require("express");
const QRCode = require("qrcode");
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
const BOT_API_URL = process.env.BOT_API_URL;
const BOT_API_TOKEN = process.env.BOT_API_TOKEN;

if (!BRIDGE_TOKEN) {
  console.error(
    "Falta BRIDGE_TOKEN en .env — no arranco sin eso, si no cualquiera en internet podria mandar mensajes al grupo."
  );
  process.exit(1);
}

let sock = null;
let conectado = false;
let ultimoQR = null;

// Comandos de solo lectura escritos en el grupo (ej. "/miembros") se
// reenvian al bot de Discord, que es el unico que habla con la API de
// Clash y con la base de datos. Este puente solo traduce ida y vuelta.
async function manejarMensajeEntrante(msg) {
  if (!GROUP_ID || msg.key.remoteJid !== GROUP_ID) return;
  if (msg.key.fromMe) return;

  const texto = msg.message?.conversation || msg.message?.extendedTextMessage?.text;
  if (!texto || !texto.startsWith("/")) return;

  const nombre = texto.slice(1).trim().split(/\s+/)[0].toLowerCase();
  if (!nombre) return;

  if (!BOT_API_URL || !BOT_API_TOKEN) {
    console.warn("Llego el comando '%s' pero BOT_API_URL/BOT_API_TOKEN no estan configurados, lo ignoro.", nombre);
    return;
  }

  let respuesta;
  try {
    const resp = await fetch(`${BOT_API_URL.replace(/\/$/, "")}/comando`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${BOT_API_TOKEN}`,
      },
      body: JSON.stringify({ nombre }),
    });
    const datos = await resp.json();
    respuesta = resp.ok ? datos.texto : datos.error || "Error desconocido consultando el bot de Discord.";
  } catch (err) {
    console.error("No se pudo contactar el bot de Discord:", err);
    respuesta = "No pude consultar el bot de Discord ahora mismo, intenta de nuevo en un rato.";
  }

  if (sock && conectado) {
    await sock.sendMessage(GROUP_ID, { text: respuesta }, { quoted: msg });
  }
}

async function iniciarWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState("auth_info");
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("messages.upsert", ({ messages, type }) => {
    if (type !== "notify") return;
    for (const msg of messages) {
      manejarMensajeEntrante(msg).catch((err) => console.error("Error manejando mensaje entrante:", err));
    }
  });

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      ultimoQR = qr;
      console.log("Nuevo QR disponible en GET /qr");
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
      ultimoQR = null;
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

app.get("/qr", autenticar, async (req, res) => {
  if (conectado) {
    return res.status(409).json({ error: "Ya esta conectado, no hay QR pendiente" });
  }
  if (!ultimoQR) {
    return res.status(503).json({ error: "Todavia no se genero ningun QR, esperá unos segundos" });
  }
  try {
    const png = await QRCode.toBuffer(ultimoQR, { type: "png", width: 400 });
    res.set("Content-Type", "image/png");
    res.send(png);
  } catch (err) {
    console.error("Error generando QR:", err);
    res.status(500).json({ error: "No se pudo generar la imagen del QR" });
  }
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

// Solo localhost: el bot de Discord vive en el mismo servidor, no hace
// falta (ni conviene) exponer esto a internet.
app.listen(PORT, "127.0.0.1", () => {
  console.log(`Puente de WhatsApp escuchando en 127.0.0.1:${PORT}`);
});
