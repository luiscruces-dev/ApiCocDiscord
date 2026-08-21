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

// IDs de mensajes que el propio bot mando (via /send o respondiendo un
// comando). No se puede ignorar todo lo "fromMe" a lo bruto: mientras el
// numero vinculado sea el personal de alguien del clan (no el dedicado
// todavia), esa persona SI necesita poder escribir comandos de verdad
// desde su propio numero, y WhatsApp marca eso tambien como fromMe. Asi
// que solo se ignoran los mensajes que efectivamente somos nosotros
// mismos mandando, identificados por su ID, no por ser fromMe en general.
const misMensajesEnviados = new Set();
const MAX_MIS_MENSAJES = 500;

function registrarMensajePropio(id) {
  if (!id) return;
  misMensajesEnviados.add(id);
  if (misMensajesEnviados.size > MAX_MIS_MENSAJES) {
    misMensajesEnviados.delete(misMensajesEnviados.values().next().value);
  }
}

// Mensajes efimeros ("se borran solos") o "ver una vez" envuelven el
// contenido real adentro de otro objeto -- si el grupo los tiene activados,
// msg.message.conversation/extendedTextMessage quedan vacios y hay que
// desenvolver primero.
function contenidoReal(msg) {
  const m = msg.message;
  return m?.ephemeralMessage?.message || m?.viewOnceMessageV2?.message || m?.viewOnceMessage?.message || m;
}

function extraerTexto(msg) {
  const contenido = contenidoReal(msg);
  return contenido?.conversation || contenido?.extendedTextMessage?.text || null;
}

// Si el mensaje es una respuesta (citando/"deslizando sobre" otro mensaje),
// devuelve el JID de quien escribio el mensaje citado -- tal cual, sin
// reconstruirlo, mismo criterio que las menciones de /recordar. Sirve para
// comandos como /cagarse que quieren apuntar a "la persona que cite" en vez
// de que el remitente tenga que escribir su nombre a mano.
function extraerCitado(msg) {
  const contenido = contenidoReal(msg);
  return contenido?.extendedTextMessage?.contextInfo?.participant || null;
}

function dormir(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Simula el tiempo que tardaria una persona en escribir el mensaje: un
// "pensar" inicial random + tiempo por palabra, con piso y techo para que
// nunca sea instantaneo ni eternamente largo. Todo esto es para que el
// envio no tenga el patron "responde en 50ms, siempre exacto" tan tipico
// de un bot -- no cambia que WhatsApp pueda reconocer la libreria a nivel
// de protocolo, pero ayuda contra deteccion por comportamiento.
function calcularDelayEnvio(texto) {
  const palabras = (texto || "").trim().split(/\s+/).filter(Boolean).length;
  const pensar = 800 + Math.random() * 1200; // 0.8-2s "leyendo/pensando"
  const porPalabra = 120 + Math.random() * 130; // 120-250ms por palabra tipeada
  const total = pensar + palabras * porPalabra;
  return Math.min(Math.max(total, 1200), 8000); // entre 1.2s y 8s
}

// Punto unico de envio al grupo: manda presencia "escribiendo...", espera
// el delay simulado, y recien ahi manda el mensaje. Usado tanto para
// responder comandos como para /send (avisos automaticos).
async function enviarConDelay(jid, contenido, opciones = {}) {
  try {
    await sock.sendPresenceUpdate("composing", jid);
  } catch (err) {
    // no es critico si esto falla, el mensaje se manda igual
  }
  await dormir(calcularDelayEnvio(contenido.text));
  try {
    await sock.sendPresenceUpdate("paused", jid);
  } catch (err) {
    // idem
  }
  return sock.sendMessage(jid, contenido, opciones);
}

// Comandos de solo lectura escritos en el grupo (ej. "/miembros") se
// reenvian al bot de Discord, que es el unico que habla con la API de
// Clash y con la base de datos. Este puente solo traduce ida y vuelta.
async function manejarMensajeEntrante(msg) {
  if (!GROUP_ID || msg.key.remoteJid !== GROUP_ID) return;
  if (misMensajesEnviados.has(msg.key.id)) return;

  const texto = extraerTexto(msg);
  if (!texto || !texto.startsWith("/")) return;

  const partes = texto.slice(1).trim().split(/\s+/);
  const nombre = (partes.shift() || "").toLowerCase();
  if (!nombre) return;
  const argumentos = partes.join(" ");

  // Un remitente no puede disparar mas de un comando cada COMANDO_COOLDOWN_MS,
  // para que nadie inunde el grupo insistiendo con el mismo comando.
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
      body: JSON.stringify({ nombre, argumentos, remitente, citado: extraerCitado(msg) }),
    });
    const datos = await resp.json();
    respuesta = resp.ok ? datos.texto : datos.error || "Error desconocido consultando el bot de Discord.";
    if (resp.ok) menciones = datos.menciones || [];
  } catch (err) {
    console.error("No se pudo contactar el bot de Discord:", err);
    respuesta = "No pude consultar el bot de Discord ahora mismo, intenta de nuevo en un rato.";
  }

  if (sock && conectado) {
    // Los JIDs a mencionar (ej. /recordar etiquetando a quien vinculo su
    // tag) vienen armados tal cual desde el bot de Discord — no se
    // reconstruyen aca. WhatsApp direcciona a cada participante por
    // @s.whatsapp.net o por @lid segun el caso, y adivinar mal el dominio
    // hace que no se reconozca como mencion real (queda como texto suelto).
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
      // Diagnostico: se puede sacar mas adelante, pero mientras se
      // depura por que algunos mensajes del grupo no disparan comandos,
      // ayuda ver la forma real de cada mensaje que llega al grupo.
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

// Debug: JIDs reales de los participantes del grupo configurado. Sirve para
// diagnosticar menciones que no resaltan (WhatsApp a veces direcciona por
// @lid en vez del numero de telefono @s.whatsapp.net).
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

// Solo localhost: el bot de Discord vive en el mismo servidor, no hace
// falta (ni conviene) exponer esto a internet.
app.listen(PORT, "127.0.0.1", () => {
  console.log(`Puente de WhatsApp escuchando en 127.0.0.1:${PORT}`);
});
