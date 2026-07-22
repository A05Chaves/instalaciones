document.addEventListener("DOMContentLoaded", function () {
    const tabla = $("#tabla-mantenimientos");


    const entradaInput = document.getElementById("id_hora_entrada");
    const salidaInput = document.getElementById("id_hora_salida");
    const horasInput = document.getElementById("id_horas");
    const duracionInput = document.getElementById("duracion-servicio");
    const errorMsg = document.getElementById("horas-error");
    const guardarBtn = document.getElementById("btn-guardar");
    const busquedaInput = document.getElementById("busqueda");

    const codigoInput = document.querySelector("input[name='codigo']");
    const clienteInput = document.querySelector("input[name='cliente']");
    const ciudadInput = document.querySelector("input[name='ciudad']");
    const direccionInput = document.querySelector("input[name='direccion']");
    const ordenInput = document.querySelector("input[name='orden']");
    const realizadoInput = document.querySelector("input[name='realizado']");

    function calcularHoras() {
        if (!entradaInput || !salidaInput || !horasInput || !duracionInput || !errorMsg) return;

        const entrada = entradaInput.value;
        const salida = salidaInput.value;

        if (entrada && salida) {
            const [eh, em] = entrada.split(":").map(Number);
            const [sh, sm] = salida.split(":").map(Number);

            const entradaMin = eh * 60 + em;
            const salidaMin = sh * 60 + sm;
            const diferencia = salidaMin - entradaMin;

            if (diferencia <= 0) {
                horasInput.value = "";
                duracionInput.value = "---";
                duracionInput.classList.add("is-invalid");
                errorMsg.classList.remove("d-none");
                if (guardarBtn) guardarBtn.disabled = true;
            } else {
                horasInput.value = (diferencia / 60).toFixed(2);
                const horas = String(Math.floor(diferencia / 60)).padStart(2, "0");
                const minutos = String(diferencia % 60).padStart(2, "0");
                duracionInput.value = `${horas}:${minutos}`;
                duracionInput.classList.remove("is-invalid");
                errorMsg.classList.add("d-none");
                if (guardarBtn) guardarBtn.disabled = false;
            }
        } else {
            horasInput.value = "";
            duracionInput.value = "---";
            duracionInput.classList.remove("is-invalid");
            errorMsg.classList.add("d-none");
            if (guardarBtn) guardarBtn.disabled = false;
        }
    }

    if (entradaInput && salidaInput) {
        entradaInput.addEventListener("change", calcularHoras);
        salidaInput.addEventListener("change", calcularHoras);
        calcularHoras();
    }

    if (busquedaInput) {
        busquedaInput.addEventListener("input", function () {
            clearTimeout(busquedaInput._timeout);
            busquedaInput._timeout = setTimeout(() => {
                this.form.submit();
            }, 600);
        });
    }

    if (ordenInput && realizadoInput) {
        ordenInput.addEventListener("change", function () {
            const valor = this.value.trim();

            if (valor && !realizadoInput.value) {
                const hoy = new Date();
                const y = hoy.getFullYear();
                const m = String(hoy.getMonth() + 1).padStart(2, "0");
                const d = String(hoy.getDate()).padStart(2, "0");
                realizadoInput.value = `${y}-${m}-${d}`;
            }
        });
    }

    if (codigoInput && clienteInput && ciudadInput && direccionInput) {
        codigoInput.addEventListener("change", function () {
            const codigo = this.value.trim();

            clienteInput.value = "";
            ciudadInput.value = "";
            direccionInput.value = "";

            if (!codigo) return;

            fetch(`/api/instalacion-por-codigo/?codigo=${encodeURIComponent(codigo)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.ok) {
                        clienteInput.value = data.cliente || "";
                        ciudadInput.value = data.ciudad || "";
                        direccionInput.value = data.direccion || "";
                    }
                })
                .catch(error => {
                    console.error("Error buscando instalación:", error);
                });
        });
    }

    function getCookie(name) {
        let cookieValue = null;

        if (document.cookie && document.cookie !== "") {
            const cookies = document.cookie.split(";");

            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();

                if (cookie.substring(0, name.length + 1) === name + "=") {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }

        return cookieValue;
    }

    function activarModoEdicion(tr, soloOrden = false) {
        if (soloOrden) {
            tr.classList.add("solo-orden");
            tr.querySelectorAll(".campo-orden .view-mode").forEach(el => el.classList.add("d-none"));
            tr.querySelectorAll(".campo-orden .edit-mode").forEach(el => el.classList.remove("d-none"));
            tr.classList.add("editing");
            return;
        }
        tr.querySelectorAll(".view-mode").forEach(el => el.classList.add("d-none"));
        tr.querySelectorAll(".edit-mode").forEach(el => el.classList.remove("d-none"));
        tr.classList.add("editing");
    }

    function desactivarModoEdicion(tr) {
        if (tr.classList.contains("solo-orden")) {
            tr.querySelectorAll(".campo-orden .view-mode").forEach(el => el.classList.remove("d-none"));
            tr.querySelectorAll(".campo-orden .edit-mode").forEach(el => el.classList.add("d-none"));
            tr.classList.remove("solo-orden", "editing");
            return;
        }
        tr.querySelectorAll(".view-mode").forEach(el => el.classList.remove("d-none"));
        tr.querySelectorAll(".edit-mode").forEach(el => el.classList.add("d-none"));
        tr.classList.remove("editing");
    }

    function guardarFila(tr, id) {
        const formData = new FormData();

        tr.querySelectorAll(".edit-mode[name]").forEach(input => {
            formData.append(input.name, input.value);
        });

        fetch(`/mantenimientos/${id}/actualizar/`, {
            method: "POST",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: formData,
        })
            .then(resp => resp.json())
            .then(data => {
                if (data.ok) {
                    window.location.reload();
                } else {
                    alert("No se pudo guardar. Intenta nuevamente.");
                }
            })
            .catch(error => {
                console.error(error);
                alert("Error al guardar.");
            });
    }

    document.querySelectorAll(".btn-inline-edit").forEach(btn => {
        btn.addEventListener("click", function () {
            const id = this.dataset.id;
            const tr = this.closest("tr");

            if (!tr.classList.contains("editing")) {
                activarModoEdicion(tr, this.dataset.soloOrden === "true");

                this.classList.remove("btn-outline-primary");
                this.classList.add("btn-success");
                this.innerHTML = '<i class="fas fa-save"></i>';

                let btnCancel = tr.querySelector(".btn-inline-cancel");

                if (!btnCancel) {
                    btnCancel = document.createElement("button");
                    btnCancel.type = "button";
                    btnCancel.className = "btn btn-sm btn-secondary btn-inline-cancel ms-1";
                    btnCancel.innerHTML = '<i class="fas fa-times"></i>';
                    this.parentElement.appendChild(btnCancel);

                    btnCancel.addEventListener("click", function () {
                        desactivarModoEdicion(tr);
                        btn.classList.remove("btn-success");
                        btn.classList.add("btn-outline-primary");
                        btn.innerHTML = '<i class="fas fa-edit"></i>';
                        btnCancel.remove();
                    });
                }
            } else {
                guardarFila(tr, id);
            }
        });
    });

    const modalEliminar = document.getElementById("modalEliminarMantenimiento");
    const formEliminar = document.getElementById("formEliminarMantenimiento");
    const textoClienteEliminar = document.getElementById("textoClienteEliminar");

    document.querySelectorAll(".btn-inline-delete").forEach(btn => {
        btn.addEventListener("click", function () {
            const id = this.dataset.id;
            const cliente = this.dataset.cliente || "";

            if (formEliminar && textoClienteEliminar && modalEliminar) {
                formEliminar.action = `/mantenimientos/${id}/eliminar/`;
                textoClienteEliminar.textContent = cliente;

                const modal = new bootstrap.Modal(modalEliminar);
                modal.show();
            }
        });
    });

    const modalUpload = document.getElementById("modalSubirArchivo");
    const formUpload = document.getElementById("formSubirArchivo");

    document.querySelectorAll(".btn-inline-upload").forEach(btn => {
        btn.addEventListener("click", function () {
            const id = this.dataset.id;

            if (formUpload && modalUpload) {
                formUpload.action = `/mantenimientos/${id}/subir-archivo/`;
                formUpload.reset();

                const modal = new bootstrap.Modal(modalUpload);
                modal.show();
            }
        });
    });
});
