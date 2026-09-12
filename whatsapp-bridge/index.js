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
const COMANDO_COOLDOWN_MS = Number(process.env.COMANDO_COOLDOWN_MS || 5000);

if (!BRIDGE_TOKEN) {
  console.error(
    "Falta BRIDGE_TOKEN en .env — no arranco sin eso, si no cualquiera en internet podria mandar mensajes al grupo."
  );
  process.exit(1);
}

let sock = null;
let conectado = false;
let ultimoQR = null;
const ultimoComandoPorRemitente = new Map();

// No se filtra por fromMe: el dueño del numero vinculado tambien escribe comandos.
const misMensajesEnviados = new Set();
const MAX_MIS_MENSAJES = 500;

function registrarMensajePropio(id) {
  if (!id) return;
  misMensajesEnviados.add(id);
  if (misMensajesEnviados.size > MAX_MIS_MENSAJES) {
    misMensajesEnviados.delete(misMensajesEnviados.values().next().value);
  }
}

// Desenvuelve mensajes efimeros y de "ver una vez".
function contenidoReal(msg) {
  const m = msg.message;
  return m?.ephemeralMessage?.message || m?.viewOnceMessageV2?.message || m?.viewOnceMessage?.message || m;
}

function extraerTexto(msg) {
  const contenido = contenidoReal(msg);
  return contenido?.conversation || contenido?.extendedTextMessage?.text || null;
}

function extraerCitado(msg) {
  const contextInfo = contenidoReal(msg)?.extendedTextMessage?.contextInfo;
  return contextInfo?.participant || contextInfo?.mentionedJid?.[0] || null;
}

function limpiarMenciones(texto, msg) {
  const mentionedJids = contenidoReal(msg)?.extendedTextMessage?.contextInfo?.mentionedJid || [];
  let limpio = texto;
  for (const jid of mentionedJids) {
    limpio = limpio.replace(new RegExp(`@${jid.split("@")[0]}\\b`, "g"), "");
  }
  return limpio.trim();
}

function citaOMencionaAlBot(msg) {
  const contextInfo = contenidoReal(msg)?.extendedTextMessage?.contextInfo;
  if (!contextInfo) return false;

  if (contextInfo.stanzaId && misMensajesEnviados.has(contextInfo.stanzaId)) {
    return true;
  }

  const miNumero = sock?.user?.id?.split(":")[0];
  if (!miNumero) return false;
  return (contextInfo.mentionedJid || []).some((jid) => jid.split("@")[0] === miNumero);
}

function dormir(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Simula el tiempo de tipeo de una persona.
function calcularDelayEnvio(texto) {
  const palabras = (texto || "").trim().split(/\s+/).filter(Boolean).length;
  const pensar = 800 + Math.random() * 1200;
  const porPalabra = 120 + Math.random() * 130;
  const total = pensar + palabras * porPalabra;
  return Math.min(Math.max(total, 1200), 8000);
}

async function enviarConDelay(jid, contenido, opciones = {}) {
  try {
    await sock.sendPresenceUpdate("composing", jid);
  } catch {}
  await dormir(calcularDelayEnvio(contenido.text));
  try {
    await sock.sendPresenceUpdate("paused", jid);
  } catch {}
  return sock.sendMessage(jid, contenido, opciones);
}

async function manejarMensajeEntrante(msg) {
  if (!GROUP_ID || msg.key.remoteJid !== GROUP_ID) return;
  if (misMensajesEnviados.has(msg.key.id)) return;

  const texto = extraerTexto(msg);
  if (!texto || !texto.startsWith("/")) return;

  const partes = texto.slice(1).trim().split(/\s+/);
  const nombre = (partes.shift() || "").toLowerCase();
  if (!nombre) return;
  const argumentos = limpiarMenciones(partes.join(" "), msg);

  const remitente = msg.key.participant || msg.key.remoteJid;
  const ahora = Date.now();
  const ultimo = ultimoComandoPorRemitente.get(remitente) || 0;
  if (ahora - ultimo < COMANDO_COOLDOWN_MS) {
    console.log(`Comando '${nombre}' de ${remitente} ignorado (cooldown)`);
    return;
  }
  ultimoComandoPorRemitente.set(remitente, ahora);

  if (!BOT_API_URL || !BOT_API_TOKEN) {
    console.warn("Llego el comando '%s' pero BOT_API_URL/BOT_API_TOKEN no estan configurados, lo ignoro.", nombre);
    return;
  }

  let respuesta;
  let menciones = [];
  try {
    const resp = await fetch(`${BOT_API_URL.replace(/\/$/, "")}/comando`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${BOT_API_TOKEN}`,
      },
      body: JSON.stringify({
        nombre,
        argumentos,
        remitente,
        citado: citaOMencionaAlBot(msg) ? "BOT" : extraerCitado(msg),
      }),
    });
    const datos = await resp.json();
    respuesta = resp.ok ? datos.texto : datos.error || "Error desconocido consultando el bot de Discord.";
    if (resp.ok) menciones = datos.menciones || [];
  } catch (err) {
    console.error("No se pudo contactar el bot de Discord:", err);
    respuesta = "No pude consultar el bot de Discord ahora mismo, intenta de nuevo en un rato.";
  }

  if (sock && conectado) {
    const enviado = await enviarConDelay(GROUP_ID, { text: respuesta, mentions: menciones }, { quoted: msg });
    registrarMensajePropio(enviado?.key?.id);
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
      if (GROUP_ID && msg.key.remoteJid === GROUP_ID) {
        console.log(
          "MSG_DEBUG",
          JSON.stringify({
            fromMe: msg.key.fromMe,
            id: msg.key.id,
            participant: msg.key.participant || null,
            esMensajePropioConocido: misMensajesEnviados.has(msg.key.id),
            texto: extraerTexto(msg),
            formaDelMensaje: msg.message ? Object.keys(msg.message) : null,
          })
        );
      }
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
  const { text, mentions } = req.body || {};
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
    const enviado = await enviarConDelay(GROUP_ID, { text, mentions: Array.isArray(mentions) ? mentions : [] });
    registrarMensajePropio(enviado?.key?.id);
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
    const lista = Object.values(grupos).map((g) => ({
      id: g.id,
      nombre: g.subject,
      miembros: g.participants?.length,
      descripcion: g.desc || null,
      esComunidad: !!g.isCommunity,
      anuncioDeComunidad: !!g.isCommunityAnnounce,
      comunidadPadre: g.linkedParent || null,
      creado: g.creation ? new Date(g.creation * 1000).toISOString() : null,
    }));
    res.json({ grupos: lista });
  } catch (err) {
    console.error("Error listando grupos:", err);
    res.status(500).json({ error: "No se pudo listar los grupos" });
  }
});

// Debug: JIDs reales de los participantes del grupo.
app.get("/participantes", autenticar, async (req, res) => {
  if (!sock || !conectado) {
    return res.status(503).json({ error: "WhatsApp no esta conectado todavia" });
  }
  if (!GROUP_ID) {
    return res.status(500).json({ error: "Falta WHATSAPP_GROUP_ID en .env" });
  }
  try {
    const metadata = await sock.groupMetadata(GROUP_ID);
    res.json({
      participantes: metadata.participants.map((p) => ({
        id: p.id,
        lid: p.lid || null,
        admin: p.admin || null,
      })),
    });
  } catch (err) {
    console.error("Error obteniendo participantes:", err);
    res.status(500).json({ error: "No se pudo obtener los participantes" });
  }
});

app.listen(PORT, "127.0.0.1", () => {
  console.log(`Puente de WhatsApp escuchando en 127.0.0.1:${PORT}`);
});
