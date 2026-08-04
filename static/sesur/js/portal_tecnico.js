document.addEventListener("DOMContentLoaded", () => {
    const cfg = window.SESUR_TECNICO;
    const lista = document.getElementById("lista-servicios");
    const plantilla = document.getElementById("plantilla-servicio");
    let servicios = [];
    let filtro = "HOY";
    let terminoBusqueda = "";

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
    function render() {
        let visibles = servicios;
        if (filtro === "HOY") visibles = servicios.filter(s => s.fecha_programada === hoy());
        if (filtro === "PENDIENTE") visibles = servicios.filter(s => s.estado !== "FINALIZADO");
        if (filtro === "EJECUCION") visibles = servicios.filter(s => s.estado === "EN_PROCESO");
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
        const servicioEnEjecucion = servicios.find(s => s.estado === "EN_PROCESO");
        visibles.forEach(servicio => {
            const nodo = plantilla.content.cloneNode(true);
            const articulo = nodo.querySelector("article");
            articulo.dataset.estado = servicio.estado;
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
            const novedad = nodo.querySelector(".novedad"); novedad.value = servicio.novedad || "";
            const iniciar = nodo.querySelector(".iniciar");
            const soltar = nodo.querySelector(".soltar");
            const finalizar = nodo.querySelector(".finalizar");
            const bloqueado = servicio.bloqueado || servicio.estado === "FINALIZADO";
            const ejecucionDistinta = servicioEnEjecucion && servicioEnEjecucion.id !== servicio.id;
            novedad.disabled = bloqueado;
            iniciar.disabled = bloqueado || servicio.estado !== "PENDIENTE" || (
                !navigator.onLine && Boolean(ejecucionDistinta)
            );
            iniciar.title = !navigator.onLine && ejecucionDistinta && servicio.estado === "PENDIENTE"
                ? "Finaliza el servicio en ejecución antes de iniciar otro."
                : "";
            soltar.classList.toggle("oculto", servicio.estado !== "EN_PROCESO");
            soltar.disabled = servicio.estado !== "EN_PROCESO" || bloqueado;
            const actualizarFinalizar = () => {
                finalizar.disabled = servicio.estado !== "EN_PROCESO" || !novedad.value.trim();
                finalizar.title = servicio.estado === "EN_PROCESO" && !novedad.value.trim()
                    ? "Escribe la novedad antes de finalizar."
                    : "";
            };
            actualizarFinalizar();
            novedad.addEventListener("input", actualizarFinalizar);
            iniciar.addEventListener("click", () => cambiarEstado(servicio, "EN_PROCESO", novedad.value));
            soltar.addEventListener("click", () => {
                if (window.confirm("¿Soltar este servicio? Volverá a pendiente y se eliminará la hora de inicio registrada.")) {
                    cambiarEstado(servicio, "PENDIENTE", novedad.value);
                }
            });
            finalizar.addEventListener("click", () => cambiarEstado(servicio, "FINALIZADO", novedad.value));
            lista.appendChild(nodo);
        });
    }
    function renderAvisos(avisos) {
        const panel = document.getElementById("avisos");
        const contenedor = document.getElementById("lista-avisos");
        panel.classList.toggle("oculto", !avisos.length);
        document.getElementById("total-avisos").textContent = avisos.length;
        contenedor.innerHTML = avisos.map(a => `<div class="aviso"><strong>${escapar(a.tipo)}</strong><br>${escapar(a.mensaje)}</div>`).join("");
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
            Object.assign(servicio, data.servicio); await guardar("datos", "servicios", servicios); render();
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
    async function sincronizar() {
        await actualizarRed();
        if (!navigator.onLine) { mensaje("Continúas sin conexión."); return; }
        try {
            await enviarCola();
            const respuesta = await fetch(cfg.api, {headers: {"Accept": "application/json"}, cache: "no-store"});
            if (!respuesta.ok) throw new Error();
            const data = await respuesta.json();
            servicios = data.servicios; await guardar("datos", "servicios", servicios);
            await guardar("datos", "avisos", data.notificaciones);
            render(); renderAvisos(data.notificaciones); mensaje("Información sincronizada.");
        } catch (_) { mensaje("No fue posible conectar. Se muestran los últimos datos guardados."); }
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
    document.getElementById("btn-sincronizar").addEventListener("click", sincronizar);
    document.getElementById("btn-leer-avisos").addEventListener("click", async () => {
        if (!navigator.onLine) return mensaje("Necesitas conexión para confirmar las notificaciones.");
        await fetch(cfg.leerAvisos, {method: "POST", headers: {"X-CSRFToken": cookie("csrftoken")}});
        await guardar("datos", "avisos", []); renderAvisos([]);
    });
    document.getElementById("form-logout").addEventListener("submit", () => indexedDB.deleteDatabase("sesur-tecnico"));
    window.addEventListener("online", sincronizar); window.addEventListener("offline", actualizarRed);
    (async () => {
        servicios = await leer("datos", "servicios") || [];
        servicios = servicios.filter(s => s.estado !== "FINALIZADO" && !s.bloqueado);
        await guardar("datos", "servicios", servicios);
        render(); renderAvisos(await leer("datos", "avisos") || []); actualizarRed(); sincronizar();
        if ("serviceWorker" in navigator) navigator.serviceWorker.register(cfg.serviceWorker);
    })();
});
