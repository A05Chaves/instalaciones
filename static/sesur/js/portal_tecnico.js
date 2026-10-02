document.addEventListener("DOMContentLoaded", () => {
    const cfg = window.SESUR_TECNICO;
    const lista = document.getElementById("lista-servicios");
    const plantilla = document.getElementById("plantilla-servicio");
    let servicios = [];
    let filtro = "HOY";
    let terminoBusqueda = "";
    let servicioAlertaId = null;
    const claveBorradores = "sesur-tecnico-borradores-novedad";
    let borradoresNovedad = {};
    try {
        borradoresNovedad = JSON.parse(sessionStorage.getItem(claveBorradores) || "{}") || {};
    } catch (_) {
        borradoresNovedad = {};
    }

    function guardarBorradores() {
        sessionStorage.setItem(claveBorradores, JSON.stringify(borradoresNovedad));
    }

    function limpiarBorrador(servicioId) {
        delete borradoresNovedad[String(servicioId)];
        guardarBorradores();
    }

    function estadoVisualActual() {
        const abiertos = Array.from(document.querySelectorAll(".servicio")).filter(articulo => (
            articulo.querySelector(".resumen-servicio")?.getAttribute("aria-expanded") === "true"
        )).map(articulo => articulo.dataset.servicioId);
        const activo = document.activeElement;
        const editando = activo?.classList?.contains("novedad") ? activo.closest(".servicio") : null;
        return {
            abiertos,
            servicioEditando: editando?.dataset.servicioId || null,
            inicioSeleccion: activo?.selectionStart,
            finSeleccion: activo?.selectionEnd,
            desplazamiento: window.scrollY,
        };
    }

    const abrirDB = () => new Promise((resolve, reject) => {
        const req = indexedDB.open("sesur-tecnico", 1);
        req.onupgradeneeded = () => {
            const db = req.result;
            if (!db.objectStoreNames.contains("datos")) db.createObjectStore("datos");
            if (!db.objectStoreNames.contains("cola")) db.createObjectStore("cola", {keyPath: "clave"});
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });

    async function guardar(almacen, clave, valor) {
        const db = await abrirDB();
        return new Promise((resolve, reject) => {
            const req = db.transaction(almacen, "readwrite").objectStore(almacen).put(valor, clave);
            req.onsuccess = resolve; req.onerror = () => reject(req.error);
        });
    }
    async function leer(almacen, clave) {
        const db = await abrirDB();
        return new Promise((resolve, reject) => {
            const req = db.transaction(almacen).objectStore(almacen).get(clave);
            req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
        });
    }
    async function colaCompleta() {
        const db = await abrirDB();
        return new Promise((resolve, reject) => {
            const req = db.transaction("cola").objectStore("cola").getAll();
            req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
        });
    }
    async function quitarCola(clave) {
        const db = await abrirDB();
        return new Promise(resolve => {
            const req = db.transaction("cola", "readwrite").objectStore("cola").delete(clave);
            req.onsuccess = resolve; req.onerror = resolve;
        });
    }
    function cookie(nombre) {
        const item = document.cookie.split(";").map(v => v.trim()).find(v => v.startsWith(`${nombre}=`));
        return item ? decodeURIComponent(item.split("=").slice(1).join("=")) : "";
    }
    function hoy() {
        const ahora = new Date();
        return `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, "0")}-${String(ahora.getDate()).padStart(2, "0")}`;
    }
    function mensaje(texto) {
        const el = document.getElementById("mensaje-app");
        el.textContent = texto; el.classList.remove("oculto");
        setTimeout(() => el.classList.add("oculto"), 3500);
    }
    async function actualizarRed() {
        const online = navigator.onLine;
        document.getElementById("indicador-red").className = `punto ${online ? "online" : "offline"}`;
        document.getElementById("texto-red").textContent = online ? "En línea" : "Sin conexión";
        const cola = await colaCompleta();
        document.getElementById("pendientes-sync").textContent = cola.length ? `${cola.length} cambio(s) pendiente(s)` : "";
    }
    function escapar(texto) {
        const div = document.createElement("div"); div.textContent = texto || ""; return div.innerHTML;
    }
    function estaActivo(servicio) {
        return servicio.estado !== "FINALIZADO" && !servicio.bloqueado && !servicio.realizado;
    }
    function render() {
        const estadoVisual = estadoVisualActual();
        const activos = servicios.filter(estaActivo);
        document.getElementById("total-pendientes").textContent = activos.length;
        let visibles = activos;
        if (filtro === "HOY") visibles = activos.filter(s => s.fecha_programada === hoy());
        if (filtro === "PENDIENTE") visibles = activos;
        if (filtro === "EJECUCION") visibles = activos.filter(s => s.estado === "EN_PROCESO");
        if (terminoBusqueda) {
            visibles = visibles.filter(servicio => [
                servicio.codigo, servicio.ticket, servicio.cliente,
                servicio.ciudad, servicio.direccion, servicio.tipo_servicio,
                servicio.tipo_falla, servicio.estado,
            ].some(valor => String(valor || "").toLocaleLowerCase("es").includes(terminoBusqueda)));
        }
        document.getElementById("titulo-lista").textContent = filtro === "HOY" ? "Servicios de hoy" : filtro === "PENDIENTE" ? "Servicios pendientes" : filtro === "EJECUCION" ? "Servicio en ejecución" : "Todos los servicios";
        document.getElementById("total-servicios").textContent = visibles.length;
        lista.innerHTML = "";
        if (!visibles.length) {
            lista.innerHTML = '<p class="vacio">No hay servicios en esta sección.</p>'; return;
        }
        const servicioEnEjecucion = activos.find(s => s.estado === "EN_PROCESO");
        visibles.forEach(servicio => {
            const nodo = plantilla.content.cloneNode(true);
            const articulo = nodo.querySelector("article");
            articulo.dataset.estado = servicio.estado;
            articulo.dataset.servicioId = servicio.id;
            nodo.querySelector(".referencia").textContent =
                `Código cliente: ${servicio.codigo || "Sin código"}` +
                (servicio.ticket ? ` · Ticket: ${servicio.ticket}` : "");
            nodo.querySelector(".cliente").textContent = servicio.cliente;
            nodo.querySelector(".estado").textContent =
                servicio.estado_label || servicio.estado.replace("_", " ");
            nodo.querySelector(".fecha").textContent = servicio.fecha_programada ? `📅 ${servicio.fecha_programada}` : "📅 Sin fecha programada";
            nodo.querySelector(".direccion").textContent = `📍 ${servicio.direccion}${servicio.ciudad ? `, ${servicio.ciudad}` : ""}`;
            nodo.querySelector(".detalle").textContent = `${servicio.tipo_servicio}${servicio.tipo_falla ? ` · ${servicio.tipo_falla}` : ""}`;
            const tiempos = [];
            if (servicio.inicio) tiempos.push(`Inicio: ${new Date(servicio.inicio).toLocaleString("es-CO")}`);
            if (servicio.fin) tiempos.push(`Finalización: ${new Date(servicio.fin).toLocaleString("es-CO")}`);
            nodo.querySelector(".tiempos").textContent = tiempos.join(" · ");
            const pendiente = nodo.querySelector(".pendiente");
            pendiente.textContent = servicio.pendiente ? `Pendiente: ${servicio.pendiente}` : "";
            const resumen = nodo.querySelector(".resumen-servicio");
            const detalleServicio = nodo.querySelector(".detalle-servicio");
            resumen.addEventListener("click", () => {
                const abierto = resumen.getAttribute("aria-expanded") === "true";
                resumen.setAttribute("aria-expanded", String(!abierto));
                detalleServicio.classList.toggle("oculto", abierto);
            });
            const novedad = nodo.querySelector(".novedad");
            const claveServicio = String(servicio.id);
            novedad.value = Object.prototype.hasOwnProperty.call(borradoresNovedad, claveServicio)
                ? borradoresNovedad[claveServicio]
                : (servicio.novedad || "");
            const iniciar = nodo.querySelector(".iniciar");
            const soltar = nodo.querySelector(".soltar");
            const finalizar = nodo.querySelector(".finalizar");
            const bloqueado = servicio.bloqueado || servicio.estado === "FINALIZADO";
            const ejecucionDistinta = servicioEnEjecucion && servicioEnEjecucion.id !== servicio.id;
            novedad.disabled = bloqueado;
            iniciar.disabled = bloqueado || servicio.estado !== "PENDIENTE";
            iniciar.title = "";
            soltar.hidden = servicio.estado !== "EN_PROCESO";
            soltar.disabled = servicio.estado !== "EN_PROCESO" || bloqueado;
            const actualizarFinalizar = () => {
                finalizar.disabled = servicio.estado !== "EN_PROCESO" || !novedad.value.trim();
                finalizar.title = servicio.estado === "EN_PROCESO" && !novedad.value.trim()
                    ? "Escribe la novedad antes de finalizar."
                    : "";
            };
            actualizarFinalizar();
            novedad.addEventListener("input", () => {
                borradoresNovedad[claveServicio] = novedad.value;
                guardarBorradores();
                actualizarFinalizar();
            });
            iniciar.addEventListener("click", () => {
                if (!navigator.onLine && ejecucionDistinta) {
                    const referencia = servicioEnEjecucion.ticket || servicioEnEjecucion.codigo || servicioEnEjecucion.id;
                    mensaje(`Tienes otro servicio abierto (${referencia}). Debes finalizarlo o soltarlo antes de iniciar otro.`);
                    return;
                }
                cambiarEstado(servicio, "EN_PROCESO", novedad.value);
            });
            soltar.addEventListener("click", () => {
                if (window.confirm("¿Soltar este servicio? Volverá a pendiente y se eliminará la hora de inicio registrada.")) {
                    cambiarEstado(servicio, "PENDIENTE", novedad.value);
                }
            });
            finalizar.addEventListener("click", () => cambiarEstado(servicio, "FINALIZADO", novedad.value));
            lista.appendChild(nodo);
        });
        estadoVisual.abiertos.forEach(id => {
            const articulo = lista.querySelector(`[data-servicio-id="${id}"]`);
            const resumen = articulo?.querySelector(".resumen-servicio");
            const detalle = articulo?.querySelector(".detalle-servicio");
            if (resumen && detalle) {
                resumen.setAttribute("aria-expanded", "true");
                detalle.classList.remove("oculto");
            }
        });
        if (estadoVisual.servicioEditando) {
            requestAnimationFrame(() => {
                const textarea = lista.querySelector(
                    `[data-servicio-id="${estadoVisual.servicioEditando}"] .novedad`
                );
                if (!textarea) return;
                textarea.focus({preventScroll: true});
                if (Number.isInteger(estadoVisual.inicioSeleccion)) {
                    textarea.setSelectionRange(
                        estadoVisual.inicioSeleccion,
                        estadoVisual.finSeleccion
                    );
                }
                window.scrollTo({top: estadoVisual.desplazamiento, behavior: "auto"});
            });
        }
    }
    function renderAvisos(avisos) {
        const panel = document.getElementById("avisos");
        const contenedor = document.getElementById("lista-avisos");
        panel.classList.toggle("oculto", !avisos.length);
        document.getElementById("total-avisos").textContent = avisos.length;
        contenedor.innerHTML = avisos.map(a => `<div class="aviso"><strong>${escapar(a.tipo)}</strong><br>${escapar(a.mensaje)}</div>`).join("");
    }
    function actualizarBotonAlertas() {
        const boton = document.getElementById("btn-alertas");
        const disponible = "Notification" in window;
        boton.hidden = !disponible || Notification.permission === "granted";
    }
    async function notificarTelefono(aviso) {
        if (!("Notification" in window) || Notification.permission !== "granted") return;
        const opciones = {
            body: aviso.mensaje,
            icon: "/static/sesur/img/logosesur.png",
            badge: "/static/sesur/img/logosesur.png",
            tag: `asignacion-${aviso.id}`,
            renotify: true,
            data: {url: window.location.href},
        };
        if ("serviceWorker" in navigator) {
            const registro = await navigator.serviceWorker.getRegistration();
            if (registro) {
                await registro.showNotification("Nuevo servicio asignado", opciones);
                return;
            }
        }
        new Notification("Nuevo servicio asignado", opciones);
    }
    async function procesarAvisosNuevos(avisos) {
        const asignaciones = avisos.filter(a => ["ASIGNACION", "REASIGNACION"].includes(a.tipo));
        if (!asignaciones.length) return;
        const mostrados = new Set(await leer("datos", "avisos_mostrados") || []);
        const nuevos = asignaciones.filter(a => !mostrados.has(a.id));
        if (!nuevos.length) return;
        nuevos.forEach(a => mostrados.add(a.id));
        await guardar("datos", "avisos_mostrados", Array.from(mostrados).slice(-100));
        const aviso = nuevos[0];
        servicioAlertaId = aviso.servicio_id;
        document.getElementById("texto-alerta-asignacion").textContent = aviso.mensaje;
        document.getElementById("alerta-asignacion").classList.remove("oculto");
        await notificarTelefono(aviso).catch(() => {});
        if (navigator.vibrate) navigator.vibrate([180, 80, 180]);
    }
    async function encolar(payload) {
        const db = await abrirDB();
        const cambio = {clave: `${payload.id}-${Date.now()}`, payload};
        await new Promise((resolve, reject) => {
            const req = db.transaction("cola", "readwrite").objectStore("cola").put(cambio);
            req.onsuccess = resolve; req.onerror = () => reject(req.error);
        });
    }
    async function enviar(payload) {
        return fetch(cfg.api, {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-CSRFToken": cookie("csrftoken")},
            body: JSON.stringify(payload),
        });
    }
    async function cambiarEstado(servicio, estado, novedad) {
        const payload = {
            id: servicio.id,
            estado,
            novedad,
            fecha_evento: new Date().toISOString(),
            registrado_offline: !navigator.onLine,
        };
        const estadoAnterior = servicio.estado;
        const realizadoAnterior = servicio.realizado;
        const inicioAnterior = servicio.inicio;
        const finAnterior = servicio.fin;
        servicio.estado = estado; servicio.novedad = novedad;
        if (estado === "FINALIZADO") servicio.realizado = hoy();
        if (estado === "PENDIENTE") {
            servicio.inicio = ""; servicio.fin = ""; servicio.realizado = "";
        }
        await guardar("datos", "servicios", servicios); render();
        try {
            if (!navigator.onLine) throw new Error("offline");
            const respuesta = await enviar(payload);
            if (respuesta.status === 404) {
                mensaje("El servicio fue reasignado y ya no puedes actualizarlo.");
                return sincronizar();
            }
            if (respuesta.status === 400 || respuesta.status === 409) {
                const error = await respuesta.json().catch(() => ({}));
                if (error.retirar) {
                    limpiarBorrador(servicio.id);
                    servicios = servicios.filter(item => item.id !== servicio.id);
                    await guardar("datos", "servicios", servicios);
                    render();
                    mensaje(error.error || "El servicio fue cerrado y se retiró del dispositivo.");
                    return sincronizar();
                }
                servicio.estado = estadoAnterior;
                servicio.realizado = realizadoAnterior;
                servicio.inicio = inicioAnterior;
                servicio.fin = finAnterior;
                render();
                mensaje(error.error || "El servidor no aceptó el cambio.");
                return;
            }
            if (!respuesta.ok || respuesta.redirected) throw new Error("servidor");
            const data = await respuesta.json();
            Object.assign(servicio, data.servicio);
            limpiarBorrador(servicio.id);
            if (!estaActivo(servicio)) servicios = servicios.filter(item => item.id !== servicio.id);
            await guardar("datos", "servicios", servicios); render();
            mensaje("Servicio actualizado.");
        } catch (_) {
            payload.registrado_offline = true;
            await encolar(payload); mensaje("Cambio guardado en el dispositivo. Se enviará al recuperar conexión.");
        }
        actualizarRed();
    }
    async function enviarCola() {
        if (!navigator.onLine) return;
        for (const cambio of await colaCompleta()) {
            try {
                const respuesta = await enviar(cambio.payload);
                if (respuesta.ok || respuesta.status === 400 || respuesta.status === 404 || respuesta.status === 409) {
                    await quitarCola(cambio.clave);
                    if (respuesta.ok) limpiarBorrador(cambio.payload.id);
                    if (!respuesta.ok) {
                        const error = await respuesta.json().catch(() => ({}));
                        mensaje(error.error || "Un cambio pendiente no pudo aplicarse.");
                    }
                } else {
                    mensaje("Hay cambios pendientes que el servidor todavía no aceptó.");
                    break;
                }
            } catch (_) { break; }
        }
    }
    async function sincronizar(silencioso = false) {
        await actualizarRed();
        if (!navigator.onLine) { if (!silencioso) mensaje("Continúas sin conexión."); return; }
        try {
            await enviarCola();
            const respuesta = await fetch(cfg.api, {headers: {"Accept": "application/json"}, cache: "no-store"});
            if (!respuesta.ok) throw new Error();
            const data = await respuesta.json();
            const escribiendoNovedad = document.activeElement?.classList?.contains("novedad");
            // No reconstruir la tarjeta mientras el teclado del teléfono está
            // abierto. La siguiente sincronización aplicará los datos nuevos.
            if (!escribiendoNovedad) {
                servicios = data.servicios;
                await guardar("datos", "servicios", servicios);
                render();
            }
            await guardar("datos", "avisos", data.notificaciones);
            renderAvisos(data.notificaciones);
            await procesarAvisosNuevos(data.notificaciones);
            if (!silencioso) mensaje("Información sincronizada.");
        } catch (_) { if (!silencioso) mensaje("No fue posible conectar. Se muestran los últimos datos guardados."); }
        actualizarRed();
    }
    document.querySelectorAll(".filtro").forEach(btn => btn.addEventListener("click", () => {
        document.querySelectorAll(".filtro").forEach(b => b.classList.remove("activo"));
        btn.classList.add("activo"); filtro = btn.dataset.filtro; render();
    }));
    document.getElementById("buscar-servicio").addEventListener("input", event => {
        terminoBusqueda = event.target.value.trim().toLocaleLowerCase("es");
        render();
    });
    document.getElementById("btn-sincronizar").addEventListener("click", () => sincronizar(false));
    document.getElementById("btn-alertas").addEventListener("click", async () => {
        if (!("Notification" in window)) return mensaje("Este dispositivo no admite notificaciones.");
        const permiso = await Notification.requestPermission();
        actualizarBotonAlertas();
        mensaje(permiso === "granted" ? "Alertas del teléfono activadas." : "No se habilitaron las alertas del teléfono.");
    });
    document.getElementById("btn-cerrar-alerta").addEventListener("click", () => {
        document.getElementById("alerta-asignacion").classList.add("oculto");
    });
    document.getElementById("btn-ver-asignacion").addEventListener("click", () => {
        document.getElementById("alerta-asignacion").classList.add("oculto");
        filtro = "TODOS";
        document.querySelectorAll(".filtro").forEach(b => b.classList.toggle("activo", b.dataset.filtro === "TODOS"));
        terminoBusqueda = "";
        document.getElementById("buscar-servicio").value = "";
        render();
        const articulo = document.querySelector(`[data-servicio-id="${servicioAlertaId}"]`);
        if (articulo) {
            articulo.scrollIntoView({behavior: "smooth", block: "center"});
            articulo.querySelector(".resumen-servicio").click();
        }
    });
    document.getElementById("btn-leer-avisos").addEventListener("click", async () => {
        if (!navigator.onLine) return mensaje("Necesitas conexión para confirmar las notificaciones.");
        await fetch(cfg.leerAvisos, {method: "POST", headers: {"X-CSRFToken": cookie("csrftoken")}});
        await guardar("datos", "avisos", []); renderAvisos([]);
    });
    document.getElementById("form-logout").addEventListener("submit", () => {
        sessionStorage.removeItem(claveBorradores);
        indexedDB.deleteDatabase("sesur-tecnico");
    });
    window.addEventListener("online", () => sincronizar(true)); window.addEventListener("offline", actualizarRed);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) sincronizar(true);
    });
    setInterval(() => sincronizar(true), 30000);
    (async () => {
        servicios = await leer("datos", "servicios") || [];
        servicios = servicios.filter(estaActivo);
        await guardar("datos", "servicios", servicios);
        render(); renderAvisos(await leer("datos", "avisos") || []); actualizarRed(); actualizarBotonAlertas(); sincronizar(true);
        if ("serviceWorker" in navigator) {
            navigator.serviceWorker.register(cfg.serviceWorker).then(registro => registro.update());
        }
    })();
});
