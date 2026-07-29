(function () {
    const config = window.SESUR_SESSION;
    if (!config || !config.renovar) return;

    const intervaloRenovacion = 5 * 60 * 1000;
    let ultimaRenovacion = Date.now();
    let renovando = false;

    function cookie(nombre) {
        const prefijo = `${nombre}=`;
        const item = document.cookie
            .split(";")
            .map(valor => valor.trim())
            .find(valor => valor.startsWith(prefijo));
        return item ? decodeURIComponent(item.slice(prefijo.length)) : "";
    }

    async function registrarActividad() {
        const ahora = Date.now();
        if (
            renovando ||
            ahora - ultimaRenovacion < intervaloRenovacion ||
            !navigator.onLine
        ) {
            return;
        }

        renovando = true;
        try {
            const respuesta = await fetch(config.renovar, {
                method: "POST",
                credentials: "same-origin",
                cache: "no-store",
                keepalive: true,
                headers: {
                    "X-CSRFToken": cookie("csrftoken"),
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            if (respuesta.ok) ultimaRenovacion = ahora;
        } catch (_) {
            // Sin conexión no se simula actividad; se renovará al reconectar.
        } finally {
            renovando = false;
        }
    }

    ["pointerdown", "keydown", "input", "scroll", "touchstart"].forEach(
        evento => window.addEventListener(
            evento,
            registrarActividad,
            {passive: true}
        )
    );
})();
